# app/hardware/vision_anomaly.py

import os
import cv2
import torch
import torch.nn as nn
from torchvision import transforms
from PIL import Image
import numpy as np
from collections import Counter

# =================================================================
# 1. 공통 설정
# =================================================================
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
MOBILENET_MEAN = [0.485, 0.456, 0.406]
MOBILENET_STD = [0.229, 0.224, 0.225]
CAMERA_INDEX = 1  # 필요하면 0으로 변경

CLASS_NAMES = ["ESP32", "L298N", "MB102"]
NUM_CLASSES = len(CLASS_NAMES)

# 프로젝트 루트 기준으로 경로 잡기
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VISION_DIR = os.path.join(BASE_DIR, "data", "visions")

# 이미지 파일 저장용
LOG_SAVE_DIR = os.path.join(VISION_DIR, "logs", "Anomaly")
os.makedirs(LOG_SAVE_DIR, exist_ok=True)

CLASSIFIER_WEIGHTS_PATH = os.path.join(
    VISION_DIR,
    "1_Object Classification",
    "checkpoint_mobilenetv3_classifier_e5_acc1.0000.pth",
)

AD_MODEL_PATHS = {
    "ESP32": os.path.join(VISION_DIR, "2_Anomaly Detection", "ESP32", "ESP32_anomaly_detector_best_loss.pth"),
    "L298N": os.path.join(VISION_DIR, "2_Anomaly Detection", "L298N", "L298N_anomaly_detector_best_loss.pth"),
    "MB102": os.path.join(VISION_DIR, "2_Anomaly Detection", "MB102", "MB102_anomaly_detector_best_loss.pth"),
}

# ⚠ 실제 값은 나중에 다시 튜닝 가능
AD_THRESHOLDS = {
    "ESP32": 0.055,
    "L298N": 0.045,
    "MB102": 0.060,
}

# ROI (카메라 해상도에 맞게 조절)
ROI_X, ROI_Y = 100, 50
ROI_W, ROI_H = 500, 400

# 평균을 낼 프레임 수
NUM_FRAMES = 10

# =================================================================
# 2. 모델 아키텍처
# =================================================================
def create_classifier_model(num_classes):
    model = torch.hub.load("pytorch/vision:v0.10.0", "mobilenet_v3_small", weights=None)
    in_features = model.classifier[-1].in_features
    model.classifier[-1] = torch.nn.Linear(in_features, num_classes)
    return model


class Autoencoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Conv2d(3, 16, 3, stride=2, padding=1), nn.ReLU(True),
            nn.Conv2d(16, 32, 3, stride=2, padding=1), nn.ReLU(True),
            nn.Conv2d(32, 64, 3, stride=2, padding=1), nn.ReLU(True),
            nn.Conv2d(64, 128, 3, stride=2, padding=1), nn.ReLU(True),
        )
        self.decoder = nn.Sequential(
            nn.ConvTranspose2d(128, 64, 3, stride=2, padding=1, output_padding=1), nn.ReLU(True),
            nn.ConvTranspose2d(64, 32, 3, stride=2, padding=1, output_padding=1), nn.ReLU(True),
            nn.ConvTranspose2d(32, 16, 3, stride=2, padding=1, output_padding=1), nn.ReLU(True),
            nn.ConvTranspose2d(16, 3, 3, stride=2, padding=1, output_padding=1),
        )

    def forward(self, x):
        return self.decoder(self.encoder(x))

# =================================================================
# 3. 전역 모델 캐시
# =================================================================
_classifier = None
_ad_model_cache = {}

classifier_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=MOBILENET_MEAN, std=MOBILENET_STD),
])

ad_preprocess = transforms.Compose([
    transforms.Resize((128, 128)),
    transforms.ToTensor(),
    transforms.Normalize(mean=MOBILENET_MEAN, std=MOBILENET_STD),
])


def _load_classifier():
    global _classifier
    if _classifier is not None:
        return _classifier

    model = create_classifier_model(NUM_CLASSES)
    if not os.path.exists(CLASSIFIER_WEIGHTS_PATH):
        print(f"[VISION] classifier weights not found: {CLASSIFIER_WEIGHTS_PATH}")
        return None

    state = torch.load(CLASSIFIER_WEIGHTS_PATH, map_location=DEVICE)
    model.load_state_dict(state)
    model.to(DEVICE)
    model.eval()
    _classifier = model
    print(f"[VISION] classifier loaded: {CLASSIFIER_WEIGHTS_PATH}")
    return _classifier


def _load_ad_model(class_name: str):
    if class_name in _ad_model_cache:
        return _ad_model_cache[class_name]

    path = AD_MODEL_PATHS.get(class_name)
    if not path or not os.path.exists(path):
        print(f"[VISION] AD model not found for {class_name}: {path}")
        _ad_model_cache[class_name] = None
        return None

    model = Autoencoder().to(DEVICE)
    state = torch.load(path, map_location=DEVICE)
    model.load_state_dict(state)
    model.eval()
    _ad_model_cache[class_name] = model
    print(f"[VISION] AD model loaded for {class_name}: {path}")
    return model

