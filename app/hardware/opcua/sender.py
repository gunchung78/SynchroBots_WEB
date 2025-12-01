# app/hardware/opcua/command_client.py

import asyncio
from asyncua import Client
from .config import OPCUA_SERVER_URL, OPCUA_NAMESPACE_URI


async def _write_clientA_data(value: object, dir: str, node: str):
    """
    ClientA_Write_Data 노드에 value 한 번 쓰고 연결 종료.
    (비동기 내부용)
    """
    client = Client(url=OPCUA_SERVER_URL)
    try:
        await client.connect()
        print("[OPCUA] write client connected")

        idx = await client.get_namespace_index(OPCUA_NAMESPACE_URI)

        write_node = await client.nodes.root.get_child([
            "0:Objects",
            f"{idx}:{dir}",
            f"{idx}:{node}",
        ])

        print(f"[OPCUA] write node: {write_node}")
        await write_node.write_value(value)
        print(f"[OPCUA] wrote value={value} to ClientA_Write_Data")

    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
        print("[OPCUA] write client disconnected")


def write_clientA_data(value: int):
    """
    Flask 같은 sync 환경에서 편하게 쓰기 위한 래퍼.
    """
    asyncio.run(_write_clientA_data(value))
