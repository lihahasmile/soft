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
# 导入日志蓝图
from logs.log import log_bp

app = Flask(__name__)
# python -c "import secrets; print(secrets.token_hex(32))"
app.secret_key = '15d3e837bbe935321c7ee7cd00f6fd47058e5b74d5920ee2420cb7d937e5fc57'

# 注册蓝图
app.register_blueprint(log_bp, url_prefix='/logs')

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

def handle_voice_recognition():
    try:
        print("启动语音识别")
        system.voice_recognizer.start()
        while not stop_event.is_set():
            time.sleep(0.1)
    except Exception as e:
        print("[异常] handle_voice_recognition:", e)
        traceback.print_exc()

def wait_for_q():
    try:
        print("按下 'q' 键退出程序...")
        keyboard.wait('q')  # 阻塞直到按下 'q'
        print("检测到退出指令，退出中...")
        stop_event.set()
        system.voice_recognizer.stop()
        os._exit(0)
    except Exception as e:
        print("[异常] wait_for_q:", e)
        traceback.print_exc()

# 启动所有线程
def start_threads():
    threads = [
        threading.Thread(target=capture_frame),
        threading.Thread(target=handle_face_recognition),
        threading.Thread(target=handle_gesture_recognition),
        threading.Thread(target=handle_voice_recognition),
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
    print("stream 路由已被访问")
    return system.get_stream()

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

# 主页路由
@app.route('/index')
def index():
    # return render_template('index.html')
    global system
    if 'username' not in session:
        return redirect('/')
    if not threads_started.is_set():
        threads_started.set()  # 设置标志，避免重复启动
        system = DrivingSystem(output_queue, output_condition,username=session['username'], role=session['role'])
        threading.Thread(target=start_threads).start()
    return render_template('index.html', username=session['username'], role=session['role'])

if __name__ == '__main__':
    try:
        # start_thread = threading.Thread(target=start_threads)
        # start_thread.start()
        print("[主线程] Flask 启动中...")
        app.run(debug=True, threaded=True, host='0.0.0.0', port=5000, use_reloader=False)
    except KeyboardInterrupt:
        print("检测到 Ctrl+C，退出中...")
        stop_event.set()
        system.voice_recognizer.stop()
    except Exception as e:
        print("主线程异常：", e)
        traceback.print_exc()
