import json
import os
import threading
from typing import Dict, Any, List, Union
from openai import OpenAI
from ges.ges import GestureRecognizer
from face.face import FaceRecognizer  # 假设你的 face 识别模块是 face.py 中的 FaceRecognizer 类
import cv2
import time
from whis.wav_text import VoiceRecognizer
# 驾驶规则配置
DRIVING_RULES = {
    "速度控制": {
        "code": "SPEED_CTRL",
        "params": {"target_speed": "float", "acceleration": "float"},
        "safety_check": lambda p: 0 <= p.get("target_speed", 0) <= 120
    },
    "转向操作": {
        "code": "STEERING_CTRL",
        "params": {"angle": "float", "direction": ["left", "right"]},
        "safety_check": lambda p: -45 <= p.get("angle", 0) <= 45
    },
    "紧急制动": {
        "code": "EMG_BRAKE",
        "params": {"force_level": [1, 2, 3]},
        "priority": 0,
        "safety_check": lambda p: p.get("force_level", 1) in [1, 2, 3]
    },
    "手势控制": {
        "code": "GESTURE_CTRL",
        "params": {"gesture_type": "str", "action": "str"},
        "safety_check": lambda p: p.get("gesture_type") in ["挥手", "握拳", "食指指向", "拇指向上"]
    },
    "语音指令": {
        "code": "VOICE_CMD",
        "params": {"command": "str"},
        "safety_check": lambda p: True  # 语音指令安全检查在解析阶段处理
    },
    "协议指令": {
        "code": "PROTOCOL_CMD",
        "params": {"protocol_id": "str", "action": "str"},
        "priority": 1,
        "safety_check": lambda p: True
    }
}

# 输入模式定义
INPUT_MODES = {
    "焦点识别": ["[手势]", "[视觉焦点]"],
    "语音识别": ["[语音]", "[协议]", "[规则]"],
    "多模态反馈": ["[多传感器]", "[系统状态]", "[雷达]", "[相机]", "[GPS]"]
}

