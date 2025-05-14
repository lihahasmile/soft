import time
import threading
import concurrent.futures
from model import DrivingSystem
import keyboard

system = DrivingSystem()

stop_event = threading.Event()
def handle_gesture_recognition(system):
    # 启动双重识别
    if not system.start_dual_recognition(display=True):
        return
    # 等待直到 stop_event 被设置
    while not stop_event.is_set():
        time.sleep(0.1)
    
    # 收到停止信号，执行清理
    system.stop_dual_recognition()

def handle_voice_recognition(system):
    try:
        print("启动语音识别")
        system.voice_recognizer.start()
        while not stop_event.is_set():
            time.sleep(0.1)
    except Exception as e:
        print("语音识别异常：", e)

def wait_for_q():
    print("按下 q 退出程序...")
    keyboard.wait('q')  
    print("检测到 q，退出中...")
    stop_event.set()
    system.voice_recognizer.stop()

# 使用线程池
with concurrent.futures.ThreadPoolExecutor() as executor:
    futures = [
        executor.submit(handle_gesture_recognition, system),
        executor.submit(handle_voice_recognition, system),
        executor.submit(wait_for_q)
    ]

    # 等待所有线程完成
    concurrent.futures.wait(futures)
    print("所有线程已退出，程序结束。")