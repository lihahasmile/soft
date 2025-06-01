from flask import Flask, render_template, Response, request, jsonify, session, redirect
import time
import threading
import concurrent.futures
from reco.model import DrivingSystem
import keyboard
import cv2
import json
import traceback
import requests
import os
from collections import deque
import sqlite3
import base64
import speech_recognition as sr
import io
import wave
from pydub import AudioSegment
import whisper
import tempfile
import os
from logs.log import log_bp, insert_log

app = Flask(__name__)
# python -c "import secrets; print(secrets.token_hex(32))"
app.secret_key = '15d3e837bbe935321c7ee7cd00f6fd47058e5b74d5920ee2420cb7d937e5fc57'
app.register_blueprint(log_bp,url_prefix='/logs')
# === 全局共享资源 ===
output_queue = deque()
output_condition = threading.Condition()

vehicle_status = {
    "ac": {"status": "关闭", "temperature": 24, "mode": "制冷"},
    "music": {"status": "暂停", "volume": 40, "current_song": ""},
    "navigation": {"status": "关闭", "destination": ""},
    "camera": {"status": "关闭"},
    "media": {"status": "暂停", "volume": 70},
    "lights": {"status": "关闭"},
    "windows": {"status": "关闭"}
}
# system = DrivingSystem(output_queue, output_condition)
system = None

# 共享帧和锁
latest_frame = None
frame_lock = threading.Lock()
stop_event = threading.Event()
threads_started = threading.Event()

def capture_frame():
    try:
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 15)

        print("摄像头启动成功，开始读取帧...")
        while not stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                continue
            with frame_lock:
                global latest_frame
                latest_frame = frame.copy()

            # cv2.imshow("Camera", frame)
            # if cv2.waitKey(1) & 0xFF == ord('q'):
            #     stop_event.set()
            #     break

            time.sleep(0.01)

        cap.release()
        cv2.destroyAllWindows()
        print("摄像头释放")
    except Exception as e:
        print("[异常] capture_frame:", e)
        traceback.print_exc()


def handle_face_recognition():
    print("启动面部识别")
    try:
        while not stop_event.is_set():
            with frame_lock:
                if latest_frame is None:
                    continue
                frame_copy = latest_frame.copy()
            system.face_recognizer.process_frame(frame_copy)
            time.sleep(0.05)
    except Exception as e:
        print("[异常] handle_face_recognition:", e)
        traceback.print_exc()


def handle_gesture_recognition():
    print("启动手势识别")
    try:
        while not stop_event.is_set():
            with frame_lock:
                if latest_frame is None:
                    continue
                frame_copy = latest_frame.copy()
            system.gesture_recognizer.process(frame_copy)
            time.sleep(0.05)
    except Exception as e:
        print("[异常] handle_gesture_recognition:", e)
        traceback.print_exc()

# 修改：移除自动启动的语音识别，只保留按需调用的语音识别功能
def handle_voice_recognition_on_demand():
    """
    按需启动的语音识别处理函数 - 不再自动启动
    语音识别现在通过Web API按需调用
    """
    try:
        print("语音识别系统已就绪，等待按需调用...")
        # 不再自动启动语音识别，只是保持系统就绪状态
        while not stop_event.is_set():
            time.sleep(1)  # 保持线程活跃，但不执行任何识别操作
    except Exception as e:
        print("[异常] handle_voice_recognition_on_demand:", e)
        traceback.print_exc()

