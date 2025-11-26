import asyncio
from asyncua import Client, ua
async def main():
    # 1. 서버 엔드포인트 주소 설정 (서버 PC의 실제 IP 주소로 변경)
    server_url = "opc.tcp://172.30.1.61:4840/freeopcua/server/"
    client = Client(url=server_url)
    # client.set_security(ua.SecurityPolicyType.NoSecurity)
    try:
        await client.connect()
        print(f"서버 접속 성공: {server_url}")
        # 2. 데이터 노드 탐색
        uri = "http://examples.freeopcua.github.io"
        idx = await client.get_namespace_index(uri)
        # 노드 1: 클라이언트가 쓰는 노드
        client_write_node = await client.nodes.root.get_child([
            "0:Objects",
            f"{idx}:MyObject",
            f"{idx}:Client_Write_To_Server"
        ])
        # 노드 2: 서버가 업데이트하는 노드 (클라이언트는 읽기만 함)
        server_update_node = await client.nodes.root.get_child([
            "0:Objects",
            f"{idx}:MyObject",
            f"{idx}:Server_Update_To_Client"
        ])
        print("두 개의 노드 ID 획득 성공.")
        # 3. 데이터 송수신 루프
        command_count = 1
        while True:
            # 3-1. 서버로부터 값 읽기 (Server -> Client 방향)
            current_server_update = await server_update_node.read_value()
            print(f":별: 서버 업데이트 값 수신: {current_server_update}")
            # 3-2. 서버로 값 쓰기 (Client -> Server 방향)
            write_command = f"COMMAND{command_count}"
            await client_write_node.write_value(write_command)
            print(f":로켓: 서버로 명령 전송 (Client_Write_To_Server): {write_command}")
            command_count += 1
            await asyncio.sleep(5)
    except Exception as e:
        print(f"OPC UA 통신 오류 발생: {e}")
    finally:
        if client:
            await client.disconnect()
            print("서버 접속 종료")
if  __name__ == "__main__":
    asyncio.run(main())