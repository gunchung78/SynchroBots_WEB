# app/api/v1/vision_api.py

from flask import Blueprint, request, jsonify, abort, send_file
from pathlib import Path
from config import Config

from sqlalchemy import func
from datetime import datetime, timedelta

from app import db
from app.models.opcua import (
    MissionCameraLog,
)

vision_api_bp = Blueprint("vision_api", __name__)

@vision_api_bp.route("/logs", methods=["GET"])
def get_vision_logs():
    """
    mission_camera_logs 목록 조회 API
    예: GET /api/v1/vision/logs?mode=ANOMALY&decision=PASS&limit=50&offset=0
    """
    # 1) 쿼리 파라미터 파싱
    mode = request.args.get("mode", type=str)          # 'ANOMALY', 'JOINT_DETECTION'
    decision = request.args.get("decision", type=str)  # 'PASS', 'REJECT', 'UNKNOWN'

    limit = request.args.get("limit", default=100, type=int)
    offset = request.args.get("offset", default=0, type=int)

    # 안전하게 상한선 하나 정도 두는 것도 추천
    if limit > 500:
        limit = 500
    if offset < 0:
        offset = 0

    # 2) 기본 쿼리
    q = MissionCameraLog.query

    # (옵션) 장비 테이블 조인해서 equipment_name 같이 가져오고 싶으면
    # q = q.join(MissionCameraLog.equipment).options(db.contains_eager(MissionCameraLog.equipment))

    # 3) 필터 적용
    if mode:
        q = q.filter(MissionCameraLog.mode == mode)

    if decision:
        q = q.filter(MissionCameraLog.decision == decision)

    # 4) total 카운트 (필터 적용된 상태에서)
    total = q.count()

    # 5) 정렬 + 페이지네이션
    rows = (
        q.order_by(MissionCameraLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # 6) 직렬화
    items = [camera_log_to_dict(row) for row in rows]

    return jsonify(
        {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    )

def camera_log_to_dict(row: MissionCameraLog) -> dict:
    """mission_camera_logs 한 줄을 프론트에서 쓰기 좋은 dict로 변환"""

    equipment_name = None
    if getattr(row, "equipment", None) is not None:
        equipment_name = row.equipment.equipment_name

    return {
        "log_camera_id": row.log_camera_id,
        "equipment_id": row.equipment_id,
        "equipment": {
            "equipment_id": row.equipment_id,
            "equipment_name": equipment_name,
        },
        "mode": row.mode,
        "image_path": row.image_path,
        "image_name": row.image_name,
        "module_type": row.module_type,
        "classification_confidence": row.classification_confidence,
        "anomaly_flag": row.anomaly_flag,
        "anomaly_score": row.anomaly_score,
        "decision": row.decision,
        "pick_coord": row.pick_coord,
        "created_at": row.created_at.isoformat(sep=" ", timespec="seconds")
        if row.created_at
        else None,
    }


@vision_api_bp.route("/logs_image", methods=["GET"])
def get_logs_image():
    """
    예:
      /api/v1/vision/logs_image?path=data/visions/logs/Anomaly&name=ESP32_20251204_113125.jpg
    """
    raw_path = (request.args.get("path") or "").replace("\\", "/").strip()
    name = (request.args.get("name") or "").strip()

    if not name:
        abort(400, description="name is required")

    # 1) 기본 베이스 디렉토리: SynchroBots_WEB/data/visions
    base = (Config.BASE_DIR).resolve()
    print(base)
    # 2) path 값이 우리가 기대하는 상대경로라고 가정 (앞으로 DB에도 이렇게 저장하는 걸 추천)
    #    예: "logs/Anomaly" 또는 "data/visions/logs/Anomaly"
    p = Path(raw_path)

    # "data/visions/..." 로 들어오는 경우에는 뒷부분만 떼서 씀
    try:
        # base 의 하위 경로이면 상대경로로 다시 재구성
        if str(p).startswith("data/visions/"):
            p = Path(*p.parts[2:])  # data, visions 잘라내기
    except Exception:
        pass

    full_path = (base / p / name).resolve()

    # 3) 디렉토리 탈출 방지
    if not str(full_path).startswith(str(base)):
        abort(400, description="invalid path")

    if not full_path.exists():
        abort(404, description=f"image not found: {full_path}")

    return send_file(str(full_path), mimetype="image/jpeg")


@vision_api_bp.route("/stats", methods=["GET"])
def get_vision_stats():
    from datetime import datetime, timedelta
    from collections import defaultdict

    mode = request.args.get("mode") or "ANOMALY"

    # 최근 n일 (기본 30일)
    days = int(request.args.get("days", 30))
    since = datetime.utcnow() - timedelta(days=days)

    q = (
        db.session.query(MissionCameraLog)
        .filter(MissionCameraLog.created_at >= since)
        .filter(MissionCameraLog.mode == mode)
        .order_by(MissionCameraLog.created_at.asc())
    )

    logs = q.all()

    # ---------- 기본 통계 ----------
    total       = len(logs)
    pass_cnt    = sum(1 for x in logs if x.decision == "PASS")
    reject_cnt  = sum(1 for x in logs if x.decision == "REJECT")
    unknown_cnt = total - pass_cnt - reject_cnt
    pass_rate   = (pass_cnt / total) if total > 0 else 0.0

    # 평균 anomaly_score (원본 값, 스케일링 X)
    anomaly_vals = [x.anomaly_score for x in logs if x.anomaly_score is not None]
    avg_anomaly = sum(anomaly_vals) / len(anomaly_vals) if anomaly_vals else None

    # 평균 confidence (원본 값)
    conf_vals = [
        x.classification_confidence
        for x in logs
        if x.classification_confidence is not None
    ]
    avg_conf = sum(conf_vals) / len(conf_vals) if conf_vals else None

    # ---------------------------
    # Day 단위 버킷 생성
    # ---------------------------
    bucket_pass = defaultdict(list)
    bucket_reject = defaultdict(list)

    for x in logs:
        if x.anomaly_score is None:
            continue

        day = x.created_at.date()  # 날짜 단위

        if x.decision == "PASS":
            bucket_pass[day].append(x.anomaly_score)
        elif x.decision == "REJECT":
            bucket_reject[day].append(x.anomaly_score)

    # 날짜 정렬
    labels = sorted(set(bucket_pass.keys()) | set(bucket_reject.keys()))

    def avg(lst):
        return (sum(lst) / len(lst)) if lst else None

    # 원본 평균 값
    raw_pass_scores   = [avg(bucket_pass[d]) for d in labels]
    raw_reject_scores = [avg(bucket_reject[d]) for d in labels]

    # ---------------------------
    # 📌 차트용 값은 10배 스케일링
    # ---------------------------
    SCALE = 10.0
    pass_scores   = [v * SCALE if v is not None else None for v in raw_pass_scores]
    reject_scores = [v * SCALE if v is not None else None for v in raw_reject_scores]

    # YYYY-MM-DD 문자열로 변환
    label_strings = [d.strftime("%Y-%m-%d") for d in labels]

    return jsonify({
        "stats": {
            "total_count": total,
            "pass_count": pass_cnt,
            "reject_count": reject_cnt,
            "unknown_count": unknown_cnt,
            "pass_rate": pass_rate,
            "avg_confidence": avg_conf,
            "avg_anomaly_score": avg_anomaly,  # ← 요약용은 원본 값 유지
        },
        "chart": {
            "labels": label_strings,
            "pass_scores": pass_scores,        # ← ×10 된 값
            "reject_scores": reject_scores,    # ← ×10 된 값
            "threshold": 0.55                  # 임계값은 그대로 유지 (0~1 범위)
        }
    })