def normalize_chinese_text(text):
    """
    标准化中文文本，将繁体转换为简体，统一异体字
    特别针对车载系统的音乐、导航、空调功能
    """
    # 繁体到简体的映射 - 特别加强车载功能相关词汇
    traditional_to_simplified = {
        # === 基础操作词汇 ===
        '開': '开', '關': '关', '打開': '打开', '關閉': '关闭', '開啟': '开启',
        '啟動': '启动', '停止': '停止', '暫停': '暂停', '調節': '调节', '調整': '调整',
        '設置': '设置', '控制': '控制', '執行': '执行', '運行': '运行', '操作': '操作',
        
        # === 音乐/媒体相关 ===
        '音樂': '音乐', '樂': '乐', '歌曲': '歌曲', '播放': '播放', '暫停': '暂停',
        '音量': '音量', '聲音': '声音', '響度': '响度', '媒體': '媒体', '音響': '音响',
        '聲': '声', '響': '响', '頻': '频', '率': '率', '調': '调', '節': '节',
        '大聲': '大声', '小聲': '小声', '靜音': '静音', '音效': '音效', '效果': '效果',
        
        # === 导航相关 ===
        '導航': '导航', '導': '导', '航': '航', '路線': '路线', '線': '线',
        '到航': '导航',
        '到行': '导航',
        '地圖': '地图', '圖': '图', '前往': '前往', '到達': '到达', '達': '达',
        '位置': '位置', '地點': '地点', '點': '点', '目標': '目标', '標': '标',
        '路徑': '路径', '徑': '径', '方向': '方向', '導向': '导向', '指引': '指引',
        
        # === 空调相关 ===
        '空調': '空调', '調': '调', '冷氣': '冷气', '氣': '气', '暖氣': '暖气',
        '溫度': '温度', '溫': '温', '度': '度', '製冷': '制冷', '製熱': '制热',
        '風速': '风速', '風': '风', '速': '速', '檔位': '档位', '檔': '档',
        '涼': '凉', '熱': '热', '冷': '冷', '暖': '暖', '舒適': '舒适', '適': '适',
        
        
        
        # === 系统相关 ===
        '系統': '系统', '統': '统', '設備': '设备', '備': '备', '裝置': '装置',
        '裝': '装', '置': '置', '設定': '设定', '定': '定', '配置': '配置',
        '電': '电', '腦': '脑', '網': '网', '絡': '络', '連': '连', '接': '接',
        
        
        # === 时间/位置介词 ===
        '於': '于', '為': '为', '與': '与', '從': '从', '來': '来', '還': '还',
        '這': '这', '那': '那', '個': '个', '們': '们', '時': '时', '間': '间',
        
        # === 常用动词 ===
        '應': '应', '該': '该', '會': '会', '將': '将', '請': '请', '讓': '让',
        '給': '给', '對': '对', '說': '说', '話': '话', '聽': '听', '見': '见',
        '看': '看', '選': '选', '擇': '择', '選擇': '选择', '確認': '确认',
        '確': '确', '認': '认', '取消': '取消', '返回': '返回', '退出': '退出',
        
        # === 数量/程度 ===
        '個': '个', '種': '种', '類': '类', '樣': '样', '種類': '种类',
        '數量': '数量', '數': '数', '量': '量', '大小': '大小', '高低': '高低',
        '強弱': '强弱', '強': '强', '弱': '弱', '多少': '多少', '幾': '几',
        
        # === 特殊词组 ===
        '開始': '开始', '結束': '结束', '結': '结', '束': '束', '完成': '完成',
        '成功': '成功', '失敗': '失败', '敗': '败', '錯誤': '错误', '錯': '错',
        '誤': '误', '正確': '正确', '好的': '好的', '可以': '可以', '不行': '不行'
    }
    
    # 先进行词组替换（长词优先）
    result = text
    word_mappings = {
        '關閉音樂': '关闭音乐', '打開空調': '打开空调', '開啟導航': '开启导航',
        '暫停音樂': '暂停音乐', '調節溫度': '调节温度', '調整音量': '调整音量',
        '設置導航': '设置导航', '啟動系統': '启动系统', '關閉系統': '关闭系统',
        '播放音樂': '播放音乐', '停止播放': '停止播放', '開始導航': '开始导航',
        '結束導航': '结束导航', '調高音量': '调高音量', '調低音量': '调低音量',
        '調高溫度': '调高温度', '調低溫度': '调低温度', '打開車燈': '打开车灯',
        '關閉車燈': '关闭车灯', '開啟攝像頭': '开启摄像头', '關閉攝像頭': '关闭摄像头'
    }
    
    # 先替换词组
    for traditional_phrase, simplified_phrase in word_mappings.items():
        result = result.replace(traditional_phrase, simplified_phrase)
    
    # 再进行单字符替换
    final_result = ''
    for char in result:
        final_result += traditional_to_simplified.get(char, char)
    
    return final_result

