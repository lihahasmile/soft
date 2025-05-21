import cv2
import dlib
import numpy as np
from PIL import ImageFont, ImageDraw, Image
import time
from collections import deque
import threading

class FaceRecognizer:
    def __init__(self, font_path="simhei.ttf", model_path="shape_predictor_68_face_landmarks.dat", on_status_change=None):
        # 人脸检测器与关键点预测器
        self.detector = dlib.get_frontal_face_detector()
        self.predictor = dlib.shape_predictor(model_path)
        self.font_path = font_path

        # 注视前方时间记录 & 注意力警告标志
        self.pitch_history = deque(maxlen=10)
        self.yaw_history = deque(maxlen=10)
        self.last_forward_time = time.time()
        self.attention_warning = False

        # 保存头部姿态历史数据（用于检测动态动作）
        self.pitch_history = deque(maxlen=10)
        self.yaw_history = deque(maxlen=10)

        # 3D 参考人脸特征点（鼻尖、下巴、眼角、嘴角）
        self.model_points = np.array([
            (0.0, 0.0, 0.0),
            (0.0, -330.0, -65.0),
            (-225.0, 170.0, -135.0),
            (225.0, 170.0, -135.0),
            (-150.0, -150.0, -125.0),
            (150.0, -150.0, -125.0)
        ])

        self.statue = "未检测"  # 新增：存储当前状态
        self.on_status_change = on_status_change
        self.statue_lock = threading.Lock()  # 线程锁保护状态读写

        # self.running = False

    def draw_chinese_text(self, frame, text, position, color=(255, 0, 0), font_size=30):
        # 在图像上绘制中文文本
        img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)
        font = ImageFont.truetype(self.font_path, font_size)
        draw.text(position, text, font=font, fill=color)
        return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

    def get_camera_matrix(self, size):
        # 构造摄像头内参矩阵
        focal_length = size[1]
        center = (size[1] / 2, size[0] / 2)
        return np.array([[focal_length, 0, center[0]],
                         [0, focal_length, center[1]],
                         [0, 0, 1]], dtype="double")

    def get_head_pose(self, shape, size):
        # 从关键点计算姿态估计
        image_points = np.array([
            (shape.part(30).x, shape.part(30).y),  # 鼻尖
            (shape.part(8).x, shape.part(8).y),    # 下巴
            (shape.part(36).x, shape.part(36).y),  # 左眼角
            (shape.part(45).x, shape.part(45).y),  # 右眼角
            (shape.part(48).x, shape.part(48).y),  # 左嘴角
            (shape.part(54).x, shape.part(54).y)   # 右嘴角
        ], dtype="double")

        cam_matrix = self.get_camera_matrix(size)
        dist_coeffs = np.zeros((4, 1))  # 默认无畸变
        success, rvec, tvec = cv2.solvePnP(self.model_points, image_points, cam_matrix, dist_coeffs)
        return rvec, tvec, cam_matrix

    def get_euler_angles(self, rvec, tvec, cam_matrix):
        """将姿态估计的旋转向量转为欧拉角（pitch, yaw, roll）"""
        rmat, _ = cv2.Rodrigues(rvec)    # 旋转向量 -> 旋转矩阵
        proj = np.hstack((rmat, tvec))   # 构建投影矩阵：3x4
        _, _, _, _, _, _, angles = cv2.decomposeProjectionMatrix(proj)
        pitch, yaw, roll = angles[0][0], angles[1][0], angles[2][0]

        # 修正角度范围：将 pitch, yaw 保持在 [-90, 90]，roll 在 [-90, 90]
        if pitch < -90: pitch += 180
        elif pitch > 90: pitch -= 180
        if yaw < -90: yaw += 180
        elif yaw > 90: yaw -= 180
        if roll > 90: roll -= 180
        elif roll < -90: roll += 180

        return pitch, yaw, roll

    def detect_dynamic_motion(self):
        # 动作检测（点头、摇头）
        if len(self.pitch_history) < 5:
            return None
        pitch_range = max(self.pitch_history) - min(self.pitch_history)
        yaw_range = max(self.yaw_history) - min(self.yaw_history)

        if pitch_range > 5:
            return "点头确认"
        elif yaw_range > 20:
            return "摇头拒绝"
        return None

    def detect_static_pose(self):
        # 姿态检测（低头、静止转头）
        if len(self.pitch_history) < 5:
            return None
        pitch_mean = np.mean(self.pitch_history)
        pitch_std = np.std(self.pitch_history)
        yaw_mean = np.mean(self.yaw_history)
        yaw_std = np.std(self.yaw_history)

        if pitch_mean > 5 and pitch_std < 5:
            return "低头看手机"
        elif yaw_mean > 20 and yaw_std < 5:
            return "向右说话"
        elif yaw_mean < -20 and yaw_std < 5:
            return "向左说话"
        return None

    # 线程安全状态写入
    def set_statue(self, new_status):
        with self.statue_lock:
            if new_status != self.statue:
                self.statue = new_status
                # ✅ 状态变化触发回调
                if self.on_status_change is not None:
                    self.on_status_change(new_status)

    # 线程安全状态读取
    def get_statue(self):
        with self.statue_lock:
            return self.statue
        
    # def start(self):
    #     """启动识别"""
    #     self.running = True
    #     return True

    def process_frame(self, frame):
        # if not self.running:
        #     return None

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.detector(gray)
        now = time.time()
        state = "未检测到人脸"
        pitch = None
        yaw = None

        for face in faces:
            shape = self.predictor(gray, face)
            rvec, tvec, cam_mtx = self.get_head_pose(shape, frame.shape)
            pitch = None
            yaw = None
            pitch, yaw, _ = self.get_euler_angles(rvec, tvec, cam_mtx)

            # 更新历史数据
            self.pitch_history.append(pitch)
            self.yaw_history.append(yaw)

            # 注视状态判断
            if abs(yaw) < 15 and abs(pitch) < 10:
                self.last_forward_time = now

            # 动态/静态行为检测
            motion = self.detect_dynamic_motion()
            pose = self.detect_static_pose()

            state = "注视前方"
            self.attention_warning = False

            if motion:
                state = motion
            elif pose:
                state = pose
            elif now - self.last_forward_time > 3:
                self.attention_warning = True
                state = "注意力偏离超过3秒"

            # 线程安全地更新状态
            self.set_statue(state)

        # 显示调试信息（可选）
        # frame = self.draw_chinese_text(
        #         frame, f"状态: {state}", (30, 30),
        #         (0, 0, 255) if self.attention_warning else (0, 255, 0), 36
        # )
        # frame = self.draw_chinese_text(
        #     frame, f"Pitch: {pitch:.1f}°, Yaw: {yaw:.1f}°", (30, 80),
        #     (0, 255, 255), 28
        # )

        return frame

    # def stop(self):
    #     """停止面部识别"""
    #     self.running = False