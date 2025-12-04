# app/models/dashboard.py
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


class MissionLog(db.Model):
    __tablename__ = "mission_logs"

    mission_id = db.Column(db.BigInteger, primary_key=True)  # PK
    equipment_id = db.Column(
        db.String(32),
        db.ForeignKey("equipment_info.equipment_id"),
        nullable=True,
    )
    equipment_type = db.Column(
        db.Enum("AMR", "PLC", "ARM", "HMI", "VISION"),
        nullable=False,
    )
    module_type = db.Column(db.String(64), nullable=False)
    status = db.Column(
        db.Enum("WAITING", "RUNNING", "DONE", "ERROR"),
        nullable=False,
    )
    description = db.Column(db.String(255), nullable=True)
    # mission_logs 테이블에 source 컬럼을 이미 추가해둔 상태라면 다음 라인 사용
    source = db.Column(
        db.Enum("PLC", "WEB", "API"),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    equipment = db.relationship(
        "EquipmentInfo",
        backref="mission_logs",
        primaryjoin="MissionLog.equipment_id == EquipmentInfo.equipment_id",
    )

    def to_dict(self):
        return {
            "mission_id": self.mission_id,
            "equipment_id": self.equipment_id,
            "equipment_type": self.equipment_type,
            "module_type": self.module_type,
            "status": self.status,
            "description": self.description,
            "source": self.source,
            "created_at": (
                self.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if self.created_at else None
            ),
        }


class MissionPlcLog(db.Model):
    __tablename__ = "mission_plc_logs"

    log_plc_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    equipment_id = db.Column(
        db.String(32),
        db.ForeignKey("equipment_info.equipment_id"),
        nullable=False,
    )
    # enum 값은 DDL에 맞춰서 조정
    source = db.Column(
        db.Enum("PLC", "WEB", "API", "OPCUA", "SCRIPT"),
        nullable=False,
    )
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    equipment = db.relationship(
        "EquipmentInfo",
        backref="mission_plc_logs",
        primaryjoin="MissionPlcLog.equipment_id == EquipmentInfo.equipment_id",
    )

    def to_dict(self):
        return {
            "log_plc_id": self.log_plc_id,
            "equipment_id": self.equipment_id,
            "source": self.source,
            "description": self.description,
            "created_at": (
                self.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if self.created_at else None
            ),
        }
    
class Map(db.Model):
    __tablename__ = "maps"

    map_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name = db.Column(db.String(64), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # DDL은 longblob 이지만, 현재는 "map.pgm" 같은 파일명을 넣어서 쓸 계획이므로
    # ORM 에서는 Text 로 잡아두는 편이 편함 (경로/파일명 문자열 저장용)
    map_image = db.Column(db.Text, nullable=True, comment="맵 파일명 또는 경로")

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    def to_dict(self):
        return {
            "map_id": self.map_id,
            "name": self.name,
            "version": self.version,
            "is_active": self.is_active,
            "map_image": self.map_image,
            "created_at": (
                self.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if self.created_at else None
            ),
        }

class AmrStateLog(db.Model):
    __tablename__ = "amr_state_log"

    idx = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    equipment_id = db.Column(
        db.String(32),
        db.ForeignKey("equipment_info.equipment_id"),
        nullable=False,
    )

    pos_x = db.Column(
        db.Float,
        nullable=False,
    )
    pos_y = db.Column(
        db.Float,
        nullable=False,
    )

    heading = db.Column(
        db.Float,
        nullable=False,
    )

    battery_pct = db.Column(
        db.Float,
        nullable=False,
    )

    speed = db.Column(
        db.Float,
        nullable=False,
    )

    state_code = db.Column(
        db.String(16),
        nullable=True,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    equipment = db.relationship(
        "EquipmentInfo",
        backref="amr_state_logs",
        primaryjoin="AmrStateLog.equipment_id == EquipmentInfo.equipment_id",
    )

    def to_dict(self):
        return {
            "idx": self.idx,
            "equipment_id": self.equipment_id,
            "pos_x": self.pos_x,
            "pos_y": self.pos_y,
            "heading": self.heading,
            "battery_pct": self.battery_pct,
            "speed": self.speed,
            "state_code": self.state_code,
            "updated_at": (
                self.updated_at.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                if self.updated_at else None
            ),
        }