def parse_voice_command(text):
    """解析语音指令并返回操作结果（支持繁简体中文）"""
    global vehicle_status
    
    # 先标准化文本（繁体转简体）
    text = normalize_chinese_text(text).lower().strip()
    
    result = {
        "success": False,
        "message": "",
        "action": "",
        "status_changes": {},
        "ui_updates": {}
    }
    
    try:
        # 空调控制 - 支持繁简体
        if any(keyword in text for keyword in ["空调", "冷气", "暖气", "空調", "冷氣", "暖氣", "制冷", "空條"]):
            if any(keyword in text for keyword in ["打开", "开启", "开", "打開", "開啟", "開", "启动", "啟動"]):
                vehicle_status["ac"]["status"] = "开启"
                result.update({
                    "success": True,
                    "message": "空调已开启",
                    "action": "ac_on",
                    "status_changes": {"ac": vehicle_status["ac"]},
                    "ui_updates": {"ac_indicator": "on", "highlight_card": "ac"}
                })
            elif any(keyword in text for keyword in ["关闭", "关", "停止", "關閉", "關", "停止", "关掉", "關掉"]):
                vehicle_status["ac"]["status"] = "关闭"
                result.update({
                    "success": True,
                    "message": "空调已关闭",
                    "action": "ac_off",
                    "status_changes": {"ac": vehicle_status["ac"]},
                    "ui_updates": {"ac_indicator": "off", "highlight_card": "ac"}
                })
            elif any(keyword in text for keyword in ["温度", "度", "溫度", "調温", "调温", "调节", "調節", "条结"]):
                # 提取温度数字
                import re
                temp_match = re.search(r'(\d+)', text)
                if temp_match:
                    temp = int(temp_match.group(1))
                    if 16 <= temp <= 30:
                        vehicle_status["ac"]["temperature"] = temp
                        result.update({
                            "success": True,
                            "message": f"空调温度已调至{temp}度",
                            "action": "ac_temp",
                            "status_changes": {"ac": vehicle_status["ac"]},
                            "ui_updates": {"ac_temp": temp, "highlight_card": "ac"}
                        })
        
        # 音乐控制 - 支持繁简体
        elif any(keyword in text for keyword in ["音乐", "歌曲", "播放", "音樂", "歌曲", "播放", "音响", "音響", "媒体", "媒體"]):
            if any(keyword in text for keyword in ["播放", "开始", "放", "播放", "開始", "放", "启动", "啟動", "打开", "打開"]):
                vehicle_status["music"]["status"] = "播放"
                result.update({
                    "success": True,
                    "message": "音乐播放已开始",
                    "action": "music_play",
                    "status_changes": {"music": vehicle_status["music"]},
                    "ui_updates": {"music_indicator": "on", "highlight_card": "music"}
                })
            elif any(keyword in text for keyword in ["暂停", "停止", "停", "暫停", "停止", "停", "关闭", "關閉"]):
                vehicle_status["music"]["status"] = "暂停"
                result.update({
                    "success": True,
                    "message": "音乐已暂停",
                    "action": "music_pause",
                    "status_changes": {"music": vehicle_status["music"]},
                    "ui_updates": {"music_indicator": "off", "highlight_card": "music"}
                })
            elif any(keyword in text for keyword in ["音量", "音量", "声音", "聲音", "大小", "大小"]):
                import re
                volume_match = re.search(r'(\d+)', text)
                if volume_match:
                    volume = int(volume_match.group(1))
                    if 0 <= volume <= 100:
                        vehicle_status["music"]["volume"] = volume
                        result.update({
                            "success": True,
                            "message": f"音量已调至{volume}%",
                            "action": "music_volume",
                            "status_changes": {"music": vehicle_status["music"]},
                            "ui_updates": {"music_volume": volume, "highlight_card": "music"}
                        })
        
        # 导航控制 - 支持繁简体
        elif any(keyword in text for keyword in ["导航", "路线", "地图", "導航", "路線", "地圖", "gps", "GPS","到航","到行"]):
            if any(keyword in text for keyword in ["打开", "开启", "开始", "打開", "開啟", "開始", "启动", "啟動"]):
                vehicle_status["navigation"]["status"] = "开启"
                result.update({
                    "success": True,
                    "message": "导航已开启",
                    "action": "nav_on",
                    "status_changes": {"navigation": vehicle_status["navigation"]},
                    "ui_updates": {"nav_indicator": "on", "highlight_card": "navigation"}
                })
            elif any(keyword in text for keyword in ["关闭", "关", "停止", "關閉", "關", "停止", "结束", "結束"]):
                vehicle_status["navigation"]["status"] = "关闭"
                result.update({
                    "success": True,
                    "message": "导航已关闭",
                    "action": "nav_off",
                    "status_changes": {"navigation": vehicle_status["navigation"]},
                    "ui_updates": {"nav_indicator": "off", "highlight_card": "navigation"}
                })
            elif any(keyword in text for keyword in ["到", "去", "到", "去", "前往", "前往"]):
                # 提取目的地
                destination = text.split("到")[-1].split("去")[-1].strip()
                if destination:
                    vehicle_status["navigation"]["destination"] = destination
                    vehicle_status["navigation"]["status"] = "开启"
                    result.update({
                        "success": True,
                        "message": f"正在导航至{destination}",
                        "action": "nav_destination",
                        "status_changes": {"navigation": vehicle_status["navigation"]},
                        "ui_updates": {"nav_indicator": "on", "nav_destination": destination, "highlight_card": "navigation"}
                    })
        
        # 未识别的指令
        else:
            result.update({
                "success": False,
                "message": f"抱歉，我无法理解指令：{text}。请尝试说'打开空调'、'播放音乐'等指令",
                "action": "unknown"
            })
            
    except Exception as e:
        result.update({
            "success": False,
            "message": f"指令处理出错：{str(e)}",
            "action": "error"
        })
    
    return result

