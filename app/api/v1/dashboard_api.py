# app/api/v1/dashboard_api.py

from flask import Blueprint, jsonify, send_file, request
from sqlalchemy import text, desc
from app import db

from app.models.dashboard import ControlLog, EquipmentInfo, EventLog


from PIL import Image
import numpy as np
import io
import os

dashboard_api_bp = Blueprint("dashboard_api", __name__)

# === AGV 맵 이미지 제공 ===

BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../..")
)
MAP_DIR = os.path.join(BASE_DIR, "data", "maps")


@dashboard_api_bp.route("/map-image", methods=["GET"])
def map_image():
    pgm_path = os.path.join(MAP_DIR, "map.pgm")

    if not os.path.exists(pgm_path):
        return jsonify({"error": "map file not found"}), 404

    img = Image.open(pgm_path).convert("L")
    arr = np.array(img)

    UNKNOWN = 205

    mask = arr != UNKNOWN
    coords = np.argwhere(mask)

    if coords.size == 0:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")

    y_min, x_min = coords.min(axis=0)
    y_max, x_max = coords.max(axis=0)

    margin = 20
    y_min = max(y_min - margin, 0)
    x_min = max(x_min - margin, 0)
    y_max = min(y_max + margin, arr.shape[0] - 1)
    x_max = min(x_max + margin, arr.shape[1] - 1)

    cropped = img.crop((x_min, y_min, x_max, y_max))

    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


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