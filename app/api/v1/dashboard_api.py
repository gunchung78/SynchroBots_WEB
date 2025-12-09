# app/api/v1/dashboard_api.py

from flask import Blueprint, jsonify, send_file, request, Response, stream_with_context
from sqlalchemy import text, desc, func, union_all, literal, and_
from app import db
import queue
import json, time

from app.models.dashboard import (
    ControlLog,
    EquipmentInfo,
    EventLog,
    Map,
    AmrStateLog,
)

from PIL import Image
import numpy as np
import io
import os

dashboard_api_bp = Blueprint("dashboard_api", __name__)


# ====== 대시보드 SSE용 간단 브로드캐스터 ======

_dashboard_subscribers: set[queue.Queue] = set()

def publish_dashboard_event(event: dict):
    """
    대시보드로 푸시할 이벤트 공통 함수.
    예) publish_dashboard_event({"type": "amr_state", "payload": {...}})
    """
    dead_queues = []
    for q in list(_dashboard_subscribers):
        try:
            q.put_nowait(event)
        except Exception:
            # 꽉 찌거나 에러난 큐는 제거 후보
            dead_queues.append(q)

    for q in dead_queues:
        _dashboard_subscribers.discard(q)


@dashboard_api_bp.route("/stream", methods=["GET"])
def dashboard_stream():
    """
    대시보드용 SSE 타이머
    클라이언트: new EventSource('/api/v1/dashboard/stream')
    3~10초마다 'tick' 이벤트를 보내서 프론트가 각 API를 다시 호출하게 만듦
    """
    INTERVAL_SEC = 3  # 원하면 3~10 사이에서 조정

    def event_stream():
        # 최초 한 번 연결 확인용
        hello = {
            "type": "hello",
            "payload": {"msg": "dashboard stream connected"},
        }
        yield f"data: {json.dumps(hello, ensure_ascii=False)}\n\n"

        while True:
            tick = {
                "type": "tick",
                "payload": {"ts": time.time()},
            }
            yield f"data: {json.dumps(tick, ensure_ascii=False)}\n\n"
            time.sleep(INTERVAL_SEC)

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
    )

# === MAP 공통 상수 ===

# 프로젝트 기준 경로
BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../..")
)
MAP_DIR = os.path.join(BASE_DIR, "data", "maps")

# 캡처 기준 해상도 (네가 잡아둔 값)
BASE_W = 725
BASE_H = 683

# 확대 정도
ZOOM_FACTOR = 1.4

# 기준 ROI (원본 캡처에서 실제 맵 영역)
BASE_ROI = (260, 230, 500, 440)

# 🔧 나중에 map.yaml 보고 실제 값으로 바꾸면 됨
ORIGIN_X = -11.5      # 예시
ORIGIN_Y = -18      # 예시
RESOLUTION = 0.05     # 예: 1픽셀 = 0.05 m


def _load_active_map_image():
    """
    DB에서 active 맵 1건을 찾아서
    PGM 이미지를 로드하고 (PIL Image), 가로/세로 픽셀을 반환.
    """
    active_map = (
        Map.query
        .order_by(desc(Map.created_at))
        .first()
    )

    if not active_map:
        return None, None, None, "no active map found"

    filename = active_map.map_image or "map.pgm"
    pgm_path = os.path.join(MAP_DIR, filename)

    if not os.path.exists(pgm_path):
        return None, None, None, f"map file not found: {pgm_path}"

    img = Image.open(pgm_path).convert("L")
    w, h = img.size
    return img, w, h, None


