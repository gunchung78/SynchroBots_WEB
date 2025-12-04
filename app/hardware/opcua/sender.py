# app/hardware/opcua/sender.py
import asyncio
import json
from asyncua import Client, ua
from .config import OPCUA_SERVER_URL, OPCUA_NAMESPACE_URI

# ==============================================================
# OPC UA NodeId 상수 (예시 값이므로 실제 서버 NodeId로 교체 필요)
# ==============================================================

# AMR
AMR_NODE_ID = "ns=2;i=1"                 # 예시: AMR 관련 Object 노드
AMR_GO_MOVE_METHOD_NODE_ID = "ns=2;i=15"        # 예시: write_amr_go_move 메서드 노드
AMR_GO_POSITIONS_METHOD_NODE_ID = "ns=2;i=16"   # 예시: write_amr_go_positions 메서드 노드

# ARM
ARM_NODE_ID = "ns=2;i=3"                 # 예시: ARM 관련 Object 노드
ARM_GO_MOVE_METHOD_NODE_ID = "ns=2;i=23"        # 예시: write_arm_go_move 메서드 노드

# PLC
PLC_NODE_ID = "ns=2;i=2"                 # 예시: PLC 관련 Object 노드
PLC_OK_NG_METHOD_NODE_ID = "ns=2;i=19"          # 예시: write_ok_ng_value 메서드 노드
PLC_READY_STATE_METHOD_NODE_ID = "ns=2;i=20"    # 예시: write_ready_state 메서드 노드


# ==============================================================
# 공통 Method Call 헬퍼
# ==============================================================

async def _call_method(object_node_id: str, method_node_id: str, arguments: list, debug_label: str = ""):
    """
    공통 OPC UA Method 호출 유틸리티
    - object_node_id: Object 노드 NodeId 문자열
    - method_node_id: Method 노드 NodeId 문자열
    - arguments: ua.Variant 리스트
    """
    client = Client(url=OPCUA_SERVER_URL)

    try:
        await client.connect()
        print(f"[OPCUA] connected for {debug_label or 'method'}")

        # 필요시 네임스페이스 인덱스 확인 (디버그용)
        idx = await client.get_namespace_index(OPCUA_NAMESPACE_URI)
        print(f"[OPCUA] namespace index = {idx}")

        obj_node = client.get_node(object_node_id)
        method_node = client.get_node(method_node_id)

        print(f"[OPCUA] obj_node    = {obj_node}")
        print(f"[OPCUA] method_node = {method_node}")
        print(f"[OPCUA] arguments   = {arguments}")

        result = await obj_node.call_method(method_node, *arguments)

        # 서버에서 (bool, string) 튜플을 주는 경우를 우선 가정
        try:
            is_success, status_message = result
            print(f"[OPCUA] {debug_label} result: success={is_success}, msg='{status_message}'")
        except Exception:
            print(f"[OPCUA] {debug_label} raw result: {result}")

        return result

    except Exception as e:
        print(f"[OPCUA] {debug_label} error: {e}")
        raise
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
        print(f"[OPCUA] disconnected ({debug_label})")


# ==============================================================
# AMR
# ==============================================================

# AMR 이동명령
async def _write_amr_go_move_async(payload: dict):
    """
    AMR 이동명령 Method 호출 (예: {"move_command": "go_home"} 등 JSON)
    """
    # 서버 Method 시그니처: (String json_command) 가정
    json_str = json.dumps(payload, ensure_ascii=False)
    args = [ua.Variant(json_str, ua.VariantType.String)]
    await _call_method(
        AMR_NODE_ID,
        AMR_GO_MOVE_METHOD_NODE_ID,
        args,
        debug_label="AMR go_move"
    )


def write_amr_go_move(payload: dict):
    """
    동기 컨텍스트(Flask API 등)에서 호출할 래퍼.
    내부에서는 async Method 호출을 수행.
    """
    asyncio.run(_write_amr_go_move_async(payload))


# AMR 운송 시작(운송물품 JSON으로 전달)
async def _write_amr_go_positions_async(payload: dict):

    json_str = json.dumps(payload, ensure_ascii=False)
    args = [ua.Variant(json_str, ua.VariantType.String)]
    await _call_method(
        AMR_NODE_ID,
        AMR_GO_POSITIONS_METHOD_NODE_ID,
        args,
        debug_label="AMR go_positions"
    )


def write_amr_go_positions(payload: dict):
    asyncio.run(_write_amr_go_positions_async(payload))


# ==============================================================
# ARM
# ==============================================================

# ARM 이동명령 
# "go_home"(초기위치 이동),
# "mission_start" (센서 체크시 - 작업실행),
# "stop" (정지)
async def _write_arm_go_move_async(payload: dict):
    """
    ARM 이동/상태 명령 (예: {"move_command": "go_home"} / {"move_command": "mission_start"} 등)
    """
    json_str = json.dumps(payload, ensure_ascii=False)
    args = [ua.Variant(json_str, ua.VariantType.String)]
    await _call_method(
        ARM_NODE_ID,
        ARM_GO_MOVE_METHOD_NODE_ID,
        args,
        debug_label="ARM go_move"
    )


def write_arm_go_move(payload: dict):
    asyncio.run(_write_arm_go_move_async(payload))


# ==============================================================
# PLC
# ==============================================================

# 컨베이어 센서 체크 후 Anomaly 체크 값 전달
async def _write_ok_ng_value_async(payload: dict):
    """
    컨베이어 센서 체크 후 Anomaly 결과 전달
    예: {"ok_ng": true} 또는 {"result": "OK"} 같은 JSON 문자열을 보내는 형태로 가정
    """
    json_str = json.dumps(payload, ensure_ascii=False)
    args = [ua.Variant(json_str, ua.VariantType.String)]
    await _call_method(
        PLC_NODE_ID,
        PLC_OK_NG_METHOD_NODE_ID,
        args,
        debug_label="PLC ok_ng_value"
    )


def write_ok_ng_value(payload: dict):
    asyncio.run(_write_ok_ng_value_async(payload))


# PLC 동작 명령
# 현재는 컨베이러 동작 "state": "c_move"
async def _write_ready_state_async(payload: dict):
    """
    PLC 동작/상태 명령
    예: {"state": "c_move"} / {"state": "stop"} 등 JSON 형태
    """
    json_str = json.dumps(payload, ensure_ascii=False)
    args = [ua.Variant(json_str, ua.VariantType.String)]
    await _call_method(
        PLC_NODE_ID,
        PLC_READY_STATE_METHOD_NODE_ID,
        args,
        debug_label="PLC ready_state"
    )


def write_ready_state(payload: dict):
    asyncio.run(_write_ready_state_async(payload))
