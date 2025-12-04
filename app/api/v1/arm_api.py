# app/api/v1/plc_api.py

from flask import Blueprint, request, jsonify
from app.hardware.opcua.sender import (
    write_ready_state,
    write_amr_go_positions,
)
from app.services.control_log_service import log_control_action

arm_api_bp = Blueprint("arm_api", __name__)


@arm_api_bp.route("/arm_img", methods=["POST"])
def arm_img():
    try:
        data = request.get_json(force=True)
        value = data.get("value")

        if value == 'Ready':
            return jsonify({"action": "Ready pass"}), 200

        print(f"[ARM] arm_img webhook 수신: value={value}")

        # True가 아닐 경우 아무 동작 안함
        if not value:
            return jsonify({"ok": True, "action": "no_action"}), 200
        # 이미지 체크 및 데이터 저장

        return jsonify({
            "ok": True,
            "action": "arm_img_triggered"
        }), 200

    except Exception as e:
        print(f"[AMR] arm_img 오류: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500
    

@arm_api_bp.route("/arm_place_single", methods=["POST"])
def arm_place_single():
    try:
        data = request.get_json(force=True)
        value = data.get("value")

        if value == 'Ready':
            return jsonify({"action": "Ready pass"}), 200

        print(f"[ARM] arm_place_single webhook 수신: value={value}")

        # True가 아닐 경우 아무 동작 안함
        if not value:
            return jsonify({"ok": True, "action": "no_action"}), 200
        
        write_ready_state({"move_command": True})

        return jsonify({
            "ok": True,
            "action": "arm_place_single_triggered"
        }), 200

    except Exception as e:
        print(f"[AMR] arm_place_single 오류: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500
    


@arm_api_bp.route("/arm_place_completed", methods=["POST"])
def arm_place_completed():
    try:
        data = request.get_json(force=True)
        value = data.get("value")

        if value == 'Ready':
            return jsonify({"action": "Ready pass"}), 200
        
        print(f"[ARM] arm_place_completed webhook 수신: value={value}")

        # True가 아닐 경우 아무 동작 안함
        if not value:
            return jsonify({"ok": True, "action": "no_action"}), 200
        
        # write_amr_go_positions({"object_info" : "['esp32']"})
        amr_cmd = {"object_info" : "esp32"}
        amr_status = "SUCCESS"
        amr_msg = None

        try:
            write_amr_go_positions(amr_cmd)
        except Exception as e:
            amr_status = "FAIL"
            amr_msg = "OPCUA access fail "

        log_control_action(
            equipment_id="AMR01",
            target_type="AMR",
            action_type="amr_go_positions",
            operator_name="SYSTEM",        # 자동 제어면 SYSTEM, 수동이면 current_user 등
            source="API",
            request_payload=amr_cmd,
            result_status=amr_status,
            result_message=amr_msg,
        )

        return jsonify({
            "ok": True,
            "action": "arm_place_completed_triggered"
        }), 200

    except Exception as e:
        print(f"[AMR] arm_place_completed 오류: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500