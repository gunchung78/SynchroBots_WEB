# app/api/v1/plc_api.py

from flask import Blueprint, request, jsonify
import traceback
from app.hardware.opcua.sender import (
    write_amr_go_move,
    write_arm_go_move,
    write_ok_ng_value
)

from app.hardware.vision_anomaly import run_anomaly_inspection_once
from app import db
from app.models.opcua import (
    MissionCameraLog
)

from app.services.control_log_service import log_control_action

plc_api_bp = Blueprint("plc_api", __name__)


@plc_api_bp.route("/conveyor_sensor_check", methods=["POST"])
def conveyor_sensor_check():
    try:
        data = request.get_json(force=True)
        value = data.get("value")

        if value == 'Ready':
            return jsonify({"action": "Ready pass"}), 200
        
        print(f"[PLC] conveyor_sensor_check webhook 수신: value={value}")

        # True가 아닐 경우 아무 동작 안함
        if not value:
            return jsonify({"ok": True, "action": "no_action"}), 200

        # vision Check 로직 기입
        # ------------------ 1) 비전 검사 실행 ------------------
        inspection = run_anomaly_inspection_once()

        log = MissionCameraLog(
            equipment_id="SENSER01",
            mode="ANOMALY",
            # image_data=inspection["image_bytes"],
            module_type=inspection["module_type"],
            classification_confidence=inspection["classification_confidence"],
            anomaly_flag=inspection["anomaly_flag"],
            anomaly_score=inspection["anomaly_score"],
            decision=inspection["decision"],
        )
        db.session.add(log)
        db.session.commit()

        # ------------------ 3) PLC에 Anomaly 결과 회신 ------------------
        # 1) anomaly_flag → 'NG' / 'OK' 변환
        flag = inspection["anomaly_flag"]
        anomaly_str = "NG" if flag else "OK"
        write_ok_ng_value({"Anomaly": anomaly_str})

        return jsonify(
            {
                "ok": True,
                "action": "conveyor_sensor_triggered",
                "vision": {
                    "module_type": inspection["module_type"],
                    "anomaly_flag": inspection["anomaly_flag"],
                    "anomaly_score": inspection["anomaly_score"],
                    "decision": inspection["decision"],
                    "log_camera_id": log.log_camera_id,
                },
            }
        ), 200

    except Exception as e:
        print(f"[PLC] conveyor_sensor_check 오류: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@plc_api_bp.route("/robotarm_sensor_check", methods=["POST"])
def robotarm_sensor_check():
    """
    OPC UA → PLC read_robotarm_sensor_check 값 Webhook
    value == True → AMR + ARM 동작 트리거
    """
    try:
        data = request.get_json(force=True)
        value = data.get("value")

        if value == 'Ready':
            return jsonify({"action": "Ready pass"}), 200
        
        print(f"[PLC] robotarm_sensor_check webhook 수신: value={value}")

        # True가 아닐 경우 아무 동작 안함
        if not value:
            return jsonify({"ok": True, "action": "no_action"}), 200

        # 1) AMR → pick_up_zone 이동
        amr_cmd = {"move_command": "pick_up_zone"}
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

        # 2) ARM → go_home (ready 상태로 복귀)
        # write_arm_go_move({"move_command": "go_home"})
        arm_cmd = {"move_command": "go_home"}
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

        return jsonify({
            "ok": True,
            "action": "amr_mission_state_triggered"
        }), 200

    except Exception as e:
        # traceback.print_exc()   # ★ 스택트레이스 전체 출력
        print(f"[PLC] robotarm_sensor_check 오류: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500