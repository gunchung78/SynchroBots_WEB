# app/hardware/opcua/client.py

import asyncio
from asyncua import Client

from .config import OPCUA_SERVER_URL, OPCUA_NAMESPACE_URI, SUBSCRIBE_NODES
from .webhook import call_webhook


# OPC UA 서버가 끊겼을 때 재접속까지 기다리는 시간 (초)
RECONNECT_DELAY_SEC = 10


class SubHandler:
    """
    OPC UA Subscription Handler

    - datachange_notification: 노드 값 변경 이벤트 → Flask 내부 API(webhook) 호출
    - status_change_notification: 구독/세션 상태 변화 이벤트 → 재접속 트리거
    """

    def __init__(self, node_info_map, disconnect_event: asyncio.Event, loop: asyncio.AbstractEventLoop):
        # nodeid -> config(dict: name, webhook, browse_path...)
        self.node_info_map = node_info_map
        self.disconnect_event = disconnect_event
        self.loop = loop

    # 노드 값 변경 콜백
    def datachange_notification(self, node, val, data):
        info = self.node_info_map.get(node.nodeid)
        if not info:
            print(f"[OPCUA] unknown node {node}, val={val}")
            return

        name = info["name"]
        webhook_path = info["webhook"]
        print(f"[OPCUA] {name} changed -> {val} (webhook={webhook_path})")

        # 비동기 webhook 호출
        self.loop.create_task(call_webhook(name, val, webhook_path))

    # 구독/세션 상태 변화 콜백
    def status_change_notification(self, status):
        """
        서버 재부팅, 세션 문제 등으로 구독 상태가 바뀌면 asyncua가 이 함수를 호출한다.
        여기서 disconnect_event를 set 해서, 한 세션을 종료시키고
        바깥 run_opcua_worker 루프가 재접속하도록 만든다.
        """
        print(f"[OPCUA] subscription status changed: {status!r}")
        # 다른 스레드에서 호출될 수 있으므로 thread-safe 방식으로 이벤트 set
        self.loop.call_soon_threadsafe(self.disconnect_event.set)


async def run_single_session(client: Client):
    """
    한 번의 OPC UA 세션을 구성한다.

    1. namespace index 조회
    2. SUBSCRIBE_NODES 기준으로 Node 찾기
    3. Subscription 생성 + datachange 구독
    4. status_change_notification 에서 disconnect_event 가 set 될 때까지 대기

    서버가 내려가거나, 세션/구독 상태가 바뀌면 status_change_notification 이 호출되어
    disconnect_event 가 set 되고, 이 함수는 return 된다.
    """
    loop = asyncio.get_running_loop()

    # namespace index 가져오기
    idx = await client.get_namespace_index(OPCUA_NAMESPACE_URI)

    node_info_map = {}
    nodes = []

    # config에 정의된 모든 노드 구독 준비
    for conf in SUBSCRIBE_NODES:
        path = [p.format(idx=idx) for p in conf["browse_path"]]
        node = await client.nodes.root.get_child(path)
        nodes.append(node)
        node_info_map[node.nodeid] = conf
        print(f"[OPCUA] subscribe target: {conf['name']} -> {node}")

    # 세션 종료 트리거용 이벤트
    disconnect_event = asyncio.Event()

    # 구독 핸들러 등록
    handler = SubHandler(node_info_map, disconnect_event, loop)
    sub = await client.create_subscription(500, handler)  # 500 ms 주기
    await sub.subscribe_data_change(nodes)

    print("[OPCUA] subscription started")

    # 여기서 대기하다가, 서버가 죽거나 세션 상태가 바뀌면
    # status_change_notification 에서 disconnect_event 가 set 됨
    await disconnect_event.wait()
    print("[OPCUA] disconnect_event set → single session 종료")


async def run_opcua_worker():
    """
    OPC UA Worker 메인 루프.

    - 무한 루프에서 OPC UA 서버에 연결을 시도
    - 연결되면 run_single_session() 으로 구독 및 이벤트 처리
    - 서버 재부팅 / 세션 에러 등으로 끊기면 10초 후 재접속
    """
    while True:
        client = Client(url=OPCUA_SERVER_URL)

        try:
            print(f"[OPCUA] trying to connect to {OPCUA_SERVER_URL} ...")
            await client.connect()
            print("[OPCUA] connected")

            # 한 세션 유지 (구독 + status_change 대기)
            await run_single_session(client)

        except asyncio.CancelledError:
            # 외부에서 작업을 종료시킨 경우
            print("[OPCUA] worker cancelled, exiting...")
            break

        except Exception as e:
            # 연결 실패, 세션 내부 예외 등
            print(f"[OPCUA] error: {e}")

        finally:
            # 어떤 경우든 client 정리
            try:
                await client.disconnect()
            except Exception:
                pass
            print(f"[OPCUA] disconnected. retry in {RECONNECT_DELAY_SEC} sec...")

        # 여기까지 왔다는 건 세션이 끝난 상태 → 일정 시간 후 재접속 시도
        await asyncio.sleep(RECONNECT_DELAY_SEC)
