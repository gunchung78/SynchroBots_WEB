# run_all.py
import subprocess
import sys
import time

processes = []


def main():
    # 실행할 명령들 정의
    cmds = [
        [sys.executable, "run.py"],              # Flask 서버
        [sys.executable, "run_opcua_worker.py"]  # OPC UA 워커
    ]

    # 각 프로세스 실행
    for cmd in cmds:
        print(f"[launcher] start: {' '.join(cmd)}")
        p = subprocess.Popen(cmd)
        processes.append(p)

    try:
        # 하나라도 죽을 때까지 대기
        while True:
            alive = [p for p in processes if p.poll() is None]
            if not alive:
                print("[launcher] all processes exited")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[launcher] Ctrl+C detected, terminating children...")
        for p in processes:
            if p.poll() is None:
                p.terminate()
        # 깔끔하게 종료 안 되면 kill
        time.sleep(3)
        for p in processes:
            if p.poll() is None:
                p.kill()


if __name__ == "__main__":
    main()
