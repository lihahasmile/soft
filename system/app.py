from flask import Flask, render_template, Response, request
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

app = Flask(__name__)

# === 全局共享资源 ===
output_queue = deque()
output_condition = threading.Condition()

system = DrivingSystem(output_queue, output_condition)

# 共享帧和锁
latest_frame = None
frame_lock = threading.Lock()
stop_event = threading.Event()

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

def handle_voice_recognition():
    try:
        print("启动语音识别")
        system.voice_recognizer.start()
        while not stop_event.is_set():
            time.sleep(0.1)
    except Exception as e:
        print("[异常] handle_voice_recognition:", e)

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
    for thread in threads:
        thread.join()

# 主页路由
@app.route('/')
def index():
    return render_template('index.html')

# 实时输出路由
@app.route('/stream')
def stream():
    print("stream 路由已被访问")
    return system.get_stream()

if __name__ == '__main__':
    try:
        start_thread = threading.Thread(target=start_threads)
        start_thread.start()
        app.run(debug=True, threaded=True, host='0.0.0.0', port=5000, use_reloader=False)
    except KeyboardInterrupt:
        print("检测到 Ctrl+C，退出中...")
        stop_event.set()
        system.voice_recognizer.stop()
    except Exception as e:
        print("主线程异常：", e)
        traceback.print_exc()
