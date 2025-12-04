# app/web/dashboard/routes.py

from flask import render_template
from . import vision_bp
from flask import Blueprint, render_template, send_file, abort
from io import BytesIO
from app import db
from app.models.opcua import MissionCameraLog

@vision_bp.get("/mission-camera-logs")
def index():
    """
    미션 카메라 로그를 최근 순으로 몇 개만 보여주는 팝업 페이지
    """
    logs = (
        MissionCameraLog.query
        .order_by(MissionCameraLog.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template("mission_camera_logs_popup.html", logs=logs)

@vision_bp.route("/mission-camera-logs/image/<int:log_id>")
def mission_camera_log_image(log_id: int):
    """
    특정 로그의 image_data BLOB 을 그대로 내려주는 엔드포인트
    <img src="..."> 에서 사용
    """
    log = MissionCameraLog.query.get(log_id)
    if not log or not log.image_data:
        abort(404)

    # 여기서는 일단 JPEG 가정 (로그 내용에 JFIF 헤더 보이니 JPG일 확률 높음)
    # 만약 PNG도 섞이면 content_type을 컬럼으로 따로 두거나 헤더보고 판단
    return send_file(
        BytesIO(log.image_data),
        mimetype="image/jpeg",
        download_name=f"log_{log_id}.jpg",
    )