from flask import Blueprint, request, jsonify, current_app
from app.models.dashboard import EquipmentInfo, ControlLog
from app import db
from sqlalchemy import func

from app.hardware.opcua.sender import (
    write_amr_go_move,
    write_arm_go_move,
    write_ready_state
)
from app.models.control import PlcControlState                 

from app.services.control_log_service import log_control_action, validate_control_payload

control_api_bp = Blueprint("control_api_bp", __name__)


@control_api_bp.get("/equipment/status")
def get_equipment_status():
    """
    제어 패널에서 사용할 장비 상태 조회 API
    CAMERA 장비는 제어 대상이 아니므로 응답에서 제외함.
    """

    ids_param = request.args.get("ids", "").strip()
    q = EquipmentInfo.query

    if ids_param:
        id_list = [x.strip() for x in ids_param.split(",") if x.strip()]
        if id_list:
            q = q.filter(EquipmentInfo.equipment_id.in_(id_list))

    # 🔥 CAMERA, SENSER 제외
    q = q.filter(~EquipmentInfo.equipment_id.like("CAMERA%"))
    q = q.filter(~EquipmentInfo.equipment_id.like("SENSER%"))
    q = q.filter(~EquipmentInfo.equipment_id.like("CONVEYOR%"))

    rows = q.all()

    data = {}
    for r in rows:
        data[r.equipment_id] = {
            "equipment_type": r.equipment_type,
            "equipment_name": r.equipment_name,
            "status": r.status,
            "is_online": bool(r.is_online),
            "location": r.location,
            "last_seen_at": (
                r.last_seen_at.isoformat() if r.last_seen_at else None
            ),
        }

    return jsonify(data)


@control_api_bp.post("/amr")
def control_amr():
    """
    AGV(AMR) 제어 API
    지금 단계: payload 검증 + control_logs INSERT 만 수행
    """
    data = request.get_json(force=True, silent=True) or {}

    ok, msg = validate_control_payload(data, expect_target="AMR")
    if not ok:
        return jsonify(ok=False, error=msg), 400

    equipment_id = data.get("equipment_id")
    target_type = data.get("target_type")    # 보통 'AMR'
    action_type = data.get("action_type")    # 예: 'AMR_ESTOP'
    trigger_event = data.get("trigger_event")

    if action_type == "AMR_ESTOP":
        cmd = {"move_command": "stop"}
        status_after = "ESTOP"   # ✅ 저장할 equipment_info.status
    elif action_type == "AMR_RESTART":
        cmd = {"move_command": "go_home"}
        status_after = "RUN"     # ✅ 저장할 equipment_info.status
    else:
        return jsonify(ok=False, error="invalid action_type"), 400

    status = "SUCCESS"
    msg = None
    
    try:
        write_amr_go_move(cmd)
    except Exception as e:
        status = "FAIL"
        msg = "OPCUA access fail "

    # ✅ 제어 성공 시 equipment_info.status 업데이트
    if status == "SUCCESS":
        try:
            update_equipment_status(equipment_id, status_after)
        except Exception:
            current_app.logger.exception("[CONTROL][AMR] status update fail")

    log_control_action(
        equipment_id=equipment_id,
        target_type=target_type,
        action_type="amr_go_move",
        operator_name=None,        # 자동 제어면 SYSTEM, 수동이면 current_user 등
        source="WEB",
        request_payload=cmd,
        result_status=status,
        result_message=msg,
        trigger_event=trigger_event,
    )

    current_app.logger.info(
        "[CONTROL][AGV] equipment_id=%s action_type=%s payload=%s",
        equipment_id,
        action_type,
        data,
    )

    # 나중에 log_id를 service에서 리턴하도록 바꾸고 싶으면 거기서 확장
    return jsonify(ok=True)


