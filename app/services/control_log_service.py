# app/services/control_log_service.py

import json
from typing import Optional, Dict, Any

from app import db
from app.models.dashboard import ControlLog  # 실제 모델 경로/이름에 맞게 수정

def log_control_action(
    *,
    equipment_id: Optional[str],
    target_type: str,          # 'AMR' | 'PLC' | 'ARM' | 'SYSTEM'
    action_type: str,
    operator_name: Optional[str] = None,
    source: str = "API",       # 'WEB' | 'API' | 'SCRIPT'
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