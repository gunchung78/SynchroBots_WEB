# app/models/dashboard.py
from app import db
from datetime import datetime


from app import db
from datetime import datetime


class ControlLog(db.Model):
    __tablename__ = "control_logs"

    control_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    equipment_id = db.Column(
        db.String(32),
        db.ForeignKey("equipment_info.equipment_id"),
        nullable=True
    )

    target_type = db.Column(
        db.Enum("AMR", "PLC", "ARM", "SYSTEM"),
        nullable=False
    )
    action_type = db.Column(db.String(64), nullable=False)
    operator_name = db.Column(db.String(64), nullable=True)
    source = db.Column(
        db.Enum("WEB", "API", "SCRIPT"),
        nullable=False,
        default="WEB"
    )

    request_payload = db.Column(
        db.Text(collation="utf8mb4_bin"),
        nullable=True
    )
    result_status = db.Column(
        db.Enum("SUCCESS", "FAIL", "TIMEOUT"),
        nullable=False,
        default="SUCCESS"
    )
    result_message = db.Column(db.Text, nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow
    )

    equipment = db.relationship(
        "EquipmentInfo",
        backref="control_logs",
        lazy="joined",
        primaryjoin="ControlLog.equipment_id == EquipmentInfo.equipment_id"
    )

    def to_dict(self):
        return {
            "control_id": self.control_id,
            "equipment_id": self.equipment_id,
            "target_type": self.target_type,
            "action_type": self.action_type,
            "operator_name": self.operator_name,
            "source": self.source,
            "request_payload": self.request_payload,
            "result_status": self.result_status,
            "result_message": self.result_message,
            "created_at": (
                self.created_at.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                if self.created_at else None
            ),
            "equipment": self.equipment.to_dict() if self.equipment else None
        }
    

class EventLog(db.Model):
    __tablename__ = "events_logs"

    event_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    equipment_id = db.Column(
        db.String(32),
        db.ForeignKey("equipment_info.equipment_id"),
        nullable=False,
    )
    equipment_type = db.Column(db.String(16), nullable=False)
    level = db.Column(db.String(8), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)

    equipment = db.relationship("EquipmentInfo", backref="events_logs")


class EquipmentInfo(db.Model):
    __tablename__ = "equipment_info"

    equipment_id = db.Column(db.String(32), primary_key=True)
    equipment_type = db.Column(db.Enum("AMR", "PLC", "ARM", "HMI"), nullable=False)
    equipment_name = db.Column(db.String(64), nullable=False)
    location = db.Column(db.String(64))
    is_online = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(32))
    last_seen_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    def to_dict(self):
        return {
            "equipment_id": self.equipment_id,
            "equipment_type": self.equipment_type,
            "equipment_name": self.equipment_name,
            "location": self.location,
            "is_online": self.is_online,
            "status": self.status,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
