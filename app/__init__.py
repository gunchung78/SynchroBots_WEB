# app/__init__.py

from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

from config import Config  # 프로젝트 루트에 있는 config.py

db = SQLAlchemy()


def create_app():
    # ───────────────────────────
    # 1) Flask App 생성
    # ───────────────────────────
    flask_app = Flask(__name__, template_folder="templates", static_folder="static")
    flask_app.config.from_object(Config)

    # ───────────────────────────
    # 2) DB 초기화
    # ───────────────────────────
    db.init_app(flask_app)

    # ───────────────────────────
    # 3) Blueprint 등록
    # ───────────────────────────
    # (1) Dashboard / Web UI 라우트
    from app.web.dashboard import dashboard_bp
    flask_app.register_blueprint(dashboard_bp)

    # (2) 기타 API 라우트들 (예: /api/v1/...)
    # 필요하면 여기에 추가
    # from app.api.example import api_bp
    # flask_app.register_blueprint(api_bp, url_prefix="/api/v1")

    # # (3) OPC UA Webhook 라우트
    # from app.api.opcua_api import opcua_bp
    # flask_app.register_blueprint(opcua_bp, url_prefix="/api/v1/opcua")

    # ───────────────────────────
    # 4) 테이블 생성 (초기 개발 시에만 사용)
    # ───────────────────────────
    with flask_app.app_context():
        import app.models  # 모든 모델 불러오기
        db.create_all()

    # ───────────────────────────
    # 5) CORS 적용
    # ───────────────────────────
    CORS(flask_app)

    # ───────────────────────────
    # 6) 최종 반환
    # ───────────────────────────
    return flask_app
