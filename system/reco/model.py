import json
import os
import threading 
from typing import Dict, Any, List, Union
from openai import OpenAI
from reco.ges.ges import GestureRecognizer
from reco.face.face import FaceRecognizer  # 假设你的 face 识别模块是 face.py 中的 FaceRecognizer 类
import cv2
import time
from reco.whis.wav_text import VoiceRecognizer
from flask import Response, session
from logs.log import insert_log

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
    "用户姿态": {
        "code": "USER_POSTURE",
        "params": {"pos_type": "str", "action": "str"},
        "safety_check": lambda p: p.get("pos_type") 
        in ["点头确认", "摇头拒绝", "低头看手机", "向右说话", "向左说话", "注意力偏离超过3秒", "注视前方"]
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
    "手势识别": ["[手势]", "[视觉焦点]"],
    "语音识别": ["[语音]", "[协议]", "[规则]"],
    "面部识别": ["[面部]", "[面部姿态]"],
    "多模态反馈": ["[多传感器]", "[系统状态]", "[雷达]", "[相机]", "[GPS]"]
}

class DrivingSystem:
    def __init__(self, output_queue, output_condition, username='system', role='system'):
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
        self.output_queue = output_queue
        self.output_condition = output_condition
        self.username = username
        self.role = role

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
        if input_mode == "手势识别":
            if "[手势]" in text:
                return f"[手势输入] {cleaned_text}"
            return f"[视觉焦点数据] {cleaned_text}"
        
        elif input_mode == "语音识别":
            if "[语音]" in text:
                return f"[语音指令] {cleaned_text}"
            return f"[协议触发] {cleaned_text}"
        
        elif input_mode == "面部识别":
            if "[面部]" in text:
                return f"[面部指令] {cleaned_text}"
            return f"[用户姿态数据] {cleaned_text}"
        
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
        
        # 🔧 修复：处理用户姿态参数，保留原始信息
        if "用户姿态" in params:
            normalized = {
                "pos_type": params["用户姿态"], 
                "action": params.get("动作", "默认动作")
            }
            # 🔧 保留持续时间等其他重要信息
            if "持续时间" in params:
                normalized["duration"] = params["持续时间"]
            return normalized
            
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
                "面部": "用户姿态",
                "协议": "协议指令"
            }
            
            intent = data.get("intent", "")
            normalized_params = self.normalize_params(intent, data.get("params", {}))
            
            # 🔧 添加调试日志
            print(f"🔍 API解析调试:")
            print(f"   原始intent: {intent}")
            print(f"   标准化intent: {intent_map.get(intent, intent)}")
            print(f"   原始params: {data.get('params', {})}")
            print(f"   标准化params: {normalized_params}")
            
            return {
                "intent": intent_map.get(intent, intent),
                "params": normalized_params
            }
            
        except (json.JSONDecodeError, IndexError) as e:
            print(f"解析错误: {str(e)}\nAPI返回内容: {content}")
            return {"intent": "速度控制", "params": {"target_speed": 0}}

    def call_deepseek_driving_api(self, text: str) -> Dict[str, Any]:
        # 根据输入类型确定系统提示
        input_mode = self.identify_input_mode(text)
        system_prompt = "你是一个智能驾驶助手，根据提供的情况选择合适的指令，请严格按JSON格式返回指令。其中intent只能从 速度控制、转向操作、紧急制动、手势控制、语音指令、协议指令、用户姿态 中选取"
        
        # 根据不同输入模式调整系统提示
        if input_mode == "手势识别":
            system_prompt += "特别注意处理手势相关的输入。"
        elif input_mode == "语音识别":
            system_prompt += "特别注意处理语音指令和系统协议触发。"
        elif input_mode == "面部识别":
            system_prompt += "特别注意处理视觉焦点、用户姿态相关的输入。"
        
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
                        要求字段：intent(操作类型), params(根据输入类型可包含速度值/转向角/手势类型/用户姿态/命令内容等)"""
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
        print(f"🔍 generate_safe_instruction 调试:")
        print(f"   输入response: {response}")
        
        if response["intent"] == "紧急制动":
            return {
                "强制指令": "EMG_BRAKE",
                "参数": {"force_level": 3},
                "系统日志": "触发AEB自动紧急制动"
            }
        
        # 手势特殊处理
        if response["intent"] == "手势控制":
            print("手势: \n")
            posture = response["params"].get("gesture_type")
            if posture == "握拳":
                print("握拳: \n")
                return {
                    "强制指令": "EMG_BRAKE",
                    "参数": {"force_level": 2},
                    "系统日志": "握拳手势音乐暂停"
                }
            
            if posture == "拇指向上":
                return {
                    "强制指令": "EMG_BRAKE",
                    "参数": {"force_level": 2},
                    "系统日志": "竖起大拇指表示确认"
                }
            
            if posture == "挥手":
                return {
                    "强制指令": "EMG_BRAKE",
                    "参数": {"force_level": 2},
                    "系统日志": "挥手表示启动语音服务"
                }
        
        # 🔧 修复：用户姿态处理逻辑
        if response["intent"] == "用户姿态":
            posture = response["params"].get("pos_type")  # 从标准化参数中获取
            duration = response["params"].get("duration", "")  # 从标准化参数中获取持续时间
            
            print(f"🔍 用户姿态处理调试:")
            print(f"   posture: {posture}")
            print(f"   duration: {duration}")
            
            # 🔧 构建完整的姿态描述
            full_posture = f"{posture}{duration}".replace(" ", "") if posture else ""
            print(f"   full_posture: '{full_posture}'")

            if posture == "点头确认":
                return {
                    "强制指令": "EMG_BRAKE",
                    "参数": {"force_level": 2},
                    "系统日志": "检测到用户点头，表示确认"
                }
            
            if posture == "摇头拒绝":
                return {
                    "强制指令": "EMG_BRAKE",
                    "参数": {"force_level": 2},
                    "系统日志": "检测到用户摇头，已拒绝相关操作"
                }
            
            if posture == "低头看手机":
                return {
                    "强制指令": "EMG_BRAKE",
                    "参数": {"force_level": 2},
                    "系统日志": "检测到用户低头玩手机，驾驶注意力可能不集中"
                }
        
            # 注意力偏离检测逻辑 - 添加乘客检查
            if full_posture == "注意力偏离超过3秒" or posture == "注意力偏离":
                print("🚨 检测到注意力偏离状态！")
                
                # 🔧 简单检查：如果是乘客，跳过警告
                if self.role == 'passenger':
                    print(f"👤 乘客用户，跳过注意力偏离警告")
                    return {
                        "强制指令": "PASSENGER_LOG",
                        "系统日志": f"检测到注意力状态变化（乘客模式，无需警告）"
                    }
                
                # 非乘客用户，正常触发注意力偏离警告（保持原有逻辑）
                print("🚨 触发注意力偏离警告！")
                return {
                    "强制指令": "ATTENTION_WARNING",
                    "参数": {"warning_level": "critical"},
                    "系统日志": "⚠ 警告：用户注意力偏离",
                    "警告类型": "attention_deviation",
                    "需要音频警告": True,
                    "警告消息": "警告！请注视前方"
                }
            
            if posture == "向右说话" or posture == "向左说话":
                return {
                    "强制指令": "EMG_BRAKE",
                    "参数": {"force_level": 2},
                    "系统日志": "检测到用户转头说话，注意观察周围环境"
                }
        
        # 这一句是为了处理没有意图的情况
        rule = DRIVING_RULES.get(response["intent"])
        if not rule:
            print(f"⚠ 未找到规则: {response['intent']}")
            return {"默认指令": "MAINTAIN_CURRENT_STATE"}
        
        safety_check = rule.get("safety_check", lambda x: True)
        if safety_check(response["params"]):
            return {
                "指令": rule["code"],
                "参数": response["params"],
                "系统日志": f"执行{response['intent']}操作"
            }
        print(f"⚠ 安全检查失败: {response}")
        return {"默认指令": "MAINTAIN_CURRENT_STATE"}
    

    def process_driving_command(self, input_text: str) -> Dict[str, Any]:
        processed = self.preprocess_driving_data(input_text)
        api_response = self.call_deepseek_driving_api(processed)
        result = self.generate_safe_instruction(api_response)
        print(f"🔍 最终处理结果: {result}")
        return result

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
        re = json.dumps(result, ensure_ascii=False, indent=2)
        print(re)
        if isinstance(result, dict) and "系统日志" in result:
            log_message = result["系统日志"]
            print("存储 logs:", log_message)
            insert_log(self.username, self.role,"语音", log_message)
        with self.output_condition:
            self.output_queue.append(result)
            print("📤 加入\n")
            self.output_condition.notify_all()


    def handle_status_change(self, text: str):
        """
        回调函数
        """
        print("收到面部，正在处理...")
        result = self.process_driving_command(f"[面部] {text}")
        print("指令生成结果:")
        re = json.dumps(result, ensure_ascii=False, indent=2)
        print(re)
        if isinstance(result, dict) and "系统日志" in result:
            log_message = result["系统日志"]
            print("存储 logs:", log_message)
            insert_log(self.username, self.role,"面部", log_message)
        with self.output_condition:
            self.output_queue.append(result)
            print("📤 加入\n")
            self.output_condition.notify_all()
    

    def handle_ges_change(self, text: str):
        """
        回调函数
        """
        print("收到手势，正在处理...")
        result = self.process_driving_command(f"[手势] {text}")
        print("指令生成结果:")
        re = json.dumps(result, ensure_ascii=False, indent=2)
        print(re)
        if isinstance(result, dict) and "系统日志" in result:
            log_message = result["系统日志"]
            print("存储 logs:", log_message)
            insert_log(self.username, self.role,"手势", log_message)
        with self.output_condition:
            self.output_queue.append(result)
            print("📤 加入\n")
            self.output_condition.notify_all()
    

    def get_stream(self):
        def event_stream():
            while True:
                try:
                    with self.output_condition:
                        while not self.output_queue:
                            print("🛑 等待新数据\n")
                            self.output_condition.wait()
                        result = self.output_queue.popleft()
                        print("✅ 发送新数据:\n", result)
                        # yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
                        # 传送系统日志字段
                        if isinstance(result, dict) and "系统日志" in result:
                            log_message = result["系统日志"]
                            print("📤 发送系统日志:", log_message)
                            yield f"data: {json.dumps(log_message, ensure_ascii=False)}\n\n"
                        else:
                            print("⏩ 跳过无系统日志的数据")
                            continue
                except Exception as e:
                    print("🚨 /stream 内部异常：", e)
                    break
        return Response(event_stream(), mimetype='text/event-stream')