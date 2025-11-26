# app/api/v1/dashboard_api.py

from flask import Blueprint, jsonify, send_file
from sqlalchemy import text
from app.utils.db import db

from PIL import Image
import numpy as np
import io, os

api_dashboard_bp = Blueprint("api_dashboard", __name__)

# === DB 연결 체크 ===
@api_dashboard_bp.route("/ping-db", methods=["GET"])
def ping_db():
    try:
        result = db.session.execute(text("SELECT 1 AS ok")).scalar()
        return jsonify({"db_ok": bool(result)}), 200
    except Exception as e:
        return jsonify({"db_ok": False, "error": str(e)}), 500


# === AGV 맵 이미지 제공 ===

# SynchroBots_web/ 기준으로 data/maps/ 경로 잡기
BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../..")
)
MAP_DIR = os.path.join(BASE_DIR, "data", "maps")


@api_dashboard_bp.route("/map-image", methods=["GET"])
def map_image():
    pgm_path = os.path.join(MAP_DIR, "map.pgm")

    if not os.path.exists(pgm_path):
        return jsonify({"error": "map file not found"}), 404

    img = Image.open(pgm_path).convert("L")
    arr = np.array(img)

    UNKNOWN = 205  # 필요시 조정

    # 1) unknown(205) 제외한 픽셀만 bbox 대상으로 사용
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

    # 필요하면 여기서 2배 확대도 가능
    # cropped = cropped.resize(
    #     (cropped.width * 2, cropped.height * 2),
    #     Image.NEAREST
    # )

    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")
