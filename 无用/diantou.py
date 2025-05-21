import dlib
import cv2
import numpy as np


class FaceRecognizer:
    def __init__(self, shape_predictor_path):
        self.detector = dlib.get_frontal_face_detector()
        self.predictor = dlib.shape_predictor(shape_predictor_path)
        self.base_nose = None

    def get_EAR(self, eye):
        A = np.linalg.norm(np.array(eye[1]) - np.array(eye[5]))
        B = np.linalg.norm(np.array(eye[2]) - np.array(eye[4]))
        C = np.linalg.norm(np.array(eye[0]) - np.array(eye[3]))
        return (A + B) / (2.0 * C)
    
    def shape_to_np(self, shape):
        return [(shape.part(i).x, shape.part(i).y) for i in range(68)]

    def detect(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.detector(gray, 0)

        for face in faces:
            shape = self.predictor(gray, face)
            shape_np = self.shape_to_np(shape)

            # EAR计算
            left_eye = shape_np[36:42]
            right_eye = shape_np[42:48]
            ear = (self.get_EAR(left_eye) + self.get_EAR(right_eye)) / 2.0
            if ear < 0.21:
                cv2.putText(frame, "Blink", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            # 张嘴判断
            top_lip = shape_np[62]
            bottom_lip = shape_np[66]
            mouth_open = abs(top_lip[1] - bottom_lip[1])
            if mouth_open > 20:
                cv2.putText(frame, "Mouth Open", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            # 点头/摇头
            nose = shape_np[30]
            if self.base_nose is None:
                self.base_nose = nose
            dx = nose[0] - self.base_nose[0]
            dy = nose[1] - self.base_nose[1]

            if dx > 15:
                cv2.putText(frame, "Turn Right", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
            elif dx < -15:
                cv2.putText(frame, "Turn Left", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
            elif dy > 15:
                cv2.putText(frame, "Nod Down", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            elif dy < -15:
                cv2.putText(frame, "Nod Up", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)

        return frame