def _compute_crop_rect(img_w, img_h):
    """
    원본 이미지 크기(img_w, img_h)를 기준으로
    BASE_ROI + ZOOM_FACTOR 를 적용한 실제 crop 영역을 계산.
    반환: (x_min, y_min, x_max, y_max)
    """
    base_x_min, base_y_min, base_x_max, base_y_max = BASE_ROI
    base_w = base_x_max - base_x_min
    base_h = base_y_max - base_y_min

    # 중심점
    cx = base_x_min + base_w / 2.0
    cy = base_y_min + base_h / 2.0

    # 확대: 폭/높이를 줄임
    zoomed_w = base_w / ZOOM_FACTOR
    zoomed_h = base_h / ZOOM_FACTOR

    zoom_x_min = cx - zoomed_w / 2.0
    zoom_x_max = cx + zoomed_w / 2.0
    zoom_y_min = cy - zoomed_h / 2.0
    zoom_y_max = cy + zoomed_h / 2.0

    # 실제 이미지 해상도에 맞게 스케일링
    scale_x = img_w / float(BASE_W)
    scale_y = img_h / float(BASE_H)

    x_min = int(zoom_x_min * scale_x)
    x_max = int(zoom_x_max * scale_x)
    y_min = int(zoom_y_min * scale_y)
    y_max = int(zoom_y_max * scale_y)

    # 이미지 범위 안으로 클램핑
    x_min = max(0, min(x_min, img_w - 1))
    x_max = max(0, min(x_max, img_w))
    y_min = max(0, min(y_min, img_h - 1))
    y_max = max(0, min(y_max, img_h))

    return x_min, y_min, x_max, y_max

@dashboard_api_bp.route("/map-image", methods=["GET"])
def map_image():
    img, w, h, err = _load_active_map_image()
    if err:
        return jsonify({"error": err}), 404

    mode = request.args.get("mode", "crop")

    # 1) 전체 원본 보기
    if mode == "raw":
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")

    # 2) crop 영역 계산
    x_min, y_min, x_max, y_max = _compute_crop_rect(w, h)

    if x_max - x_min < 10 or y_max - y_min < 10:
        # 안전장치: 뭔가 잘못되면 원본 리턴
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")

    cropped = img.crop((x_min, y_min, x_max, y_max))

    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

@dashboard_api_bp.route("/map-meta", methods=["GET"])
def get_map_meta():
    """
    프론트가 좌표 변환할 수 있도록
    맵/크롭 관련 메타데이터를 내려주는 API
    """
    img, w, h, err = _load_active_map_image()
    if err:
        return jsonify({"error": err}), 404

    x_min, y_min, x_max, y_max = _compute_crop_rect(w, h)

    crop_w = x_max - x_min
    crop_h = y_max - y_min

    return jsonify({
        "origin_x": ORIGIN_X,
        "origin_y": ORIGIN_Y,
        "resolution": RESOLUTION,   # meter → pixel 전환
        "img_width": w,
        "img_height": h,
        "crop_x_min": x_min,
        "crop_y_min": y_min,
        "crop_w": crop_w,
        "crop_h": crop_h,
    }), 200

# === Control Logs (제어 명령 로그) ===

def _get_limit(default=10, max_limit=100):
    try:
        limit = int(request.args.get("limit", default))
    except (TypeError, ValueError):
        return default
    return max(1, min(limit, max_limit))


@dashboard_api_bp.route("/control_logs", methods=["GET"])
def get_control_logs():
    limit = _get_limit(default=10)

    logs = (
        ControlLog.query
        .order_by(desc(ControlLog.created_at))
        .limit(limit)
        .all()
    )

    return jsonify({
        "items": [log.to_dict() for log in logs]
    })