def wait_for_q():
    try:
        print("按下 'q' 键退出程序...")
        keyboard.wait('q')  # 阻塞直到按下 'q'
        print("检测到退出指令，退出中...")
        stop_event.set()
        # 修改：不需要停止自动运行的语音识别，因为现在是按需的
        # if system and hasattr(system, 'voice_recognizer'):
        #     system.voice_recognizer.stop()
        os._exit(0)
    except Exception as e:
        print("[异常] wait_for_q:", e)
        traceback.print_exc()

# 修改：启动线程时不包含自动语音识别
def start_threads():
    threads = [
        threading.Thread(target=capture_frame),
        threading.Thread(target=handle_face_recognition),
        threading.Thread(target=handle_gesture_recognition),
        # 移除自动启动的语音识别线程
        # threading.Thread(target=handle_voice_recognition),
        threading.Thread(target=handle_voice_recognition_on_demand),  # 改为按需的语音识别
        threading.Thread(target=wait_for_q)
    ]
    for thread in threads:
        thread.start()
        print(f"[主线程] 启动线程")
    for thread in threads:
        thread.join()
        print(f"[主线程] 线程已结束：{thread.name}")


# 实时输出路由
@app.route('/stream')
def stream():
    def generate():
        while True:
            with output_condition:
                if output_queue:
                    data = output_queue.popleft()
                    # 格式化输出数据
                    formatted_data = {
                        "timestamp": data.get("timestamp", time.time()),
                        "type": data.get("type", "system"),
                        "content": data.get("content", str(data)),
                        "user": data.get("user", "system")
                    }
                    yield f"data: {json.dumps(formatted_data, ensure_ascii=False)}\n\n"
                else:
                    output_condition.wait(timeout=1)
            time.sleep(0.1)
    
    return Response(generate(), mimetype='text/event-stream')

