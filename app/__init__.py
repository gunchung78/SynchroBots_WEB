# app/__init__.py

from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from config import Config

db = SQLAlchemy()


def create_app():
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static"
    )
    app.config.from_object(Config)

    # DB 초기화
    db.init_app(app)

    # 모델 import (FK나 관계가 있으면 반드시 init 후 import)
    from app.models import dashboard

     # ───────── Web UI Blueprints ──────
    from app.web.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp)
    from app.web.vision import vision_bp
    app.register_blueprint(vision_bp, url_prefix="/vision")

    # ───────── API Blueprints ─────────
    from app.api.v1.plc_api import plc_api_bp
    app.register_blueprint(plc_api_bp, url_prefix="/api/v1/plc")      
    from app.api.v1.amr_api import amr_api_bp
    app.register_blueprint(amr_api_bp, url_prefix="/api/v1/amr")     
    from app.api.v1.arm_api import arm_api_bp
    app.register_blueprint(arm_api_bp, url_prefix="/api/v1/arm")     
    from app.api.v1.vision_api import vision_api_bp
    app.register_blueprint(vision_api_bp, url_prefix="/api/v1/vision")     


    from app.api.v1.dashboard_api import dashboard_api_bp
    app.register_blueprint(dashboard_api_bp, url_prefix="/api/v1/dashboard")

    # 초기 개발용: 테이블 자동 생성
    with app.app_context():
        db.create_all()

    # CORS
    CORS(app)

    return app
