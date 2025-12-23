# app/hardware/vision_anomaly.py

import os
import cv2
import time
import numpy as np
from PIL import Image
from collections import Counter

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import models, transforms

# =================================================================
# 1. 공통 설정 (기존 구조 유지)
# =================================================================
DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
MOBILENET_MEAN = [0.485, 0.456, 0.406]
MOBILENET_STD = [0.229, 0.224, 0.225]
CAMERA_INDEX = 2  # 필요하면 0으로 변경

CLASS_NAMES = ["ESP32", "L298N", "MB102"]
NUM_CLASSES = len(CLASS_NAMES)

# 프로젝트 루트 기준으로 경로 잡기
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VISION_DIR = os.path.join(BASE_DIR, "data", "visions")

# DB에 넣을 상대경로 (프로젝트 루트 기준)
LOG_REL_DIR = os.path.join("data", "visions", "logs", "Anomaly")
LOG_SAVE_DIR = os.path.join(BASE_DIR, LOG_REL_DIR)
os.makedirs(LOG_SAVE_DIR, exist_ok=True)

# =================================================================
# 2. (고도화 로직) 모델/가중치 경로
# - 사용자가 "기존 파일과 동일 위치에 넣어놨다"는 전제 하에
#   프로젝트의 VISION_DIR 기준 상대경로로 구성
# =================================================================
CLASSIFIER_WEIGHTS_PATH = os.path.join(VISION_DIR,"1_Object Classification", "ano_classification.pth")

AD_MODEL_PATHS = {
    "ESP32": os.path.join(VISION_DIR, "2_Anomaly Detection", "ESP32", "ESP32_memory_bank.pt"),
    "L298N": os.path.join(VISION_DIR, "2_Anomaly Detection", "L298N", "L298N_memory_bank.pt"),
    "MB102": os.path.join(VISION_DIR, "2_Anomaly Detection", "MB102", "MB102_memory_bank.pt"),
}

# [고도화 로직의 클래스별 임계값]
AD_THRESHOLDS = {
    "ESP32": 4.5,
    "L298N": 4.5,
    "MB102": 4.5,
}

# ROI (고도화 로직 값 적용)
ROI_X, ROI_Y = 100, 50
ROI_W, ROI_H = 450, 400

# 평균을 낼 프레임 수 (기존 유지)
NUM_FRAMES = 10

# =================================================================
# 3. 전역 모델 캐시 (기존처럼 1회 로딩 후 재사용)
# =================================================================
_inspector = None