# 启动界面
@app.route('/')
def home():
    return render_template('login.html')

# 登陆注册
@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        role = data.get('role')

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username=? AND password=? AND role=?", (username, password, role))
        user = cursor.fetchone()
        conn.close()

        if user:
            session['username'] = username
            session['role'] = role
            if user[3] == 'admin':  # 假设角色在用户表中的第4个字段
                return jsonify({"success": True, "redirect_url": "/log"})
            else:
                return jsonify({"success": True, "redirect_url": "/index"})
        else:
            return jsonify({"success": False, "message": "用户名、密码或身份错误"})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form['username']
            password = request.form['password']
            role = request.form['role']

            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()

            # 检查用户名是否存在
            cursor.execute("SELECT * FROM users WHERE username=?", (username,))
            if cursor.fetchone():
                conn.close()
                return render_template('register.html', error='用户名已存在，请更换用户名')

            # 插入新用户
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                           (username, password, role))
            conn.commit()
            conn.close()
            return redirect('/')
        except Exception as e:
            return f"注册失败：{str(e)}"
    else:
        return render_template('register.html')
# 管理员路由
@app.route('/log')
def load_log():
    return render_template('log.html')
# 主页路由（原有的index.html）
@app.route('/index')
def index():
    global system
    if 'username' not in session:
        return redirect('/')
    if not threads_started.is_set():
        threads_started.set()  # 设置标志，避免重复启动
        try:
            # 修改：初始化系统但不自动启动语音识别
            system = DrivingSystem(output_queue, output_condition, username=session['username'], role=session['role'])
            print("✅ DrivingSystem初始化完成，语音识别设置为按需模式")
        except Exception as e:
            print("[初始化 DrivingSystem 异常]", e)
            traceback.print_exc()
        threading.Thread(target=start_threads).start()
    return render_template('index.html', username=session['username'], role=session['role'])

# 车载面板界面
@app.route('/vehicle')
def vehicle_panel():
    """车载面板界面"""
    if 'username' not in session:
        return redirect('/')
    
    global system
    if not threads_started.is_set():
        threads_started.set()
        try:
            # 修改：初始化系统但不自动启动语音识别
            system = DrivingSystem(output_queue, output_condition, username=session['username'], role=session['role'])
            print("✅ DrivingSystem初始化完成，语音识别设置为按需模式")
        except Exception as e:
            print("[初始化 DrivingSystem 异常]", e)
            traceback.print_exc()
        threading.Thread(target=start_threads).start()
    
    return render_template('vehicle_panel.html', username=session['username'], role=session['role'])

