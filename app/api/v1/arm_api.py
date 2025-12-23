# app/api/v1/plc_api.py

from flask import Blueprint, request, jsonify, current_app
import os
import json
import base64
import numpy as np
import time
import cv2
from app import db
from app.models.opcua import (
    MissionCameraLog
)
from app.hardware.opcua.sender import (
    write_ready_state,
    write_amr_go_positions,
)
from app.services.mission_service import (
    get_latest_mission_id_for_equipment,
    get_arm_place_logs_for_mission,
)
from app.services.control_log_service import log_control_action

arm_api_bp = Blueprint("arm_api", __name__)

# 프로젝트 루트 기준으로 경로 잡기
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# DB에 넣을 상대경로 (프로젝트 루트 기준)
LOG_REL_DIR = os.path.join("data", "visions", "logs", "Joint")

# 이미지 파일 저장용
ARM_LOG_DIR = os.path.join(BASE_DIR, LOG_REL_DIR)
os.makedirs(ARM_LOG_DIR , exist_ok=True)


@arm_api_bp.route("/send_arm_json", methods=["POST"])
def arm_img():
    try:
        data = request.get_json(force=True)
        value = data.get("value")

        if value == 'Ready':
            return jsonify({"action": "Ready pass"}), 200

        print(f"[ARM] arm_img webhook 수신: value={value}")

        data_string = value
        # value 가 문자열(JSON)인 경우 / dict 인 경우 둘 다 처리
        if isinstance(value, str):
            payload = json.loads(value)
        else:
            payload = value

        # -----------------------------
        # 1) JSON 필드 파싱
        # -----------------------------
        module_type = payload.get("module_type")                  # 예: "Mission_State"
        cls_conf = float(payload.get("classification_confidence") or 0.0)
        status = payload.get("status")                            # 예: "arm_mission_success"
        base64_img_str = payload.get("img")                       # 매우 긴 base64 문자열
        pick_coord = json.dumps(payload["pick_coord"], ensure_ascii=False)
        img_name = None
        img_path = None

        # -----------------------------
        # 2) 이미지 복원 및 파일 저장ㅜ
        # -----------------------------
        if base64_img_str:
            try:
                # data:image/jpeg;base64,xxxx 이런 형식일 수도 있으니 ',' 이후만 사용
                if "," in base64_img_str:
                    base64_img_str = base64_img_str.split(",", 1)[1]

                # base64 → bytes
                img_bytes = base64.b64decode(base64_img_str)

                # bytes → numpy → cv2 이미지
                np_arr = np.frombuffer(img_bytes, np.uint8)
                decoded_img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                if decoded_img is None:
                    raise RuntimeError("cv2.imdecode() 결과가 None 입니다.")

                # 파일명: 모듈타입_타임스탬프.jpg
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                safe_module_type = module_type or "ARM"
                img_name = f"{safe_module_type}_{timestamp}.jpg"
                print(BASE_DIR)
                # 저장 디렉토리 생성
                os.makedirs(ARM_LOG_DIR, exist_ok=True)
                img_path = os.path.join(ARM_LOG_DIR, img_name)

                # 실제 파일 저장
                # ✅ OpenCV가 아니라, imencode + Python 파일 쓰기 방식 사용
                ok, buf = cv2.imencode(".jpg", decoded_img)
                if not ok:
                    raise RuntimeError("imencode('.jpg') failed in arm_img")

                with open(img_path, "wb") as f:
                    f.write(buf.tobytes())
                    
                print(f"[ARM] 이미지 저장 완료: {img_path}")

            except Exception as e:
                # 이미지 복원 오류는 로그만 남기고 계속 진행 (원하면 여기서 return 처리도 가능)
                print(f"[ARM] 이미지 복원/저장 중 오류: {e}")

        # -----------------------------
        # 3) DB mission_camera_logs Insert
        # -----------------------------
        image_path = os.path.join("SynchroBots_WEB", LOG_REL_DIR)
        log = MissionCameraLog(
            equipment_id="SENSER02",                     # ARM 장비 ID
            mode="JOINT_DETECTION",                  # enum('ANOMALY','JOINT_DETECTION') 중 하나
            image_name=img_name,                     # 없으면 None
            image_path=image_path,                     # 없으면 None
            module_type=module_type,                 # 예: "Mission_State" 등
            pick_coord=pick_coord,
            classification_confidence=cls_conf,
            anomaly_flag=None,                       # ARM에서는 사용 안 하므로 None
            anomaly_score=0.0,                       # ARM에서는 사용 안 하므로 0.0
        )

        db.session.add(log)
        db.session.commit()

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

        cmd = {"move_command": "conveyor_move"}
        status = "SUCCESS"
        msg = None
        
        try:
            write_ready_state(cmd)
        except Exception as e:
            status = "FAIL"
            msg = "OPCUA access fail "

        log_control_action(
            equipment_id="CONVEYOR01",
            target_type="PLC",
            action_type="move_command",
            operator_name="SYSTEM",        # 자동 제어면 SYSTEM, 수동이면 current_user 등
            source="API",
            request_payload=cmd,
            result_status=status,
            result_message=msg,
        )

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
        # 1) ARM 장비 ID (지금은 고정값으로 사용, 나중에 value 안에서 뽑아 써도 됨)
        arm_equipment_id = "ARM01"

        # 2) ARM01 이 가장 최근에 수행한 미션 ID 조회
        mission_id = get_latest_mission_id_for_equipment(arm_equipment_id)
        print(mission_id)
        if mission_id is None:
            current_app.logger.warning(
                "[ARM][arm_place_completed] no mission found for equipment_id=%s",
                arm_equipment_id,
            )
            return jsonify({"ok": False, "error": "no mission for ARM"}), 404
        # 3) 그 미션에 대한 PLACE 로그 목록 조회
        place_logs = get_arm_place_logs_for_mission(mission_id)

        # 4) module_type 기준으로 적재된 물체 목록 추출 (SUCCESS 인 것만, NULL 제외)
        object_list = []
        for log in place_logs:
            if log.get("result_status") != "SUCCESS":
                continue

            m = log.get("module_type")
            if not m:
                continue

            object_list.append(m)

        # PLACE 로그가 없거나 유효한 module_type 이 없으면 아무 것도 안 보냄
        if not object_list:
            current_app.logger.warning(
                "[ARM][arm_place_completed] no valid PLACE logs for mission_id=%s",
                mission_id,
            )
            return jsonify({"ok": False, "error": "no PLACE logs"}), 404

        # 5) AMR 로 보낼 payload 구성
        #    - 지금 구조에 맞게 string 또는 list 중 골라 사용
        #    - 예: ["ESP32", "MB102", "L298N"] -> 리스트 그대로 보내기
        amr_cmd = {
            "object_info": object_list,     # 필요하면 ",".join(object_list) 로 바꿔도 됨
        }
        print(amr_cmd)
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