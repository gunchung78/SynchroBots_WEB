# app/hardware/opcua/config.py

OPCUA_SERVER_URL = "opc.tcp://172.30.1.61:0630/freeopcua/server/"
OPCUA_NAMESPACE_URI = "http://examples.freeopcua.github.io"

# Flask 서버 베이스 URL (같은 서버라면 127.0.0.1)
API_BASE = "http://172.30.1.29:80"

# ─────────────────────────────────────
# 여기만 수정해서 구독 노드들을 관리
# ─────────────────────────────────────
SUBSCRIBE_NODES = [

    # PLC
    #컨베이어 센서 체크 - Anomaly 체크 PLC : write_ok_ng_value("{"Anomaly" : true}")
    {   
        "name": "conveyor_sensor_check",
        "browse_path": ["0:Objects", "{idx}:PLC", "{idx}:read_conveyor_sensor_check"],
        "webhook": "/api/v1/plc/conveyor_sensor_check",  
    },
    #로봇암 센서 체크 - AMR : write_amr_go_move("pick_up_zone")
    {
        "name": "robotarm_sensor_check",
        "browse_path": ["0:Objects", "{idx}:PLC", "{idx}:read_robotarm_sensor_check"],
        "webhook": "/api/v1/plc/robotarm_sensor_check",  
    },


    # ARM
    # Detection 체크용 이미지 및 로그 전달(* 이미지여부를 체크하고 DB에 로그 데이터를 저장하기 위해 WEB에서 파일 및 데이터를 체크 후 DB에 저장)
    {
        "name": "arm_img",
        "browse_path": ["0:Objects", "{idx}:ARM", "{idx}:read_arm_img"],
        "webhook": "/api/v1/arm/arm_img",
    },
    # Place 단건 수행 완료 알림 - PLC : write_ready_state()
    {
        "name": "arm_place_single",
        "browse_path": ["0:Objects", "{idx}:ARM", "{idx}:read_arm_place_single"],
        "webhook": "/api/v1/arm/arm_place_single", 
    },
     # Place 전체 수행 완료 알림 - AMR : write_amr_go_positions("{"object_info" : "['esp32','motordriver','powersuplpy']"}")
    {
        "name": "arm_place_completed",
        "browse_path": ["0:Objects", "{idx}:ARM", "{idx}:read_arm_place_completed"],
        "webhook": "/api/v1/arm/arm_place_completed", 
    },


    # AMR
    # 미션 상태 전송 - 모든 미션 완료, 장애물 혹은 에러로 인한 이동불가상태, 픽업존 도착시(딜레이 감소)
    # 1.모든 미션 완료 - AMR : write_amr_go_move("go_home") 
    # 2.픽업존 도착(robotarm_sensor_check 일때만 픽업존 이동) - ARM : write_arm_go_move("mission_start")
    # 3.장애물 혹은 에러로 인한 이동불가상태 - AMR : write_amr_go_move("go_home")
    {
        "name": "write_amr_mission_state",
        "browse_path": ["0:Objects", "{idx}:AMR", "{idx}:read_amr_mission_state"],
        "webhook": "/api/v1/amr/conveyor_sensor_check",  
    },

]