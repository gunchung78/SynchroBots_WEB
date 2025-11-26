# app/hardware/opcua/client.py

import asyncio
from asyncua import Client
from .config import OPCUA_SERVER_URL, OPCUA_NAMESPACE_URI, SUBSCRIBE_NODES
from .webhook import call_webhook


class SubHandler:
    """OPC UA datachange 콜백 → 각 노드의 webhook 호출"""

    def __init__(self, node_info_map):
        # nodeid -> config(dict: name, webhook, browse_path...)
        self.node_info_map = node_info_map

    def datachange_notification(self, node, val, data):
        info = self.node_info_map.get(node.nodeid)
        if not info:
            print(f"[OPCUA] unknown node {node}, val={val}")
            return

        name = info["name"]
        webhook_path = info["webhook"]
        print(f"[OPCUA] {name} changed -> {val} (webhook={webhook_path})")

        loop = asyncio.get_event_loop()
        loop.create_task(call_webhook(name, val, webhook_path))


async def run_opcua_worker():
    client = Client(url=OPCUA_SERVER_URL)

    try:
        await client.connect()
        print("[OPCUA] connected")

        idx = await client.get_namespace_index(OPCUA_NAMESPACE_URI)

        node_info_map = {}
        nodes = []

        for conf in SUBSCRIBE_NODES:
            path = [p.format(idx=idx) for p in conf["browse_path"]]
            node = await client.nodes.root.get_child(path)
            nodes.append(node)
            node_info_map[node.nodeid] = conf
            print(f"[OPCUA] subscribe target: {conf['name']} -> {node}")

        handler = SubHandler(node_info_map)
        sub = await client.create_subscription(500, handler)
        await sub.subscribe_data_change(nodes)

        print("[OPCUA] subscription started")

        # 연결 유지
        while True:
            await asyncio.sleep(1)

    except Exception as e:
        print(f"[OPCUA] error: {e}")
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
        print("[OPCUA] disconnected")
