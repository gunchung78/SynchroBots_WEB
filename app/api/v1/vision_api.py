# app/api/v1/vision_api.py

from flask import Blueprint, request, jsonify, abort, send_file
from pathlib import Path
from config import Config

from sqlalchemy import func, case, desc
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
    from collections import defaultdict
    from datetime import datetime, timedelta

    mode = request.args.get("mode") or "ANOMALY"

    # ✅ 최근 "데이터가 있는 날짜" 기준 N개
    limit_days = int(request.args.get("limit_days", 5))
    if limit_days <= 0:
        limit_days = 5
    if limit_days > 30:
        limit_days = 30

    # (옵션) 기존 days 파라미터는 호환용으로만 두고, 실제로는 사용 안 해도 됨
    # days = int(request.args.get("days", 30))

    # ---------------------------
    # 1) 최근 날짜 N개 먼저 뽑기
    # ---------------------------
    day_col = func.date(MissionCameraLog.created_at).label("d")

    recent_days_rows = (
        db.session.query(day_col)
        .filter(MissionCameraLog.mode == mode)
        .group_by(day_col)
        .order_by(desc(day_col))
        .limit(limit_days)
        .all()
    )

    # 데이터가 없으면 빈 응답
    if not recent_days_rows:
        return jsonify({
            "stats": {
                "total_count": 0,
                "pass_count": 0,
                "reject_count": 0,
                "unknown_count": 0,
                "pass_rate": 0.0,
                "avg_confidence": None,
                "avg_anomaly_score": None,
            },
            "chart": {
                "labels": [],
                "pass_scores": [],
                "reject_scores": [],
                "threshold": 45
            },
            "meta": {
                "window_type": "recent_days_with_data",
                "limit_days": limit_days,
                "mode": mode,
            }
        })

    # 날짜 리스트 (desc로 뽑혔으니 이후 차트는 asc로 보기 좋게)
    recent_days = [r.d for r in recent_days_rows]
    recent_days_sorted = sorted(recent_days)  # asc

    # ---------------------------
    # 2) 그 날짜들에 해당하는 로그만 조회
    #    (DATE(created_at) IN (...))
    # ---------------------------
    logs = (
        db.session.query(MissionCameraLog)
        .filter(MissionCameraLog.mode == mode)
        .filter(func.date(MissionCameraLog.created_at).in_(recent_days))
        .order_by(MissionCameraLog.created_at.asc())
        .all()
    )

    # ---------- 기본 통계 ----------
    total       = len(logs)
    pass_cnt    = sum(1 for x in logs if x.decision == "PASS")
    reject_cnt  = sum(1 for x in logs if x.decision == "REJECT")
    unknown_cnt = total - pass_cnt - reject_cnt
    pass_rate   = (pass_cnt / total) if total > 0 else 0.0

    anomaly_vals = [x.anomaly_score for x in logs if x.anomaly_score is not None]
    avg_anomaly = (sum(anomaly_vals) / len(anomaly_vals)) if anomaly_vals else None

    conf_vals = [x.classification_confidence for x in logs if x.classification_confidence is not None]
    avg_conf = (sum(conf_vals) / len(conf_vals)) if conf_vals else None

    # ---------------------------
    # Day 단위 버킷 생성 (최근 N일만)
    # ---------------------------
    bucket_pass = defaultdict(list)
    bucket_reject = defaultdict(list)

    count_pass = defaultdict(int)
    count_reject = defaultdict(int)
    count_total = defaultdict(int)

    for x in logs:
        day = x.created_at.date()

        # total은 anomaly_score 유무와 무관하게 "결정 로그 수"로 세고 싶으면 decision 기준 추천
        if x.decision in ("PASS", "REJECT"):
            count_total[day] += 1
            if x.decision == "PASS":
                count_pass[day] += 1
            elif x.decision == "REJECT":
                count_reject[day] += 1

        # score 평균용 버킷은 anomaly_score 있을 때만
        if x.anomaly_score is None:
            continue

        if x.decision == "PASS":
            bucket_pass[day].append(x.anomaly_score)
        elif x.decision == "REJECT":
            bucket_reject[day].append(x.anomaly_score)
        
        
        
    def avg(lst):
        return (sum(lst) / len(lst)) if lst else None

    # ✅ labels는 “최근 N일(데이터 있는 날짜)”을 강제로 유지
    labels = recent_days_sorted

    pass_counts   = [count_pass[d] for d in labels]
    reject_counts = [count_reject[d] for d in labels]
    total_counts  = [count_total[d] for d in labels]

    raw_pass_scores   = [avg(bucket_pass[d]) for d in labels]
    raw_reject_scores = [avg(bucket_reject[d]) for d in labels]

    # 차트용 10배 스케일링
    SCALE = 10.0
    pass_scores   = [v * SCALE if v is not None else None for v in raw_pass_scores]
    reject_scores = [v * SCALE if v is not None else None for v in raw_reject_scores]

    label_strings = [d.strftime("%Y-%m-%d") for d in labels]

    return jsonify({
        "stats": {
            "total_count": total,
            "pass_count": pass_cnt,
            "reject_count": reject_cnt,
            "unknown_count": unknown_cnt,
            "pass_rate": pass_rate,
            "avg_confidence": avg_conf,
            "avg_anomaly_score": avg_anomaly,
        },
        "chart": {
            "labels": label_strings,
            "pass_scores": pass_scores,
            "reject_scores": reject_scores,
            "threshold": 45,
            "pass_counts": pass_counts,
            "reject_counts": reject_counts,
            "total_counts": total_counts,
        },
        "meta": {
            "window_type": "recent_days_with_data",
            "limit_days": limit_days,
            "mode": mode,
        }
    })