@control_api_bp.post("/robot")
def control_robot():
    data = request.get_json(force=True, silent=True) or {}

    ok, msg = validate_control_payload(data, expect_target="ARM")
    if not ok:
        return jsonify(ok=False, error=msg), 400

    equipment_id = data.get("equipment_id")
    target_type = data.get("target_type")    # 'ARM'
    action_type = data.get("action_type")    # 예: 'ARM_ESTOP'
    trigger_event = data.get("trigger_event")

    status_after = None

    if action_type == "ARM_ESTOP":
        cmd = {"move_command": "stop"}
        status_after = "ESTOP"
    elif action_type == "ARM_HOME":
        cmd = {"move_command": "go_home"}
        status_after = "RUN"  # 원하면 지정, 아니면 None
    elif action_type == "ARM_RESTART":
        cmd = {"move_command": "restart"}
        status_after = "RUN"
    else:
        return jsonify(ok=False, error="invalid action_type"), 400

    status = "SUCCESS"
    msg = None
    
    try:
        write_arm_go_move(cmd)
    except Exception as e:
        status = "FAIL"
        msg = "OPCUA access fail "

    # ✅ 제어 성공 + status_after 지정된 경우에만 status 업데이트
    if status == "SUCCESS" and status_after:
        try:
            update_equipment_status(equipment_id, status_after)
        except Exception:
            current_app.logger.exception("[CONTROL][ARM] status update fail")
        
    log_control_action(
        equipment_id=equipment_id,
        target_type=target_type,
        action_type="arm_go_move",
        operator_name=None,        # 자동 제어면 SYSTEM, 수동이면 current_user 등
        source="WEB",
        request_payload=cmd,
        result_status=status,
        result_message=msg,
        trigger_event=trigger_event,
    )

    current_app.logger.info(
        "[CONTROL][ARM] equipment_id=%s action_type=%s payload=%s",
        equipment_id,
        action_type,
        data,
    )

    return jsonify(ok=True)

def update_equipment_status(equipment_id: str, new_status: str):
    """
    equipment_info.status만 업데이트 (스키마 변경 없이)
    - 성공한 제어 결과를 화면에 반영하기 위한 용도
    """
    if not equipment_id:
        return

    eq = EquipmentInfo.query.get(equipment_id)
    if not eq:
        return

    eq.status = new_status
    # updated_at은 테이블에서 ON UPDATE current_timestamp(6)로 자동 갱신됨
    db.session.commit()


