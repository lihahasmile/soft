import cv2
import mediapipe as mp
import math
import time
from collections import deque

class GestureRecognizer:
    def __init__(self, on_ges_change):
        # 初始化MediaPipe Hands和Drawing工具
        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        self.cap = None
        self.gesture_history = {}
        self.detected_gestures = []

        self.on_ges_change = on_ges_change
        
        # self.running = False
    @staticmethod
    def vector_2d_angle(v1, v2):
        """计算两个二维向量v1和v2之间的夹角（0~180度）"""
        v1_x, v1_y = v1
        v2_x, v2_y = v2
        try:
            dot = v1_x * v2_x + v1_y * v2_y
            norm1 = math.sqrt(v1_x**2 + v1_y**2)
            norm2 = math.sqrt(v2_x**2 + v2_y**2)
            angle_ = math.degrees(math.acos(dot / (norm1 * norm2)))
        except:
            angle_ = 180
        return angle_

    def hand_angle(self, hand_landmarks):
        """计算手指关节的角度列表"""
        angle_list = []
        # 拇指
        angle = self.vector_2d_angle(
            ((hand_landmarks[0][0] - hand_landmarks[2][0]), (hand_landmarks[0][1] - hand_landmarks[2][1])),
            ((hand_landmarks[3][0] - hand_landmarks[4][0]), (hand_landmarks[3][1] - hand_landmarks[4][1]))
        )
        angle_list.append(angle)

        # 食指
        angle = self.vector_2d_angle(
            ((hand_landmarks[0][0] - hand_landmarks[6][0]), (hand_landmarks[0][1] - hand_landmarks[6][1])),
            ((hand_landmarks[7][0] - hand_landmarks[8][0]), (hand_landmarks[7][1] - hand_landmarks[8][1]))
        )
        angle_list.append(angle)

        # 中指
        angle = self.vector_2d_angle(
            ((hand_landmarks[0][0] - hand_landmarks[10][0]), (hand_landmarks[0][1] - hand_landmarks[10][1])),
            ((hand_landmarks[11][0] - hand_landmarks[12][0]), (hand_landmarks[11][1] - hand_landmarks[12][1]))
        )
        angle_list.append(angle)

        # 无名指
        angle = self.vector_2d_angle(
            ((hand_landmarks[0][0] - hand_landmarks[14][0]), (hand_landmarks[0][1] - hand_landmarks[14][1])),
            ((hand_landmarks[15][0] - hand_landmarks[16][0]), (hand_landmarks[15][1] - hand_landmarks[16][1]))
        )
        angle_list.append(angle)

        # 小拇指
        angle = self.vector_2d_angle(
            ((hand_landmarks[0][0] - hand_landmarks[18][0]), (hand_landmarks[0][1] - hand_landmarks[18][1])),
            ((hand_landmarks[19][0] - hand_landmarks[20][0]), (hand_landmarks[19][1] - hand_landmarks[20][1]))
        )
        angle_list.append(angle)

        return angle_list

    def recognize_gesture(self, angle_list, history_x, move_thr=30):
        """手势识别，识别挥手、握拳和竖大拇指"""
        thr_angle = 65  # 手指弯曲的阈值
        thr_angle_s = 50  # 手指伸直的阈值

        # 判断手指状态
        thumb_straight = angle_list[0] < thr_angle_s
        index_straight = angle_list[1] < thr_angle_s
        middle_straight = angle_list[2] < thr_angle_s
        ring_straight = angle_list[3] < thr_angle_s
        pinky_straight = angle_list[4] < thr_angle_s

        # 判断所有手指是否伸直（用于挥手检测）
        is_all_fingers_open = all([index_straight, middle_straight, ring_straight, pinky_straight])

        # 挥手检测（需要所有手指伸直且有水平移动）
        if is_all_fingers_open and len(history_x) >= 2:
            x_diff = abs(history_x[-1] - history_x[-2])
            if x_diff > move_thr:
                return "挥手"

        # 竖大拇指（只有拇指伸直，其他手指弯曲）
        if thumb_straight and not index_straight and not middle_straight and not ring_straight and not pinky_straight:
            return "拇指向上"

        # 握拳（所有手指都弯曲）
        if all(angle > thr_angle for angle in angle_list):
            return "握拳"

        return ""

    # def start(self):
    #     """启动手势识别"""
    #     self.running = True
    #     return True

    def process(self, frame):
        """获取当前手势"""
        # if not self.running:
        #     return None
        
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(frame_rgb)

        self.detected_gestures = []

        if results.multi_hand_landmarks:
            for idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
                # 绘制手部关键点
                self.mp_drawing.draw_landmarks(
                    frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)

                # 提取手部关键点坐标
                hand_local = []
                for lm in hand_landmarks.landmark:
                    x = int(lm.x * frame.shape[1])
                    y = int(lm.y * frame.shape[0])
                    hand_local.append((x, y))

                if hand_local:
                    # 计算手指角度
                    angle_list = self.hand_angle(hand_local)
                    
                    # 更新手的历史x坐标用于挥手判定
                    if idx not in self.gesture_history:
                        self.gesture_history[idx] = deque(maxlen=5)
                    self.gesture_history[idx].append(hand_local[0][0])  # 手腕x坐标
                    
                    # 识别手势
                    gesture_str = self.recognize_gesture(angle_list, self.gesture_history[idx])
                    
                    if gesture_str:
                        self.detected_gestures.append(gesture_str)
                        print("新的手势进行回调")
                        self.on_ges_change(gesture_str)
                        # cv2.putText(frame, gesture_str, 
                        #               (hand_local[0][0], hand_local[0][1] - 30),
                        #               cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)

        return frame
    
    def get_gesture(self):
        return self.detected_gestures

    # def stop(self):
    #     """停止手势识别"""
    #     self.running = False
    