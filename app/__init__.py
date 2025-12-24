# app/__init__.py

from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from config import Config
import logging

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

    # ───────── Web UI Blueprint ─────────
    from app.web import web_bp
    app.register_blueprint(web_bp, url_prefix="")  # url_prefix="" (루트에 매핑)

    # ───────── API Blueprints ─────────
    from app.api.v1.plc_api import plc_api_bp
    app.register_blueprint(plc_api_bp, url_prefix="/api/v1/plc")      
    from app.api.v1.amr_api import amr_api_bp
    app.register_blueprint(amr_api_bp, url_prefix="/api/v1/amr")     
    from app.api.v1.arm_api import arm_api_bp
    app.register_blueprint(arm_api_bp, url_prefix="/api/v1/arm")     
    from app.api.v1.vision_api import vision_api_bp
    app.register_blueprint(vision_api_bp, url_prefix="/api/v1/vision")     
    from app.api.v1.control_api import control_api_bp
    app.register_blueprint(control_api_bp, url_prefix="/api/v1/control")     


    from app.api.v1.dashboard_api import dashboard_api_bp
    app.register_blueprint(dashboard_api_bp, url_prefix="/api/v1/dashboard")

    # 초기 개발용: 테이블 자동 생성
    with app.app_context():
        db.create_all()

    # CORS
    CORS(app)

    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    return app
