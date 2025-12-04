# app/api/v1/amr_api.py

from flask import Blueprint, request, jsonify
from app.hardware.opcua.sender import (
    write_amr_go_move,
    write_arm_go_move,
    write_amr_go_move
)
import json
from app.services.control_log_service import log_control_action
amr_api_bp = Blueprint("amr_api", __name__)


@amr_api_bp.route("/amr_mission_state", methods=["POST"])
def amr_mission_state():
    try:
        data = request.get_json(force=True)
        value = data.get("value")
       
        if value == 'Ready':
            return jsonify({"action": "Ready pass"}), 200
        
        print(f"[AMR] amr_mission_state webhook 수신: value={value}")

         # 2) value를 dict 형태로 정규화
        status = None

        if isinstance(value, dict):
            # 이미 {"status": "..."} 형태인 경우
            status = value.get("status")

        elif isinstance(value, str):
            # 문자열이면 JSON 파싱 시도
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    status = parsed.get("status")
                else:
                    # 그냥 "DONE" 같은 문자열인 경우
                    status = parsed
            except json.JSONDecodeError:
                # JSON이 아니면 그냥 문자열 자체를 status로 사용
                status = value

        # 3) 유효한 status 없으면 no_action
        if not status:
            return jsonify({"ok": True, "action": "no_action"}), 200

        if status == "DONE":
            # 예: AGV가 작업 완료 → 다음 명령
            # write_amr_go_move({"move_command": "go_home"})
            return jsonify({"ok": True, "action": "mission_done"}), 200

        elif status == "PICK":
            # 예: 로봇암 픽업 시작
            # write_arm_go_move({"move_command": "mission_start"})

            arm_cmd = {"move_command": "mission_start"}
            arm_status = "SUCCESS"
            arm_msg = None

            try:
                write_arm_go_move(arm_cmd)
            except Exception as e:
                arm_status = "FAIL"
                arm_msg = "OPCUA access fail "

            log_control_action(
                equipment_id="ARM01",
                target_type="ARM",
                action_type="arm_go_move",
                operator_name="SYSTEM",        # 자동 제어면 SYSTEM, 수동이면 current_user 등
                source="API",
                request_payload=arm_cmd,
                result_status=arm_status,
                result_message=arm_msg,
            )

            return jsonify({"ok": True, "action": "pick_start"}), 200

        elif status == "ERR":
            # 예: AGV 오류 → AGV 홈으로
            # write_amr_go_move({"move_command": "go_home"})
            amr_cmd = {"move_command": "go_home"}
            amr_status = "SUCCESS"
            amr_msg = None

            try:
                write_amr_go_move(amr_cmd)
            except Exception as e:
                amr_status = "FAIL"
                amr_msg = "OPCUA access fail "

            log_control_action(
                equipment_id="AMR01",
                target_type="AMR",
                action_type="amr_go_move",
                operator_name="SYSTEM",        # 자동 제어면 SYSTEM, 수동이면 current_user 등
                source="API",
                request_payload=amr_cmd,
                result_status=amr_status,
                result_message=amr_msg,
            )

            return jsonify({"ok": True, "action": "error_handle"}), 200

    except Exception as e:
        print(f"[AMR] amr_mission_state 오류: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500
