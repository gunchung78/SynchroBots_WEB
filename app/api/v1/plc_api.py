# app/api/v1/plc_api.py

from flask import Blueprint, request, jsonify

plc_api_bp = Blueprint("plc_api", __name__)


@plc_api_bp.route("/conveyor_sensor_check", methods=["POST"])
def conveyor_sensor_check():
    """
    OPC UA Worker → Flask Webhook
    config.SUBSCRIBE_NODES 에서 name='conveyor_sensor_check' 로 들어오는 값 처리
    """
    data = request.get_json(silent=True) or {}

    event = data.get("event")   # ex) "conveyor_sensor_check"
    value = data.get("value")   # ex) True / 0/1 / 기타 숫자, 문자열

    print(f"[PLC API] conveyor_sensor_check: event={event}, value={value}")

    # TODO: 나중에 여기서 카메라 Anomaly 체크 로직 기입
    print(f'최종 : {value}')
    return jsonify({
        "ok": True,
        "event": event,
        "value": value,
    }), 200


@plc_api_bp.route("/read_robotarm_sensor_check", methods=["POST"])
def read_robotarm_sensor_check():
    """
    OPC UA Worker → Flask Webhook
    config.SUBSCRIBE_NODES 에서 name='conveyor_sensor_check' 로 들어오는 값 처리
    """
    data = request.get_json(silent=True) or {}

    event = data.get("event")   # ex) "conveyor_sensor_check"
    value = data.get("value")   # ex) True / 0/1 / 기타 숫자, 문자열

    print(f"[PLC API] read_robotarm_sensor_check: event={event}, value={value}")

    # 값이 True로 전달 될 시 
    # AMR write_amr_go_move(이동명령 "pick_up_zone")
    # ARM write_arm_start(미션 시작 명령 )
    if(value == True):
        print(f'최종 : {value}')



    # TODO: 나중에 여기서 카메라 Anomaly 체크 로직 기입
   
    return jsonify({
        "ok": True,
        "event": event,
        "value": value,
    }), 200
