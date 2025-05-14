import cv2
import dlib
import numpy as np
from scipy.spatial import distance as dist
from imutils.video import VideoStream
from imutils import face_utils
import imutils
import time

class FaceRecognizer:
    def __init__(self, predictor_path="shape_predictor_68_face_landmarks.dat"):
        # 初始化面部检测器
        self.detector = dlib.get_frontal_face_detector()
        self.predictor = dlib.shape_predictor(predictor_path)
        
        # 定义面部特征点索引
        (self.lStart, self.lEnd) = face_utils.FACIAL_LANDMARKS_IDXS["left_eye"]
        (self.rStart, self.rEnd) = face_utils.FACIAL_LANDMARKS_IDXS["right_eye"]
        (self.mStart, self.mEnd) = face_utils.FACIAL_LANDMARKS_IDXS["mouth"]
        (self.nStart, self.nEnd) = face_utils.FACIAL_LANDMARKS_IDXS["nose"]
        (self.jStart, self.jEnd) = face_utils.FACIAL_LANDMARKS_IDXS['jaw']
        (self.eyebrowStart, self.eyebrowEnd) = face_utils.FACIAL_LANDMARKS_IDXS['left_eyebrow']
        
        # 初始化状态变量
        self.eye_blinks = 0
        self.mouth_opens = 0
        self.head_shakes = 0
        self.head_nods = 0
        self.head_state = "normal"  # normal/shaking/nodding
        self.vs = None
        
        # 阈值配置
        self.EYE_AR_THRESH = 0.27
        self.EYE_AR_CONSEC_FRAMES = 2
        self.MAR_THRESH = 0.5
        
        # 计数器
        self.eye_counter = 0
        self.mouth_counter = 0
        self.distance_left = 0
        self.distance_right = 0
        self.nod_flag = 0
        self.display = False
        self.running = False
    def start(self, display=False):
        """启动视频流"""
        self.display = display
        self.running = True
        return True


    def eye_aspect_ratio(self, eye):
        """计算眼睛纵横比"""
        A = dist.euclidean(eye[1], eye[5])
        B = dist.euclidean(eye[2], eye[4])
        C = dist.euclidean(eye[0], eye[3])
        return (A + B) / (2.0 * C)

    def mouth_aspect_ratio(self, mouth):
        """计算嘴巴纵横比"""
        A = np.linalg.norm(mouth[2] - mouth[9])
        B = np.linalg.norm(mouth[4] - mouth[7])
        C = np.linalg.norm(mouth[0] - mouth[6])
        return (A + B) / (2.0 * C)

    def _update_head_pose(self, nose, jaw, left_eyebrow):
        """更新头部姿态"""
        # 摇头检测
        face_left1 = dist.euclidean(nose[0], jaw[0])
        face_right1 = dist.euclidean(nose[0], jaw[16])
        face_left2 = dist.euclidean(nose[3], jaw[2])
        face_right2 = dist.euclidean(nose[3], jaw[14])
        
        if face_left1 >= face_right1+10 and face_left2 >= face_right2+10:
            self.distance_left += 1
            self.head_state = "shaking_left"
        elif face_right1 >= face_left1+10 and face_right2 >= face_left2+10:
            self.distance_right += 1
            self.head_state = "shaking_right"
        else:
            self.head_state = "normal"
            
        if self.distance_left != 0 and self.distance_right != 0:
            self.head_shakes += 1
            self.distance_left = 0
            self.distance_right = 0
            self.head_state = "shaking"
        
        # 点头检测
        eyebrow_left = dist.euclidean(left_eyebrow[2], jaw[0])
        eyebrow_right = dist.euclidean(left_eyebrow[2], jaw[16])
        left_right = dist.euclidean(jaw[0], jaw[16])
        
        if eyebrow_left + eyebrow_right <= left_right + 3:
            self.nod_flag += 1
            self.head_state = "nodding_down"
        if self.nod_flag != 0 and eyebrow_left + eyebrow_right >= left_right + 3:
            self.head_nods += 1
            self.nod_flag = 0
            self.head_state = "nodding"

    def get_status(self):
        """获取当前状态"""
        
        return {
            "eye_blinks": self.eye_blinks,
            "mouth_opens": self.mouth_opens,
            "head_shakes": self.head_shakes,
            "head_nods": self.head_nods,
            "headstate": self.head_state
        }

    def update(self, frame):
        """更新检测状态"""
        if not self.running:
            return
            
        frame = imutils.resize(frame, width=600)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        rects = self.detector(gray, 0)
        
        for rect in rects:
            shape = self.predictor(gray, rect)
            shape = face_utils.shape_to_np(shape)
            
            # 提取特征点
            left_eye = shape[self.lStart:self.lEnd]
            right_eye = shape[self.rStart:self.rEnd]
            mouth = shape[self.mStart:self.mEnd]
            nose = shape[self.nStart:self.nEnd]
            jaw = shape[self.jStart:self.jEnd]
            left_eyebrow = shape[self.eyebrowStart:self.eyebrowEnd]
            
            # 计算各项指标
            left_ear = self.eye_aspect_ratio(left_eye)
            right_ear = self.eye_aspect_ratio(right_eye)
            ear = (left_ear + right_ear) / 2.0
            mar = self.mouth_aspect_ratio(mouth)
            
            # 更新眨眼状态
            if ear < self.EYE_AR_THRESH:
                self.eye_counter += 1
            else:
                if self.eye_counter >= self.EYE_AR_CONSEC_FRAMES:
                    self.eye_blinks += 1
                self.eye_counter = 0
                
            # 更新张嘴状态
            if mar > self.MAR_THRESH:
                self.mouth_counter += 1
            else:
                if self.mouth_counter != 0:
                    self.mouth_opens += 1
                self.mouth_counter = 0
                
            # 更新头部姿态
            self._update_head_pose(nose, jaw, left_eyebrow)
            
            # 绘制可视化
            self._draw_landmarks(frame, left_eye, right_eye, mouth, nose, jaw)
            
            # 显示状态信息
            self._display_status(frame)
        
        if self.display:
            cv2.imshow("Face Recognition", frame)
        return frame

    def _draw_landmarks(self, frame, left_eye, right_eye, mouth, nose, jaw):
        """绘制面部特征点"""
        left_eye_hull = cv2.convexHull(left_eye)
        right_eye_hull = cv2.convexHull(right_eye)
        mouth_hull = cv2.convexHull(mouth)
        nose_hull = cv2.convexHull(nose)
        jaw_hull = cv2.convexHull(jaw)
        
        cv2.drawContours(frame, [left_eye_hull], -1, (0, 255, 0), 1)
        cv2.drawContours(frame, [right_eye_hull], -1, (0, 255, 0), 1)
        cv2.drawContours(frame, [mouth_hull], -1, (255, 0, 0), 1)
        cv2.drawContours(frame, [nose_hull], -1, (0, 0, 255), 1)
        cv2.drawContours(frame, [jaw_hull], -1, (0, 0, 255), 1)

    def _display_status(self, frame):
        """显示状态信息"""
        cv2.putText(frame, f"Blinks: {self.eye_blinks}", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(frame, f"Mouth Opens: {self.mouth_opens}", (10, 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(frame, f"Head Shakes: {self.head_shakes}", (10, 90),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(frame, f"Head Nods: {self.head_nods}", (10, 120),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(frame, f"Head State: {self.head_state}", (10, 150),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    def stop(self):
        """停止面部识别"""
        self.running = False
        if self.display:
            cv2.destroyWindow("Face Recognition")