@control_api_bp.get("/logs")
def get_control_logs():
    """
    제어 패널 우측 로그 박스용 (페이징)
    - query: source=WEB&limit=50&offset=0
    - return:
      {
        "items": [...],
        "paging": {"total": 1234, "limit": 50, "offset": 0}
      }
    """
    source = request.args.get("source", "WEB")

    # limit / offset
    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        limit = 50
    limit = max(1, min(limit, 200))  # 과도한 요청 방지(원하면 숫자 조절)

    try:
        offset = int(request.args.get("offset", 0))
    except ValueError:
        offset = 0
    offset = max(0, offset)

    q = ControlLog.query

    if source:
        q = q.filter(ControlLog.source == source)

    # ✅ 전체 개수(페이징용)
    total = q.with_entities(func.count(ControlLog.control_id)).scalar() or 0

    # ✅ 페이지 데이터
    rows = (
        q.order_by(ControlLog.created_at.desc())
         .offset(offset)
         .limit(limit)
         .all()
    )

    items = []
    for r in rows:
        items.append({
            "control_id": r.control_id,
            "equipment_id": r.equipment_id,
            "target_type": r.target_type,          # AMR / ARM / PLC / SYSTEM
            "action_type": r.action_type,          # amr_go_move ...
            "result_status": r.result_status,      # SUCCESS / FAIL / TIMEOUT
            "result_message": r.result_message,
            "trigger_event": r.trigger_event,      # USER_CLICK_...
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return jsonify({
        "items": items,
        "paging": {
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    })



@control_api_bp.get("/plc/state")
def get_plc_state():
    """
    PLC 상태 조회 API
    - /logs 와 동일한 스타일: rows -> result(list) -> jsonify(result)
    - equipment_id를 주면 0~1행 반환
    - equipment_id 없으면 PLC 상태 전체(여러 장비) 반환도 가능
    """
    equipment_id = request.args.get("equipment_id", "").strip()

    q = PlcControlState.query

    # equipment_id가 있으면 해당 장비만
    if equipment_id:
        q = q.filter(PlcControlState.equipment_id == equipment_id)

    rows = q.all()

    result = []
    for r in rows:
        result.append({
            "equipment_id": r.equipment_id,
            "run_mode": r.run_mode,
            "direction": r.direction,
            "frequency": float(r.frequency) if r.frequency is not None else None,
            "acceleration": r.acceleration,
            "deceleration": r.deceleration,
            "remark1": r.remark1,
            "remark2": r.remark2,
            "remark3": r.remark3,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        })

    return jsonify(result)


@control_api_bp.post("/plc/state")
def save_plc_state():
    data = request.get_json(force=True, silent=True) or {}

    equipment_id = (data.get("equipment_id") or "").strip()
    if not equipment_id:
        return jsonify(ok=False, error="equipment_id required"), 400

    row = PlcControlState.query.get(equipment_id)
    if not row:
        row = PlcControlState(equipment_id=equipment_id)
        db.session.add(row)

    # 부분 업데이트 (넘어온 키만 반영)
    if "run_mode" in data:
        v = data.get("run_mode")
        if v not in ("STOP", "RUN"):
            return jsonify(ok=False, error="invalid run_mode"), 400
        row.run_mode = v

        if v == "STOP":
            # 1) AMR → pick_up_zone 이동
            cmd = {"move_command": "conveyor_stop"}
            status = "SUCCESS"
            msg = None

            try:
                write_ready_state(cmd)
            except Exception as e:
                status = "FAIL"
                msg = "OPCUA access fail "

            log_control_action(
                equipment_id=equipment_id,
                target_type="PLC",
                action_type="ready_state",
                operator_name="SYSTEM",        # 자동 제어면 SYSTEM, 수동이면 current_user 등
                source="WEB",
                request_payload=cmd,
                result_status=status,
                result_message=msg,
            )

    if "direction" in data:
        v = data.get("direction")
        if v not in ("FORWARD", "REVERSE"):
            return jsonify(ok=False, error="invalid direction"), 400
        row.direction = v

    def _none_if_empty(v):
        return None if v in (None, "", "null") else v

    if "frequency" in data:
        v = _none_if_empty(data.get("frequency"))
        if v is None:
            row.frequency = None
        else:
            try:
                row.frequency = float(v)
            except Exception:
                return jsonify(ok=False, error="invalid frequency"), 400

    if "acceleration" in data:
        v = _none_if_empty(data.get("acceleration"))
        if v is None:
            row.acceleration = None
        else:
            try:
                row.acceleration = int(v)
            except Exception:
                return jsonify(ok=False, error="invalid acceleration"), 400

    if "deceleration" in data:
        v = _none_if_empty(data.get("deceleration"))
        if v is None:
            row.deceleration = None
        else:
            try:
                row.deceleration = int(v)
            except Exception:
                return jsonify(ok=False, error="invalid deceleration"), 400

    # 비고도 필요한 경우에만
    for k in ("remark1", "remark2", "remark3"):
        if k in data:
            setattr(row, k, data.get(k))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("[PLC_STATE] commit fail: %s", e)
        return jsonify(ok=False, error="db commit fail"), 500

    return jsonify(ok=True)


@control_api_bp.post("/plc/manual_start")
def plc_manual_start():
    data = request.get_json(force=True, silent=True) or {}

    equipment_id = data.get("equipment_id")  # 로그에만 쓰고, 없어도 동작 가능하게
    trigger_event = data.get("trigger_event")


    # 1) AMR → pick_up_zone 이동
    cmd = {"move_command": "conveyor_move"}
    status = "SUCCESS"
    msg = None

    try:
        write_ready_state(cmd)
    except Exception as e:
        status = "FAIL"
        msg = "OPCUA access fail "

    log_control_action(
        equipment_id=equipment_id,
        target_type="PLC",
        action_type="ready_state",
        operator_name="SYSTEM",        # 자동 제어면 SYSTEM, 수동이면 current_user 등
        source="WEB",
        request_payload=cmd,
        result_status=status,
        result_message=msg,
    )

    return jsonify(ok=(status == "SUCCESS"), error=msg)