class DrivingSystem:
    def __init__(self):
        os.environ["DASHSCOPE_API_KEY"] = "sk-8e2f065fa5314b0b91deaf67ca6e969f"
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise ValueError("请设置 DASHSCOPE_API_KEY 环境变量")

        self.client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.preserved_terms = ["加速", "减速", "左转", "右转", "米", "km/h", "障碍物"]
        self.voice_recognizer = VoiceRecognizer(on_transcription=self.handle_transcription)
        
        self.gesture_recognizer = GestureRecognizer(on_ges_change=self.handle_ges_change)
        self.face_recognizer = FaceRecognizer(on_status_change=self.handle_status_change)
        self.cap = None
        # self.frame = None
        self.latest_frame = None  # 主线程采集的最新帧
        self.gesture_result = None
        self.face_result = None
        self.gesture_lock = threading.Lock()
        self.face_lock = threading.Lock()
        self.frame_lock = threading.Lock()
        self.running = False
    def identify_input_mode(self, text: str) -> str:
        """识别输入文本的来源模式"""
        for mode, prefixes in INPUT_MODES.items():
            for prefix in prefixes:
                if prefix in text:
                    return mode
        return "未知来源"

    def preprocess_driving_data(self, text: str) -> str:
        # 识别输入模式
        input_mode = self.identify_input_mode(text)
        
        # 清理无效信号
        cleaned_text = "".join([c for c in text if c not in ["[无效信号]"]])
        
        # 根据输入模式处理
        if input_mode == "焦点识别":
            if "[手势]" in text:
                return f"[手势输入] {cleaned_text}"
            return f"[视觉焦点数据] {cleaned_text}"
        
        elif input_mode == "语音识别":
            if "[语音]" in text:
                return f"[语音指令] {cleaned_text}"
            return f"[协议触发] {cleaned_text}"
        
        elif input_mode == "多模态反馈":
            for sensor in ["多传感器", "系统状态", "雷达", "相机", "GPS"]:
                if f"[{sensor}]" in text:
                    return f"[{sensor}数据上下文] {cleaned_text}"
        
        return cleaned_text

    def normalize_params(self, intent: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """标准化参数格式"""
        if "速度值" in params:
            return {"target_speed": params["速度值"]}
        if "转向角" in params:
            return {"angle": params["转向角"]}
        
        # 处理手势参数
        if "手势类型" in params:
            return {"gesture_type": params["手势类型"], "action": params.get("动作", "默认动作")}
        
        # 处理语音命令参数
        if "命令内容" in params:
            return {"command": params["命令内容"]}
            
        return params

    def parse_api_response(self, content: str) -> Dict[str, Any]:
        """解析API响应内容"""
        try:
            # 处理被json包裹的情况
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()

            # 尝试解析JSON
            data = json.loads(content)
            
            # 标准化意图
            intent_map = {
                "减速": "速度控制",
                "加速": "速度控制",
                "左转": "转向操作",
                "右转": "转向操作",
                "手势": "手势控制",
                "语音命令": "语音指令",
                "协议": "协议指令"
            }
            
            intent = data.get("intent", "")
            return {
                "intent": intent_map.get(intent, intent),
                "params": self.normalize_params(intent, data.get("params", {}))
            }
            
        except (json.JSONDecodeError, IndexError) as e:
            print(f"解析错误: {str(e)}\nAPI返回内容: {content}")
            return {"intent": "速度控制", "params": {"target_speed": 0}}

    def call_deepseek_driving_api(self, text: str) -> Dict[str, Any]:
        # 根据输入类型确定系统提示
        input_mode = self.identify_input_mode(text)
        system_prompt = "你是一个智能驾驶助手，根据提供的情况选择合适的指令，请严格按JSON格式返回指令。其中intent只能从 速度控制、转向操作、紧急制动、手势控制、语音指令、协议指令、用户姿态 中选取"
        
        # 根据不同输入模式调整系统提示
        if input_mode == "焦点识别":
            system_prompt += "特别注意处理手势和视觉焦点、用户头部姿态相关的输入。"
        elif input_mode == "语音识别":
            system_prompt += "特别注意处理语音指令和系统协议触发。"
        
        try:
            completion = self.client.chat.completions.create(
                model="qwen-plus",
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": f"""严格按JSON格式解析驾驶指令：
                        输入：{text}
                        要求字段：intent(操作类型), params(根据输入类型可包含速度值/转向角/手势类型/命令内容等)"""
                    }
                ]
            )
            
            content = completion.choices[0].message.content

            # 输出调试信息
            print("--------------------------------------")
            print(f"API返回内容: {content}")
            print("--------------------------------------")
            return self.parse_api_response(content)
                
        except Exception as e:
            print(f"API调用错误: {str(e)}")
            return {"intent": "速度控制", "params": {"target_speed": 0}}

    def generate_safe_instruction(self, response: Dict[str, Any]) -> Dict[str, Any]:
        if response["intent"] == "紧急制动":
            return {
                "强制指令": "EMG_BRAKE",
                "参数": {"force_level": 3},
                "系统日志": "触发AEB自动紧急制动"
            }
        
        # 手势特殊处理
        if response["intent"] == "手势控制" and response["params"].get("gesture_type") == "握拳":
            return {
                "强制指令": "EMG_BRAKE",
                "参数": {"force_level": 2},
                "系统日志": "握拳手势触发紧急停车"
            }
        
        # 这一句是为了处理没有意图的情况
        rule = DRIVING_RULES.get(response["intent"])
        if not rule:
            return {"默认指令": "MAINTAIN_CURRENT_STATE"}
        
        safety_check = rule.get("safety_check", lambda x: True)
        if safety_check(response["params"]):
            return {
                "指令": rule["code"],
                "参数": response["params"],
                "系统日志": f"执行{response['intent']}操作"
            }
        return {"默认指令": "MAINTAIN_CURRENT_STATE"}

    def process_driving_command(self, input_text: str) -> Dict[str, Any]:
        processed = self.preprocess_driving_data(input_text)
        api_response = self.call_deepseek_driving_api(processed)
        return self.generate_safe_instruction(api_response)

    def handle_transcription(self, text: str):
        """
        回调函数，处理转写的语音文本。
        1. 包装为语音输入格式
        2. 传入大模型分析意图
        3. 输出最终指令
        """
        print("收到语音文本，正在处理...")
        result = self.process_driving_command(f"[语音] {text}")
        print("指令生成结果:")
        print(json.dumps(result, ensure_ascii=False, indent=2))    

    def handle_status_change(self, text: str):
        """
        回调函数
        """
        print("收到面部，正在处理...")
        result = self.process_driving_command(f"[面部] {text}")
        print("指令生成结果:")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    def handle_ges_change(self, text: str):
        """
        回调函数
        """
        print("收到手势，正在处理...")
        result = self.process_driving_command(f"[手势] {text}")
        print("指令生成结果:")
        print(json.dumps(result, ensure_ascii=False, indent=2))

def test_driving_system():
    """
    测试不同数据源的驾驶指令处理
    
    输入规则说明:
    1. 焦点识别模块: [手势], [视觉焦点]
    2. 语音识别模块: [语音], [协议], [规则]
    3. 多模态反馈模块: [多传感器], [系统状态], [雷达], [相机], [GPS]
    """
    system = DrivingSystem()

    # 测试用例
    test_cases = [
        # 焦点识别模块
        "[手势] 五指张开 → 激活系统",
        "[手势] 握拳 → 紧急暂停",
        "[视觉焦点] 驾驶员视线停留在左侧后视镜",
        
        # 语音识别模块
        "[语音] \"请降低车速到60公里\"",
        "[语音] \"下一个路口右转\"",
        "[协议] 检测到疲劳驾驶：触发警报协议3.2",
        "[规则] 雨天限速规则激活",
        
        # 多模态反馈模块
        "[多传感器] 雷达检测前方10米障碍物 + 摄像头识别红灯",
        "[系统状态] 电池电量剩余30% + 胎压异常",
        "[雷达] 前方障碍物距离5米,相对速度20km/h",
        "[相机] 前方红灯,需要减速停车",
        "[GPS] 前方500米有急转弯"
    ]

    print("=== 开始驾驶系统测试 ===")
    for test_input in test_cases:
        print(f"\n测试输入: {test_input}")
        print(f"输入模式: {system.identify_input_mode(test_input)}")
        result = system.process_driving_command(test_input)
        print("处理结果:", json.dumps(result, ensure_ascii=False, indent=2))
    print("=== 测试完成 ===")

    # 测试复合输入
    print("\n=== 测试复合输入 ===")
    complex_input = [
        "[手势] 食指指向导航屏幕",
        "[语音] '避开当前拥堵路线'",
        "[协议] 夜间行驶自动开启远光灯",
        "[多传感器] 超声波:左侧0.5m障碍物"
    ]

    for input_text in complex_input:
        print(f"\n测试输入: {input_text}")
        print(f"输入模式: {system.identify_input_mode(input_text)}")
        result = system.process_driving_command(input_text)
        print("处理结果:", json.dumps(result, ensure_ascii=False, indent=2))
    print("=== 复合输入测试完成 ===")