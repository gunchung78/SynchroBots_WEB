# app/models/control.py
from app import db
from sqlalchemy.sql import func

class PlcControlState(db.Model):
    __tablename__ = "plc_control_state"

    equipment_id = db.Column(
        db.String(32),
        db.ForeignKey("equipment_info.equipment_id"),
        primary_key=True,
        nullable=False,
        comment="컨베이어 장비 ID (equipment_info FK)"
    )

    run_mode = db.Column(
        db.Enum("STOP", "RUN"),
        nullable=False,
        default="STOP",
        comment="운행 상태 (정지 / 자동운전 / 수동)"
    )

    direction = db.Column(
        db.Enum("FORWARD", "REVERSE"),
        nullable=True,
        default="FORWARD",
        comment="벨트 방향"
    )

    frequency = db.Column(
        db.Numeric(6, 2),
        nullable=True,
        comment="주파수 설정값"
    )

    acceleration = db.Column(
        db.Integer,
        nullable=True,
        comment="가속도"
    )

    deceleration = db.Column(
        db.Integer,
        nullable=True,
        comment="감속도"
    )


    remark1 = db.Column(db.String(255), nullable=True, comment="비고1")
    remark2 = db.Column(db.String(255), nullable=True, comment="비고2")
    remark3 = db.Column(db.String(255), nullable=True, comment="비고3")

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        comment="마지막 업데이트 시각"
    )

    equipment = db.relationship(
        "EquipmentInfo",
        backref="plc_control_state",
        lazy="joined",
        primaryjoin="PlcControlState.equipment_id == EquipmentInfo.equipment_id"
    )

    def to_dict(self, include_image=False):
        data = {
            "equipment_id": self.equipment_id,
            "run_mode": self.run_mode,
            "direction": self.direction,
            "frequency": float(self.frequency) if self.frequency is not None else None,
            "acceleration": self.acceleration,
            "deceleration": self.deceleration,
            "remark1": self.remark1,
            "remark2": self.remark2,
            "remark3": self.remark3,
            "updated_at": (
                self.updated_at.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                if self.updated_at else None
            ),
            "equipment": self.equipment.to_dict() if self.equipment else None,
        }

