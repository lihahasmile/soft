import cv2
import dlib
import numpy as np
from PIL import ImageFont, ImageDraw, Image
import time
from collections import deque

# 设置字体路径
FONT_PATH = "simhei.ttf"

# 初始化 dlib 模型
detector = dlib.get_frontal_face_detector()
predictor = dlib.shape_predictor("shape_predictor_68_face_landmarks.dat")

# 注意力检测
last_forward_time = time.time()
attention_warning = False

# 姿态历史队列（用于检测点头/摇头）
pitch_history = deque(maxlen=10)
yaw_history = deque(maxlen=10)

# 绘制中文
def draw_chinese_text(frame, text, position, color=(255, 0, 0), font_size=30):
    img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    font = ImageFont.truetype(FONT_PATH, font_size)
    draw.text(position, text, font=font, fill=color)
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

# 相机内参矩阵
def get_camera_matrix(size):
    focal_length = size[1]
    center = (size[1] / 2, size[0] / 2)
    return np.array([[focal_length, 0, center[0]],
                     [0, focal_length, center[1]],
                     [0, 0, 1]], dtype="double")

# 3D人脸模型点
model_points = np.array([
    (0.0, 0.0, 0.0),             
    (0.0, -330.0, -65.0),        
    (-225.0, 170.0, -135.0),     
    (225.0, 170.0, -135.0),      
    (-150.0, -150.0, -125.0),    
    (150.0, -150.0, -125.0)      
])

# 姿态估计
def get_head_pose(shape, size):
    image_points = np.array([
        (shape.part(30).x, shape.part(30).y),
        (shape.part(8).x, shape.part(8).y),
        (shape.part(36).x, shape.part(36).y),
        (shape.part(45).x, shape.part(45).y),
        (shape.part(48).x, shape.part(48).y),
        (shape.part(54).x, shape.part(54).y)
    ], dtype="double")
    cam_matrix = get_camera_matrix(size)
    dist_coeffs = np.zeros((4, 1))
    success, rvec, tvec = cv2.solvePnP(
        model_points, image_points, cam_matrix, dist_coeffs
    )
    return rvec, tvec, cam_matrix

# 欧拉角转换
def get_euler_angles(rvec, tvec, cam_matrix):
    rmat, _ = cv2.Rodrigues(rvec)
    proj = np.hstack((rmat, tvec))
    _, _, _, _, _, _, angles = cv2.decomposeProjectionMatrix(proj)
    pitch = angles[0][0]
    yaw = angles[1][0]
    roll = angles[2][0]

    # 转换为更自然的人体角度坐标系
    if pitch < -90:
        pitch += 180
    elif pitch > 90:
        pitch -= 180

    if yaw < -90:
        yaw += 180
    elif yaw > 90:
        yaw -= 180

    if roll > 90:
        roll -= 180
    elif roll < -90:
        roll += 180

    return pitch, yaw, roll

# 姿态动作识别
def detect_dynamic_motion(pitch_vals, yaw_vals):
    if len(pitch_vals) < 5:
        return None

    pitch_diff = max(pitch_vals) - min(pitch_vals)
    yaw_diff = max(yaw_vals) - min(yaw_vals)

    if pitch_diff > 5:
        return "点头确认"
    if yaw_diff > 20:
        return "摇头拒绝"
    return None

def detect_static_pose(pitch_vals, yaw_vals):
    if len(pitch_vals) < 5:
        return None

    pitch_mean = np.mean(pitch_vals)
    pitch_std = np.std(pitch_vals)
    yaw_mean = np.mean(yaw_vals)
    yaw_std = np.std(yaw_vals)

    # 判断是否低头：持续 pitch 大 + 稳定
    if pitch_mean > 5 and pitch_std < 5:
        return "低头看手机"

    # 判断是否转头（静态向左/右说话）
    if yaw_mean > 20 and yaw_std < 5:
        return "向右说话"
    if yaw_mean < -20 and yaw_std < 5:
        return "向左说话"

    return None


# 打开摄像头
cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    size = frame.shape
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = detector(gray)

    now = time.time()
    state = "未检测到人脸"

    for face in faces:
        shape = predictor(gray, face)
        rvec, tvec, cam_mtx = get_head_pose(shape, size)
        pitch, yaw, roll = get_euler_angles(rvec, tvec, cam_mtx)

        # 保存历史数据
        pitch_history.append(pitch)
        yaw_history.append(yaw)

        # 更新注视时间
        if abs(yaw) < 15 and abs(pitch) < 10:
            last_forward_time = now

        # 姿态动作识别
        motion = detect_dynamic_motion(list(pitch_history), list(yaw_history))
        pose = detect_static_pose(list(pitch_history), list(yaw_history))

        # 默认状态
        state = "注视前方"
        attention_warning = False

        if motion:
            state = motion
        elif pose:
            state = pose
        elif now - last_forward_time > 3:
            attention_warning = True
            state = "注意力偏离超过3秒"
        else:
            state = "注视前方"

        if abs(yaw) < 15 and abs(pitch) < 10:
            last_forward_time = now

        # 显示状态与角度
        frame = draw_chinese_text(frame, f"状态: {state}", (30, 30), (0, 0, 255) if attention_warning else (0, 255, 0), 36)
        frame = draw_chinese_text(frame, f"Pitch: {pitch:.1f}°, Yaw: {yaw:.1f}°", (30, 80), (0, 255, 255), 28)

    cv2.imshow("驾驶员行为识别系统", frame)
    if cv2.waitKey(1) == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
