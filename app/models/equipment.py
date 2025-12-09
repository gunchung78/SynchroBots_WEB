# app/models/equipment.py

from app import db
from datetime import datetime

class EquipmentInfo(db.Model):
    __tablename__ = "equipment_info"

    equipment_id   = db.Column(db.String(32), primary_key=True)
    equipment_type = db.Column(db.String(16), nullable=False)  # AMR / PLC / ARM / HMI
    equipment_name = db.Column(db.String(64), nullable=False)
    location       = db.Column(db.String(64))
    is_online      = db.Column(db.Boolean, nullable=False, default=False)
    status         = db.Column(db.String(32))
    last_seen_at   = db.Column(db.DateTime)
    created_at     = db.Column(db.DateTime, nullable=False)
    updated_at     = db.Column(db.DateTime, nullable=False)

    def to_status_label(self):
        """
        UI에 보여줄 문자열 한 줄로 만들어주는 헬퍼.
        예) 'myAgv#1 · IDLE'
        """
        base = self.equipment_name or self.equipment_id
        return f"{base} · {self.status or 'UNKNOWN'}"