@dashboard_api_bp.route("/events_logs", methods=["GET"])
def get_events():
    """
    대시보드 이벤트 로그용 API
    GET /api/v1/events?limit=10
    """
    try:
        limit = request.args.get("limit", default=10, type=int)
        if not limit or limit < 1:
            limit = 10
        if limit > 100:
            limit = 100

        # 최신순으로 EquipmentInfo와 조인해서 가져오기
        q = (
            db.session.query(EventLog, EquipmentInfo)
            .join(EquipmentInfo, EventLog.equipment_id == EquipmentInfo.equipment_id)
            .order_by(EventLog.created_at.desc())
            .limit(limit)
        )

        items = []
        for ev, eq in q.all():
            items.append(
                {
                    "event_id": ev.event_id,
                    "equipment_id": ev.equipment_id,
                    "equipment_type": ev.equipment_type,
                    "level": ev.level,
                    "message": ev.message,
                    "created_at": ev.created_at.isoformat(sep=" ", timespec="seconds")
                    if ev.created_at
                    else None,
                    "equipment": {
                        "equipment_id": eq.equipment_id,
                        "equipment_name": eq.equipment_name,
                        "equipment_type": eq.equipment_type,
                        "location": eq.location,
                    }
                    if eq
                    else None,
                }
            )

        return jsonify({"items": items, "count": len(items)}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    

@dashboard_api_bp.route("/mission_logs", methods=["GET"])
def get_mission_logs():
    """
    미션 로그(mission_logs) + PLC 미션 로그(mission_plc_logs)를 합쳐서
    장비(equipment_id)별로 가장 최신 1건만 반환하는 API.

    GET /api/v1/dashboard/mission_logs?limit=5
    """
    try:
        limit = _get_limit(default=5, max_limit=50)

        sql = text("""
        SELECT
            x.equipment_id,
            x.equipment_type,
            x.status,
            x.description,
            x.source,
            x.created_at,
            ei.equipment_name
        FROM (
            -- 1) PLC 쪽 미션 로그
            SELECT
                mpl.equipment_id               AS equipment_id,
                'PLC'                          AS equipment_type,
                NULL                           AS status,
                mpl.description                AS description,
                mpl.source                     AS source,
                mpl.created_at                 AS created_at
            FROM mission_plc_logs AS mpl

            UNION ALL

            -- 2) 일반 미션 로그
            SELECT
                ml.equipment_id                AS equipment_id,
                ml.equipment_type              AS equipment_type,
                ml.status                      AS status,
                ml.description                 AS description,
                ml.source                      AS source,
                ml.created_at                  AS created_at
            FROM mission_logs AS ml
        ) AS x
        JOIN (
            -- 장비별 최신 created_at만 뽑기
            SELECT
                equipment_id,
                MAX(created_at) AS max_created_at
            FROM (
                SELECT equipment_id, created_at
                FROM mission_plc_logs
                UNION ALL
                SELECT equipment_id, created_at
                FROM mission_logs
            ) t
            GROUP BY equipment_id
        ) latest
          ON latest.equipment_id = x.equipment_id
         AND latest.max_created_at = x.created_at
        LEFT JOIN equipment_info ei
          ON ei.equipment_id = x.equipment_id
        ORDER BY x.created_at DESC
        LIMIT :limit
        """)

        rows = db.session.execute(sql, {"limit": limit}).mappings().all()

        items = []
        for row in rows:
            created_at = row["created_at"]
            created_str = (
                created_at.strftime("%Y-%m-%d %H:%M:%S")
                if created_at is not None else None
            )

            items.append({
                "equipment_id": row["equipment_id"],
                "equipment_type": row["equipment_type"],
                "status": row["status"],
                "description": row["description"],
                "source": row["source"],
                "created_at": created_str,
                # 프론트에서 m.equipment?.equipment_name 로 쓰기 좋게 nested 구조
                "equipment": {
                    "equipment_id": row["equipment_id"],
                    "equipment_name": row["equipment_name"],
                } if row["equipment_name"] is not None else None,
            })

        return jsonify({"count": len(items), "items": items}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    
@dashboard_api_bp.route("/amr_states", methods=["GET"])
def get_latest_amr_states():
    """
    AGV(AMR) 상태 로그에서
    모든 equipment_id 별로 updated_at 기준 최신 1건씩만 조회.
    (특정 ID 조회 기능 제거됨)
    """

    try:
        # 1) equipment_id 별로 가장 최신 updated_at 을 구하는 서브쿼리
        subq = (
            db.session.query(
                AmrStateLog.equipment_id.label("eq_id"),
                func.max(AmrStateLog.updated_at).label("max_updated_at"),
            )
            .group_by(AmrStateLog.equipment_id)
            .subquery()
        )

        # 2) 서브쿼리와 조인하여 실제 최신 상태 row 가져오기
        q = (
            db.session.query(AmrStateLog)
            .join(
                subq,
                and_(
                    AmrStateLog.equipment_id == subq.c.eq_id,
                    AmrStateLog.updated_at == subq.c.max_updated_at,
                ),
            )
            .order_by(AmrStateLog.equipment_id.asc())
        )

        logs = q.all()

        items = []
        for log in logs:
            data = log.to_dict()

            # equipment_info 조인 결과 포함
            if log.equipment:
                data["equipment"] = log.equipment.to_dict()

            items.append(data)

        return jsonify({
            "items": items,
            "count": len(items)
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500