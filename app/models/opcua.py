# app/models/dashboard.py
from app import db
from datetime import datetime

class MissionCameraLog(db.Model):
    __tablename__ = "mission_camera_logs"

    # PK
    log_camera_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)

    # FK: equipment_info.equipment_id
    equipment_id = db.Column(
        db.String(32),
        db.ForeignKey("equipment_info.equipment_id"),
        nullable=False,
    )

    # 검사 모드: ANOMALY / JOINT_DETECTION
    mode = db.Column(
        db.Enum("ANOMALY", "JOINT_DETECTION", name="enum_mission_camera_mode"),
        nullable=False,
        default="ANOMALY",
        server_default="ANOMALY",
    )

    # 이미지 파일 경로 (선택)
    image_path = db.Column(db.String(255))

    # 캡처 원본 이미지 (JPEG/PNG 바이너리)
    image_data = db.Column(db.LargeBinary)

    # 모듈 분류 결과 (MB102, L298N, ESP32 등)
    module_type = db.Column(db.String(64))

    # 분류 신뢰도 (0.0 ~ 1.0)
    classification_confidence = db.Column(db.Float)

    # 이상 탐지 여부 (1=불량, 0=정상, NULL=미실행)
    anomaly_flag = db.Column(db.Boolean)

    # 이상 점수
    anomaly_score = db.Column(db.Float)

    # 최종 판단: PASS / REJECT / UNKNOWN
    decision = db.Column(
        db.Enum("PASS", "REJECT", "UNKNOWN", name="enum_mission_camera_decision"),
        nullable=False,
        default="UNKNOWN",
        server_default="UNKNOWN",
    )

    # 픽업 좌표 (나중에 mycobot coord 연동 시 사용)
    pick_coord = db.Column(db.Float)

    # 생성 시각
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=db.func.current_timestamp(),
    )

    # 필요하다면 equipment_info 모델과 관계도 걸어둘 수 있음
    equipment = db.relationship(
        "EquipmentInfo",
        backref=db.backref("mission_camera_logs", lazy="dynamic"),
        lazy="joined",
    )

    def __repr__(self):
        return (
            f"<MissionCameraLog id={self.log_camera_id} "
            f"eq={self.equipment_id} mode={self.mode} decision={self.decision}>"
        )