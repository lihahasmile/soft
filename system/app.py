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
import tempfile
import os
import whisper
from opencc import OpenCC
from logs.log import log_bp, insert_log
from reco.voice.voice import parse_voice_command, vehicle_status

app = Flask(__name__)
# python -c "import secrets; print(secrets.token_hex(32))"
app.secret_key = '15d3e837bbe935321c7ee7cd00f6fd47058e5b74d5920ee2420cb7d937e5fc57'
app.register_blueprint(log_bp,url_prefix='/logs')
# === 全局共享资源 ===
output_queue = deque()
output_condition = threading.Condition()

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

@app.route('/api/voice_recognition', methods=['POST'])
def voice_recognition():
    """语音识别API - 使用原版tiny.pt模型和处理方式"""
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
        
        # 生成文件名（与原版格式一致）
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        audio_filename = f"web_record_{timestamp}.wav"
        audio_save_path = f"./reco/whis/test/{audio_filename}"
        
        # 确保目录存在
        os.makedirs(os.path.dirname(audio_save_path), exist_ok=True)
        
        # 音频格式转换（保持与原版兼容的格式）
        try:
            # 保存临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_file:
                temp_file.write(audio_data)
                temp_webm_path = temp_file.name
            
            # 转换为与原版相同的格式（16kHz, 单声道）
            audio_segment = AudioSegment.from_file(temp_webm_path)
            audio_segment = audio_segment.set_frame_rate(16000).set_channels(1)
            audio_segment.export(audio_save_path, format="wav")
            
            # 清理临时文件
            os.unlink(temp_webm_path)
            print(f"[Web语音识别] 音频已保存: {audio_save_path}")
            
        except Exception as e:
            print(f"[Web语音识别] 音频转换失败: {e}")
            return jsonify({"status": "error", "message": f"音频格式转换失败: {str(e)}"})
        
        # 🔧 使用原版的处理方式
        try:
            print("正在转录语音...")
            
            # 直接使用原版的模型和参数
            model_path = "./reco/whis/tiny.pt"
            if os.path.exists(model_path):
                model = whisper.load_model(model_path)
                print(f"[Web语音识别] 加载原版tiny.pt模型: {model_path}")
            else:
                model = whisper.load_model("tiny")
                print(f"[Web语音识别] 使用官方tiny模型")
            cc = OpenCC("t2s")
            
            # 🔧 使用与原版完全相同的转录参数
            result = model.transcribe(audio_save_path, language="zh")
            text = cc.convert(result["text"])
            
            print(f"[Web语音识别] 语音内容: {text}")
            
            if text and text.strip():
                # 🔧 使用原版的文本保存方式
                txt_path = os.path.join("./reco/whis/test", f"web_转写_{timestamp}.txt")
                with open(txt_path, "a", encoding="utf-8") as f:
                    f.write(f"[Web语音] {text}\n")
                
                # 🔧 触发原版的回调处理（如果存在）
                if system and hasattr(system, 'voice_recognizer') and system.voice_recognizer.on_transcription:
                    print("触发原版转写回调...")
                    system.voice_recognizer.on_transcription(text)
                
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
                
                print("转录完成\n")
                # 日志写入
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
            print(f"[Web语音识别] 转录异常: {e}")
            traceback.print_exc()
            return jsonify({
                "status": "error", 
                "message": f"语音转录失败: {str(e)}"
            })
        
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

# 下面两个api目前没有调用的

# 获取当前车辆状态API
# @app.route('/api/vehicle_status')
# def get_vehicle_status():
#     """获取当前车辆状态"""
#     global system
#     if 'username' not in session:
#         return jsonify({"status": "error", "message": "用户未登录"})
    
#     try:
#         if system and hasattr(system, 'vehicle_state'):
#             return jsonify({
#                 "status": "success",
#                 "vehicle_state": system.vehicle_state,
#                 "user": {
#                     "username": session['username'],
#                     "role": session['role']
#                 }
#             })
#         else:
#             return jsonify({
#                 "status": "error", 
#                 "message": "系统未初始化",
#                 "user": {
#                     "username": session['username'],
#                     "role": session['role']
#                 }
#             })
#     except Exception as e:
#         print(f"[API异常] get_vehicle_status: {e}")
#         return jsonify({"status": "error", "message": str(e)})

# # 健康检查API
# @app.route('/api/health')
# def health_check():
#     """系统健康检查"""
#     return jsonify({
#         "status": "healthy",
#         "timestamp": time.time(),
#         "system_initialized": system is not None,
#         "threads_started": threads_started.is_set(),
#         "logged_in": 'username' in session,
#         "user": session.get('username', 'anonymous') if 'username' in session else None,
#         "voice_recognition_mode": "on_demand"  # 新增：标识语音识别为按需模式
#     })

# 退出登录
@app.route('/logout')
def logout():
    """用户退出登录"""
    session.clear()
    return redirect('/')

# 用户信息API
# @app.route('/api/user_info')
# def get_user_info():
#     """获取当前用户信息"""
#     if 'username' not in session:
#         return jsonify({"status": "error", "message": "用户未登录"})
    
#     return jsonify({
#         "status": "success",
#         "user": {
#             "username": session['username'],
#             "role": session['role']
#         }
#     })

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