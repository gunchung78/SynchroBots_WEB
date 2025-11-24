from flask import Blueprint, jsonify
from app.utils.db import db
from sqlalchemy import text   # ✅ 추가

api_dashboard_bp = Blueprint("api_dashboard", __name__)

@api_dashboard_bp.route("/ping-db", methods=["GET"])
def ping_db():
    try:
        # SQLAlchemy 2.x에서는 text()로 감싸줘야 함
        result = db.session.execute(text("SELECT 1 AS ok")).scalar()
        return jsonify({"db_ok": bool(result)}), 200
    except Exception as e:
        return jsonify({"db_ok": False, "error": str(e)}), 500
