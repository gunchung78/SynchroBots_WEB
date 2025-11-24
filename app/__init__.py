from flask import Flask, render_template
from flask_cors import CORS

from config import (
    SECRET_KEY,
    SQLALCHEMY_DATABASE_URI,
    SQLALCHEMY_TRACK_MODIFICATIONS,
)
from app.utils.db import db


def create_app():
    # 템플릿/정적 폴더 설정 포함해서 Flask 인스턴스 생성
    flask_app = Flask(
        __name__,
        template_folder="templates",   # ✅ app 기준으로 templates
        static_folder="static",        # ✅ app/static
        static_url_path="/static",
    )

    # 1) 기본 설정
    flask_app.config["SECRET_KEY"] = SECRET_KEY
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = SQLALCHEMY_TRACK_MODIFICATIONS

    # 2) DB 초기화
    db.init_app(flask_app)

    # 3) 웹 화면 블루프린트 등록
    from app.web.dashboard.routes import bp as dashboard_bp
    # 필요해지면 아래도 다시 켜면 됨
    # from app.web.agv.routes       import bp as agv_web_bp
    # from app.web.log.routes       import bp as log_web_bp

    flask_app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    # flask_app.register_blueprint(agv_web_bp, url_prefix="/agv")
    # flask_app.register_blueprint(log_web_bp, url_prefix="/log")

    # 4) API 블루프린트 등록
    from app.api.v1.dashboard_api import api_dashboard_bp
    # from app.api.v1.agv_api import api_agv_bp
    # from app.api.v1.log_api import api_log_bp

    flask_app.register_blueprint(api_dashboard_bp, url_prefix="/api/v1")
    # flask_app.register_blueprint(api_agv_bp, url_prefix="/api/v1")
    # flask_app.register_blueprint(api_log_bp, url_prefix="/api/v1")

    # 5) 기본 라우트 (예전 run.py 에서 쓰던 것 옮기기)
    @flask_app.get("/")
    def index():
        from flask import render_template
        return render_template("dashboard.html")

    @flask_app.get("/control")
    def control_page():
        from flask import render_template
        return render_template("control.html")

    # 6) 테이블 생성 (초기 개발용)
    with flask_app.app_context():
        import app.models  # 모델 불러오기 (지금은 비어 있어도 OK)
        db.create_all()

    # 7) CORS 적용
    CORS(flask_app)

    return flask_app
