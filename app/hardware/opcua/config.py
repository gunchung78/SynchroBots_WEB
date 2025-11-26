# app/hardware/opcua/config.py

OPCUA_SERVER_URL = "opc.tcp://172.30.1.61:4840/freeopcua/server/"
OPCUA_NAMESPACE_URI = "http://examples.freeopcua.github.io"

# Flask 서버 베이스 URL (같은 서버라면 127.0.0.1)
API_BASE = "http://172.30.1.29:80"

# ─────────────────────────────────────
# 여기만 수정해서 구독 노드들을 관리
# ─────────────────────────────────────
SUBSCRIBE_NODES = [
    {
        "name": "agv_issue",
        "browse_path": ["0:Objects", "{idx}:MyObject", "{idx}:AGV_Issue"],
        "webhook": "/api/v1/opcua/agv_issue",  # Flask 라우트
    },
    {
        "name": "vision_capture",
        "browse_path": ["0:Objects", "{idx}:MyObject", "{idx}:Vision_Capture"],
        "webhook": "/api/v1/opcua/vision_capture",
    },
    # 필요하면 계속 추가
    # {
    #   "name": "plc_event",
    #   "browse_path": [...],
    #   "webhook": "/api/v1/opcua/plc_event",
    # },
]