class IntegratedInspector:
    """
    고도화 로직:
    - Classification: ResNet50 (fc 교체)
    - AD: ResNet50 backbone + layer1/2/3 hook feature → embedding
    - Memory bank: 클래스별 .pt 로드
    """
    def __init__(self):
        # --- 3.1 Classification 모델 로드 ---
        if not os.path.exists(CLASSIFIER_WEIGHTS_PATH):
            print(f"[VISION] classifier weights not found: {CLASSIFIER_WEIGHTS_PATH}")
            self.classifier = None
        else:
            print(f"[VISION] Loading Classification Model: {CLASSIFIER_WEIGHTS_PATH}")
            self.classifier = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V1)
            num_ftrs = self.classifier.fc.in_features
            self.classifier.fc = nn.Linear(num_ftrs, NUM_CLASSES)
            self.classifier.load_state_dict(torch.load(CLASSIFIER_WEIGHTS_PATH, map_location=DEVICE))
            self.classifier.to(DEVICE).eval()

        # --- 3.2 PatchCore 백본 및 Hook 설정 ---
        self.ad_backbone = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V1).to(DEVICE)
        self.ad_backbone.eval()
        self.features = []

        def hook(module, input, output):
            self.features.append(output)

        self.ad_backbone.layer1[-1].register_forward_hook(hook)
        self.ad_backbone.layer2[-1].register_forward_hook(hook)
        self.ad_backbone.layer3[-1].register_forward_hook(hook)

        # --- 3.3 Memory Banks 로드 ---
        self.memory_banks = {}
        for name, path in AD_MODEL_PATHS.items():
            if os.path.exists(path):
                print(f"[VISION] Loading {name} Memory Bank: {path}")
                self.memory_banks[name] = torch.load(path, map_location=DEVICE)
            else:
                print(f"[VISION] Memory bank not found for {name}: {path}")

        # --- 3.4 전처리 설정 ---
        self.transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(mean=MOBILENET_MEAN, std=MOBILENET_STD),
        ])

    def embed(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: (1,3,224,224)
        return: (H*W, C) 형태 임베딩 (예: 56*56, 1792)
        """
        self.features = []
        with torch.no_grad():
            _ = self.ad_backbone(x)

        f1, f2, f3 = self.features
        target_size = (f1.shape[2], f1.shape[3])

        f1 = F.avg_pool2d(f1, 3, 1, 1)
        f2 = F.interpolate(f2, size=target_size, mode="bilinear", align_corners=False)
        f2 = F.avg_pool2d(f2, 3, 1, 1)
        f3 = F.interpolate(f3, size=target_size, mode="bilinear", align_corners=False)
        f3 = F.avg_pool2d(f3, 3, 1, 1)

        combined = torch.cat([f1, f2, f3], dim=1)
        return combined.permute(0, 2, 3, 1).reshape(-1, combined.shape[1])

    def classify_frame_roi(self, frame: np.ndarray):
        """
        프레임에서 ROI를 잘라 classification 수행
        return: (pred_class:str, confidence:float)  / 실패 시 ("None", 0.0)
        """
        if self.classifier is None:
            return "None", 0.0

        x1, y1 = ROI_X, ROI_Y
        x2, y2 = ROI_X + ROI_W, ROI_Y + ROI_H
        roi_bgr = frame[y1:y2, x1:x2]
        if roi_bgr.size == 0:
            return "None", 0.0

        roi_input = cv2.resize(roi_bgr, (224, 224))
        roi_rgb = cv2.cvtColor(roi_input, cv2.COLOR_BGR2RGB)
        inp = self.transform(Image.fromarray(roi_rgb)).unsqueeze(0).to(DEVICE)

        with torch.no_grad():
            out = self.classifier(inp)
            probs = F.softmax(out, dim=1).squeeze(0)
            pred_idx = int(torch.argmax(probs).item())
            pred_class = CLASS_NAMES[pred_idx]
            confidence = float(probs[pred_idx].item())

        return pred_class, confidence

    def anomaly_score_frame_roi(self, frame: np.ndarray, class_name: str) -> float:
        """
        프레임에서 ROI를 잘라 지정 class_name의 memory bank로 anomaly score 계산
        return: score (float) / 불가 시 0.0
        """
        if class_name not in self.memory_banks:
            return 0.0

        x1, y1 = ROI_X, ROI_Y
        x2, y2 = ROI_X + ROI_W, ROI_Y + ROI_H
        roi_bgr = frame[y1:y2, x1:x2]
        if roi_bgr.size == 0:
            return 0.0

        roi_input = cv2.resize(roi_bgr, (224, 224))
        roi_rgb = cv2.cvtColor(roi_input, cv2.COLOR_BGR2RGB)
        inp = self.transform(Image.fromarray(roi_rgb)).unsqueeze(0).to(DEVICE)

        with torch.no_grad():
            embedding = self.embed(inp)  # (56*56, C)

            bank = self.memory_banks[class_name].to(DEVICE)
            distances = torch.cdist(embedding, bank, p=2)
            min_distances, _ = torch.min(distances, dim=1)

            # 224 입력에서 layer1 기준 56x56
            side_len = 56
            anomaly_map = min_distances.reshape(side_len, side_len)

            # 기존 고도화 예시처럼 "map의 max"를 score로 사용
            score = float(anomaly_map.max().item())

        return score


def _load_inspector():
    global _inspector
    if _inspector is not None:
        return _inspector
    _inspector = IntegratedInspector()
    return _inspector


# =================================================================
# 4. 10프레임 기반 검사 함수 (API에서 호출) - 기존 시그니처/리턴 유지
# =================================================================
def run_anomaly_inspection_once():
    """
    (기존 흐름 유지)
    - 10프레임 캡쳐
    - 각 프레임 classification → 최빈값 module_type
    - module_type 기준 anomaly score 평균 → threshold로 anomaly_flag
    - 마지막 프레임 저장 → 파일명/경로 리턴
    """
    inspector = _load_inspector()
    if inspector.classifier is None:
        raise RuntimeError("Classifier model not loaded")

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        raise RuntimeError("Cannot open camera")

    frames = []
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
    # 1) Classification - 모든 프레임
    # -----------------------------
    cls_scores = []
    cls_preds = []

    for frame in frames:
        pred_class, conf = inspector.classify_frame_roi(frame)
        if pred_class == "None":
            continue
        cls_scores.append(float(conf))
        cls_preds.append(CLASS_NAMES.index(pred_class))

    if not cls_preds:
        # 기존 로직 스타일대로 에러 처리
        raise RuntimeError("Classification failed for all frames")

    # 최빈값 class 선택
    count = Counter(cls_preds)
    most_common_idx, _ = count.most_common(1)[0]
    module_type = CLASS_NAMES[most_common_idx]

    # 평균 confidence (기존 방식 유지)
    classification_confidence = float(sum(cls_scores) / len(cls_scores)) if cls_scores else 0.0

    # -----------------------------
    # 2) Anomaly Detection - 선택된 module_type 기준
    # -----------------------------
    anomaly_flag = None
    anomaly_score = 0.0

    ad_scores = []
    for frame in frames:
        score = inspector.anomaly_score_frame_roi(frame, module_type)
        # score=0.0도 포함(기존 로직의 continue 정책과 유사하게 쓰려면 여기서 걸러야 하지만, 개선은 일단 보류)
        ad_scores.append(float(score))

    if ad_scores:
        anomaly_score = float(sum(ad_scores) / len(ad_scores))
        thr = AD_THRESHOLDS.get(module_type, 5.0)
        anomaly_flag = anomaly_score > thr
    else:
        anomaly_score = 0.0
        anomaly_flag = None

    # -----------------------------
    # 3) 최종 decision 및 이미지 저장 (기존 그대로)
    # -----------------------------
    decision = "REJECT" if anomaly_flag else "PASS"

    last_frame = frames[-1]

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{module_type}_{timestamp}.jpg"
    save_path = os.path.join(LOG_SAVE_DIR, filename)
    os.makedirs(LOG_SAVE_DIR, exist_ok=True)

    ok, buf = cv2.imencode(".jpg", last_frame)
    if not ok:
        raise RuntimeError("imencode('.jpg') failed")

    with open(save_path, "wb") as f:
        f.write(buf.tobytes())

    print("[SAVE] anomaly image saved:", save_path)

    image_path = os.path.join("SynchroBots_WEB", LOG_REL_DIR)

    return {
        "module_type": module_type,
        "classification_confidence": classification_confidence,
        "anomaly_flag": anomaly_flag,
        "anomaly_score": anomaly_score,
        "decision": decision,
        "image_name": filename,
        "image_path": image_path,
    }