@vision_api_bp.route("/confidence_stats", methods=["GET"])
def get_vision_confidence_stats():
    limit_days = int(request.args.get("limit_days", 5))
    if limit_days <= 0:
        limit_days = 5

    exclude_zero = request.args.get("exclude_zero", "1")
    exclude_zero = exclude_zero not in ("0", "false", "False")

    day_col = func.date(MissionCameraLog.created_at).label("d")

    # ✅ 평균
    anomaly_cls_avg = func.avg(
        case((MissionCameraLog.mode == "ANOMALY", MissionCameraLog.classification_confidence), else_=None)
    ).label("anomaly_cls_avg")

    joint_cls_avg = func.avg(
        case((MissionCameraLog.mode == "JOINT_DETECTION", MissionCameraLog.classification_confidence), else_=None)
    ).label("joint_cls_avg")

    # ✅ 카운트(일자별)
    anomaly_cnt = func.sum(
        case((MissionCameraLog.mode == "ANOMALY", 1), else_=0)
    ).label("anomaly_cnt")

    joint_cnt = func.sum(
        case((MissionCameraLog.mode == "JOINT_DETECTION", 1), else_=0)
    ).label("joint_cnt")

    q = db.session.query(day_col, anomaly_cls_avg, joint_cls_avg, anomaly_cnt, joint_cnt)

    if exclude_zero:
        q = q.filter(
            ~(
                (MissionCameraLog.mode == "JOINT_DETECTION")
                & (MissionCameraLog.classification_confidence == 0.0)
            )
        )

    rows_desc = (
        q.group_by(day_col)
         .order_by(desc(day_col))
         .limit(limit_days)
         .all()
    )
    rows = list(reversed(rows_desc))  # asc

    labels = []
    anomaly_avg = []
    joint_avg = []
    anomaly_counts = []
    joint_counts = []
    total_counts = []

    for r in rows:
        labels.append(r.d.strftime("%Y-%m-%d"))
        anomaly_avg.append(float(r.anomaly_cls_avg) if r.anomaly_cls_avg is not None else None)
        joint_avg.append(float(r.joint_cls_avg) if r.joint_cls_avg is not None else None)

        a = int(r.anomaly_cnt or 0)
        j = int(r.joint_cnt or 0)
        anomaly_counts.append(a)
        joint_counts.append(j)
        total_counts.append(a + j)

    return jsonify({
        "chart": {
            "labels": labels,
            "anomaly_cls_avg": anomaly_avg,
            "joint_cls_avg": joint_avg,
            "anomaly_counts": anomaly_counts,
            "joint_counts": joint_counts,
            "total_counts": total_counts
        },
        "meta": {
            "window_type": "recent_days_with_data",
            "limit_days": limit_days,
            "exclude_zero": exclude_zero
        }
    })