@app.route('/api/voice_recognition', methods=['POST'])
def voice_recognition():
    """语音识别API - 使用现有的Whisper系统（按需调用）"""
    global system
    if 'username' not in session:
        return jsonify({"status": "error", "message": "用户未登录"})
    
    try:
        # 获取音频数据
        if 'audio' in request.files:
            audio_file = request.files['audio']
            audio_data = audio_file.read()
        else:
            data = request.get_json()
            audio_base64 = data.get('audio', '')
            if not audio_base64:
                return jsonify({"status": "error", "message": "没有音频数据"})
            audio_data = base64.b64decode(audio_base64.split(',')[1] if ',' in audio_base64 else audio_base64)
        
        print(f"[Web语音识别] 开始处理音频，大小: {len(audio_data)} bytes")
        
        # 生成文件名（与现有系统格式一致）
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        audio_filename = f"web_record_{timestamp}.wav"
        
        # 保存到现有系统的路径
        audio_save_path = f"./reco/whis/test/{audio_filename}"
        
        # 确保目录存在
        os.makedirs(os.path.dirname(audio_save_path), exist_ok=True)
        
        try:
            # 使用pydub转换音频格式（与现有系统兼容）
            
            # 先保存原始数据到临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_file:
                temp_file.write(audio_data)
                temp_webm_path = temp_file.name
            
            print(f"[Web语音识别] 转换音频格式...")
            
            # 读取并转换音频
            try:
                # 尝试不同的音频格式
                audio_segment = AudioSegment.from_file(temp_webm_path)
            except Exception as e:
                print(f"[Web语音识别] 尝试webm格式: {e}")
                try:
                    audio_segment = AudioSegment.from_file(temp_webm_path, format="webm")
                except Exception as e2:
                    print(f"[Web语音识别] 尝试ogg格式: {e2}")
                    audio_segment = AudioSegment.from_file(temp_webm_path, format="ogg")
            
            # 转换为与现有系统兼容的格式（16kHz, 单声道）
            audio_segment = audio_segment.set_frame_rate(16000).set_channels(1)
            
            # 保存到现有系统路径
            audio_segment.export(audio_save_path, format="wav")
            print(f"[Web语音识别] 音频已保存: {audio_save_path}")
            print(f"[Web语音识别] 音频时长: {len(audio_segment)/1000:.2f}秒")
            
            # 清理临时文件
            os.unlink(temp_webm_path)
            
            # 创建结果容器
            recognition_result = {
                "text": None, 
                "processed": False, 
                "error": None
            }
            
            # 修改：直接使用Whisper进行识别，不依赖自动运行的语音识别系统
            try:
                print(f"[Web语音识别] 使用Whisper按需识别...")
                
                # 检查是否已有模型实例，或者加载新的
                if system and hasattr(system, 'voice_recognizer') and hasattr(system.voice_recognizer, 'model'):
                    model = system.voice_recognizer.model
                    print(f"[Web语音识别] 使用现有Whisper模型")
                else:
                    print(f"[Web语音识别] 加载Whisper模型...")
                    model = whisper.load_model("base")
                
                result = model.transcribe(audio_save_path, language="zh")
                text = result["text"].strip()
                print(f"[Web语音识别] Whisper识别结果: '{text}'")
                recognition_result["text"] = text
                recognition_result["processed"] = True
                
            except Exception as e:
                print(f"[Web语音识别] Whisper识别失败: {e}")
                recognition_result["error"] = str(e)
                recognition_result["processed"] = True
            
            # 处理识别结果
            if recognition_result["error"]:
                print(f"[Web语音识别] 处理出错: {recognition_result['error']}")
                return jsonify({
                    "status": "error", 
                    "message": f"语音识别失败: {recognition_result['error']}"
                })
            
            text = recognition_result["text"]
            if text:
                print(f"[Web语音识别] 最终识别结果: '{text}'")
                
                # 解析语音指令
                command_result = parse_voice_command(text)
                
                # 添加到输出队列
                with output_condition:
                    output_queue.append({
                        "timestamp": time.time(),
                        "type": "voice_recognition",
                        "content": f"Web语音识别: {text}",
                        "user": session['username'],
                        "command_result": command_result
                    })
                    output_condition.notify_all()

                insert_log(system.username, system.role, "语音", text)
                
                return jsonify({
                    "status": "success", 
                    "text": text,
                    "message": f"识别成功: {text}",
                    "command_result": command_result
                })
            else:
                print(f"[Web语音识别] 识别结果为空")
                return jsonify({
                    "status": "error", 
                    "message": "语音识别失败，请确保说话清晰"
                })
                
        except Exception as e:
            print(f"[Web语音识别] 音频处理异常: {e}")
            traceback.print_exc()
            return jsonify({
                "status": "error", 
                "message": f"音频处理失败: {str(e)}"
            })
        finally:
            # 清理保存的音频文件（可选，你可能想保留用于调试）
            try:
                if os.path.exists(audio_save_path):
                    # os.unlink(audio_save_path)  # 取消注释这行来删除文件
                    print(f"[Web语音识别] 音频文件保留: {audio_save_path}")
            except:
                pass
                
    except Exception as e:
        print(f"[Web语音识别] API异常: {e}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)})
    
# 语音指令测试API
@app.route('/api/test_voice', methods=['POST'])
def test_voice():
    """测试语音指令API - 用于车载面板和测试面板（按需调用）"""
    global system
    if 'username' not in session:
        return jsonify({"status": "error", "message": "用户未登录"})
    
    try:
        data = request.get_json()
        voice_text = data.get('text', '')
        
        if voice_text:
            # 解析语音指令
            command_result = parse_voice_command(voice_text)
            
            # 添加到输出队列用于实时显示
            with output_condition:
                output_queue.append({
                    "timestamp": time.time(),
                    "type": "voice_command",
                    "content": f"语音指令: {voice_text}",
                    "user": session['username'],
                    "command_result": command_result
                })
                output_condition.notify_all()
            
            # 修改：不依赖自动运行的语音识别系统
            # 这里可以添加其他处理逻辑，但不需要调用自动运行的语音识别
            print(f"[测试语音指令] 处理指令: {voice_text}")
            
            return jsonify({
                "status": "success", 
                "message": command_result["message"],
                "command_result": command_result
            })
        else:
            return jsonify({"status": "error", "message": "无效的语音文本"})
            
    except Exception as e:
        print(f"[API异常] test_voice: {e}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)})

# 获取当前车辆状态API
@app.route('/api/vehicle_status')
def get_vehicle_status():
    """获取当前车辆状态"""
    global system
    if 'username' not in session:
        return jsonify({"status": "error", "message": "用户未登录"})
    
    try:
        if system and hasattr(system, 'vehicle_state'):
            return jsonify({
                "status": "success",
                "vehicle_state": system.vehicle_state,
                "user": {
                    "username": session['username'],
                    "role": session['role']
                }
            })
        else:
            return jsonify({
                "status": "error", 
                "message": "系统未初始化",
                "user": {
                    "username": session['username'],
                    "role": session['role']
                }
            })
    except Exception as e:
        print(f"[API异常] get_vehicle_status: {e}")
        return jsonify({"status": "error", "message": str(e)})

# 健康检查API
@app.route('/api/health')
def health_check():
    """系统健康检查"""
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "system_initialized": system is not None,
        "threads_started": threads_started.is_set(),
        "logged_in": 'username' in session,
        "user": session.get('username', 'anonymous') if 'username' in session else None,
        "voice_recognition_mode": "on_demand"  # 新增：标识语音识别为按需模式
    })

