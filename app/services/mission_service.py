# app/services/mission_service.py

from typing import Optional, List, Dict, Any
from app import db
from app.models.dashboard import MissionLog, MissionRobotArmLog


def get_latest_mission_id_for_equipment(equipment_id: str) -> Optional[int]:
    """
    특정 장비(예: ARM01)에 대해 가장 최근 mission_id 반환.
    ARM 장비만 대상으로 한다.
    """
    row = (
        MissionLog.query
        .filter(
            MissionLog.equipment_id == equipment_id,
        )
        .order_by(MissionLog.created_at.desc())
        .first()
    )
    return row.mission_id if row else None


def get_arm_place_logs_for_mission(mission_id: int):
    """
    해당 mission_id의 로봇암 PLACE 로그 목록 반환 (created_at 오름차순).
    """
    rows = (
        MissionRobotArmLog.query
        .filter(
            MissionRobotArmLog.mission_id == mission_id,
            MissionRobotArmLog.action_type == "PLACE",
            MissionRobotArmLog.result_status == "SUCCESS",
        )
        .order_by(MissionRobotArmLog.created_at.asc())
        .all()
    )

    result = []
    for r in rows:
        print(f"test : {r}")
        result.append({
            "log_arm_id": r.log_arm_id,
            "mission_id": r.mission_id,
            "action_type": r.action_type,
            "target_pose": r.target_pose,
            "result_status": r.result_status,
            "module_type": r.module_type,  
            "result_message": r.result_message,
            "created_at": r.created_at.isoformat(),
        })
    return result
