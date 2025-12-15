# app/services/control_log_service.py

import json
from typing import Optional, Dict, Any, Tuple

from app import db
from app.models.dashboard import ControlLog  # 실제 모델 경로/이름에 맞게 수정

def log_control_action(
    *,
    equipment_id: Optional[str],
    target_type: str,          # 'AMR' | 'PLC' | 'ARM' | 'SYSTEM'
    action_type: str,
    operator_name: Optional[str] = None,
    source: str = "API",       # 'WEB' | 'API' | 'SCRIPT'
    trigger_event: Optional[str] = None,  
    request_payload: Any = None,
    result_status: str = "SUCCESS",   # 'SUCCESS' | 'FAIL' | 'TIMEOUT'
    result_message: Optional[str] = None,
) -> None:
    """
    control_logs 테이블에 한 줄 로그를 남기는 공통 함수.
    request_payload 에 dict / list / str 뭐가 와도 결국 문자열로 저장.
    """
    try:
        payload_str: Optional[str] = None

        if request_payload is None:
            payload_str = None
        elif isinstance(request_payload, (dict, list)):
            # dict/list 는 JSON 문자열로
            payload_str = json.dumps(request_payload, ensure_ascii=False)
        else:
            # 나머지는 그냥 str() 한 번
            payload_str = str(request_payload)

        log = ControlLog(
            equipment_id=equipment_id,
            target_type=target_type,
            action_type=action_type,
            operator_name=operator_name,
            trigger_event=trigger_event,
            source=source,
            request_payload=payload_str,
            result_status=result_status,
            result_message=result_message,
        )

        db.session.add(log)
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        print(f"[CONTROL_LOG] insert error: {e}")


# ------------------------------------------------------
# 1) 공통 Payload 검증 함수
# ------------------------------------------------------
def validate_control_payload(
    data: Dict[str, Any],
    *,
    expect_target: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Control API로 들어오는 요청 Payload 공통 검증.
    - equipment_id
    - target_type
    - action_type
    모두 있어야 하고,
    expect_target이 있을 경우 target_type 일치 여부도 검증한다.
    """

    if not isinstance(data, dict):
        return False, "JSON 요청 형식이 잘못되었습니다."

    equipment_id = data.get("equipment_id")
    target_type = data.get("target_type")
    action_type = data.get("action_type")

    if not equipment_id:
        return False, "equipment_id 가 필요합니다."
    if not target_type:
        return False, "target_type 이 필요합니다."
    if not action_type:
        return False, "action_type 이 필요합니다."

    # target_type 강제(AMR/ARM/PLC API 별로 제한 가능)
    if expect_target and target_type != expect_target:
        return False, f"target_type 은 '{expect_target}' 이어야 합니다."

    return True, ""