# 退出登录
@app.route('/logout')
def logout():
    """用户退出登录"""
    session.clear()
    return redirect('/')

# 用户信息API
@app.route('/api/user_info')
def get_user_info():
    """获取当前用户信息"""
    if 'username' not in session:
        return jsonify({"status": "error", "message": "用户未登录"})
    
    return jsonify({
        "status": "success",
        "user": {
            "username": session['username'],
            "role": session['role']
        }
    })

if __name__ == '__main__':
    try:
        print("=" * 60)
        print("🚗 车载智能多模态交互系统启动中...")
        print("=" * 60)
        print("📋 可用路由：")
        print("   🏠 登录页面: http://localhost:5000/")
        print("   📝 注册页面: http://localhost:5000/register")
        print("=" * 60)
        print("💡 提示：")
        print("   - 首次访问需要登录或注册")
        print("   - 车载面板提供完整的车载体验")
        print("   - 语音识别已设置为按需模式，点击录音按钮后才开始识别")
        print("=" * 60)
        
        app.run(debug=True, threaded=True, host='0.0.0.0', port=5000, use_reloader=False)
    except KeyboardInterrupt:
        print("检测到 Ctrl+C，退出中...")
        stop_event.set()
        # 修改：不需要停止自动运行的语音识别
        # if system:
        #     system.voice_recognizer.stop()
    except Exception as e:
        print("主线程异常：", e)
        traceback.print_exc()