# =================================================================
# 4. 10프레임 기반 검사 함수 (API에서 호출)
# =================================================================
def run_anomaly_inspection_once():
    """
    카메라에서 최대 NUM_FRAMES(기본 10) 프레임을 캡쳐해서

    1) 각 프레임마다 Classification 실행
       - CLASS_NAMES 중 하나로 분류
       - confidence 리스트에 누적

    2) 최빈값 class를 최종 module_type 으로 선택
       - classification_confidence = 모든 프레임의 conf 평균

    3) 선택된 module_type 전용 AD 모델 로드 후
       - 저장해둔 모든 프레임의 ROI에 대해 anomaly score 계산
       - anomaly_score = 모든 프레임의 score 평균
       - anomaly_flag = (anomaly_score > THRESHOLD)

    4) 마지막 프레임을 JPEG로 인코딩해서 image_bytes 로 반환

    return 예시:
    {
        "module_type": "ESP32",
        "classification_confidence": 0.97,
        "anomaly_flag": True,        # 불량 여부
        "anomaly_score": 0.053,
        "decision": "REJECT",        # PASS / REJECT
        "image_bytes": b"...",       # JPEG 인코딩 (마지막 프레임)
    }
    """
    classifier = _load_classifier()
    if classifier is None:
        raise RuntimeError("Classifier model not loaded")

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        raise RuntimeError("Cannot open camera")

    frames = []

    # -----------------------------
    # 1) 프레임 캡쳐 (최대 NUM_FRAMES)
    # -----------------------------
    try:
        for _ in range(NUM_FRAMES):
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            frames.append(frame.copy())
    finally:
        cap.release()

    if not frames:
        raise RuntimeError("Failed to capture any frame")

    # -----------------------------
    # 2) Classification - 모든 프레임
    # -----------------------------
    cls_scores = []
    cls_preds = []

    with torch.no_grad():
        for frame in frames:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb)
            inp = classifier_transform(pil_image).unsqueeze(0).to(DEVICE)

            outputs = classifier(inp)
            probs = torch.softmax(outputs, dim=1)
            conf_score, pred_idx = torch.max(probs, 1)

            cls_scores.append(float(conf_score.item()))
            cls_preds.append(int(pred_idx.item()))

    # 최빈값 class 선택
    count = Counter(cls_preds)
    most_common_idx, _ = count.most_common(1)[0]
    module_type = CLASS_NAMES[most_common_idx]

    # 평균 confidence
    classification_confidence = float(sum(cls_scores) / len(cls_scores))

    # -----------------------------
    # 3) Anomaly Detection - 선택된 module_type 기준
    # -----------------------------
    ad_model = _load_ad_model(module_type)
    anomaly_flag = None
    anomaly_score = 0.0

    if ad_model is not None:
        x1, y1 = ROI_X, ROI_Y
        x2, y2 = ROI_X + ROI_W, ROI_Y + ROI_H

        ad_scores = []

        with torch.no_grad():
            for frame in frames:
                roi = frame[y1:y2, x1:x2]
                if roi.size == 0:
                    continue

                roi_rgb = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
                ad_pil = Image.fromarray(roi_rgb)
                ad_inp = ad_preprocess(ad_pil).unsqueeze(0).to(DEVICE)

                recon = ad_model(ad_inp)
                loss = torch.mean((ad_inp - recon) ** 2).item()
                ad_scores.append(float(loss))

        if ad_scores:
            anomaly_score = float(sum(ad_scores) / len(ad_scores))
            thr = AD_THRESHOLDS.get(module_type, 0.05)
            anomaly_flag = anomaly_score > thr
        else:
            anomaly_score = 0.0
            anomaly_flag = None
    else:
        anomaly_score = 0.0
        anomaly_flag = None

    # -----------------------------
    # 4) 최종 decision 및 이미지 인코딩
    # -----------------------------
    decision = "REJECT" if anomaly_flag else "PASS"

    last_frame = frames[-1]
    ok, buf = cv2.imencode(".jpg", last_frame)
    image_bytes = buf.tobytes() if ok else None

    import time

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{module_type}_{timestamp}.jpg"
    save_path = os.path.join(LOG_SAVE_DIR, filename)

    os.makedirs(LOG_SAVE_DIR, exist_ok=True)

    # OpenCV는 메모리 버퍼로만 JPEG 인코딩
    ok, buf = cv2.imencode(".jpg", last_frame)
    if not ok:
        raise RuntimeError("imencode('.jpg') failed")

    # 파일 쓰기는 파이썬이 담당 (유니코드 경로 잘 지원)
    with open(save_path, "wb") as f:
        f.write(buf.tobytes())

    print("[SAVE] anomaly image saved:", save_path)

    return {
        "module_type": module_type,
        "classification_confidence": classification_confidence,
        "anomaly_flag": anomaly_flag,
        "anomaly_score": anomaly_score,
        "decision": decision,
        "image_bytes": image_bytes,
        "image_path": save_path,
    }
