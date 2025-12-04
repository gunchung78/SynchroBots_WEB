# app/hardware/vision_anomaly.py

import os
import io
import cv2
import torch
import torch.nn as nn
from torchvision import transforms
from PIL import Image
import numpy as np

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

AD_THRESHOLDS = {
    "ESP32": 0.045,
    "L298N": 0.045,
    "MB102": 0.060,
}

# ROI (카메라 해상도에 맞게 조절)
ROI_X, ROI_Y = 100, 50
ROI_W, ROI_H = 500, 400

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
# 4. 원샷 검사 함수 (API에서 호출)
# =================================================================
def run_anomaly_inspection_once():
    """
    카메라에서 한 프레임을 캡쳐해서
    - 분류 (ESP32 / L298N / MB102)
    - 해당 클래스의 Anomaly Detection
    을 수행한 뒤 결과 dict를 반환한다.

    return 예시:
    {
        "module_type": "ESP32",
        "conf": 0.99,
        "anomaly_flag": True,   # 불량 여부
        "anomaly_score": 0.053,
        "decision": "REJECT",   # PASS / REJECT
        "image_bytes": b"...",  # JPEG 인코딩
    }
    """
    classifier = _load_classifier()
    if classifier is None:
        raise RuntimeError("Classifier model not loaded")

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        raise RuntimeError("Cannot open camera")

    try:
        ok, frame = cap.read()
    finally:
        cap.release()

    if not ok or frame is None:
        raise RuntimeError("Failed to capture frame")

    # 1) Classification
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(rgb)
    inp = classifier_transform(pil_image).unsqueeze(0).to(DEVICE)

    with torch.no_grad():
        outputs = classifier(inp)
        probs = torch.softmax(outputs, dim=1)
        conf_score, pred_idx = torch.max(probs, 1)

    module_type = CLASS_NAMES[pred_idx.item()]
    conf = float(conf_score.item())

    # 2) Anomaly Detection
    ad_model = _load_ad_model(module_type)
    anomaly_flag = None
    anomaly_score = 0.0

    if ad_model is not None:
        x1, y1 = ROI_X, ROI_Y
        x2, y2 = ROI_X + ROI_W, ROI_Y + ROI_H
        roi = frame[y1:y2, x1:x2]

        if roi.size > 0:
            roi_rgb = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
            ad_pil = Image.fromarray(roi_rgb)
            ad_inp = ad_preprocess(ad_pil).unsqueeze(0).to(DEVICE)

            with torch.no_grad():
                recon = ad_model(ad_inp)
                anomaly_score = float(torch.mean((ad_inp - recon) ** 2).item())

            thr = AD_THRESHOLDS.get(module_type, 0.05)
            anomaly_flag = anomaly_score > thr
        else:
            anomaly_flag = None
            anomaly_score = 0.0
    else:
        anomaly_flag = None
        anomaly_score = 0.0

    decision = "REJECT" if anomaly_flag else "PASS"

    # 3) 전체 프레임을 JPEG로 인코딩 -> DB에 저장용
    ok, buf = cv2.imencode(".jpg", frame)
    image_bytes = buf.tobytes() if ok else None

    return {
        "module_type": module_type,
        "conf": conf,
        "anomaly_flag": anomaly_flag,
        "anomaly_score": anomaly_score,
        "decision": decision,
        "image_bytes": image_bytes,
    }
