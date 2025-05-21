import time
import threading
import concurrent.futures
from model import DrivingSystem
import keyboard
import cv2

system = DrivingSystem()

# 共享帧和锁
latest_frame = None
frame_lock = threading.Lock()
stop_event = threading.Event()
def capture_frame():
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

        # 显示图像窗口
        cv2.imshow("Camera", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):  # 可以用来辅助退出
            stop_event.set()
            break

        time.sleep(0.01)

    cap.release()
    cv2.destroyAllWindows()
    print("摄像头释放")

def handle_face_recognition():
    print("启动面部识别")
    while not stop_event.is_set():
        with frame_lock:
            if latest_frame is None:
                continue
            frame_copy = latest_frame.copy()
        system.face_recognizer.process_frame(frame_copy)
        time.sleep(0.05)

def handle_gesture_recognition():
    print("启动手势识别")
    while not stop_event.is_set():
        with frame_lock:
            if latest_frame is None:
                continue
            frame_copy = latest_frame.copy()
        system.gesture_recognizer.process(frame_copy)
        time.sleep(0.05)


def handle_voice_recognition():
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
        executor.submit(capture_frame),
        executor.submit(handle_face_recognition),
        executor.submit(handle_gesture_recognition),
        executor.submit(handle_voice_recognition),
        executor.submit(wait_for_q)
    ]

    # 等待所有线程完成
    concurrent.futures.wait(futures)
    print("所有线程已退出，程序结束。")