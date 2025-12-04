# run.py
from flask import Flask
import config
# from app.hardware.Modbus import ModbusMonitor
import os
import time
from app import create_app

app = create_app()
# print(app.url_map)  # 이 줄 추가해서 어떤 URL이 등록됐는지 확인

# 간단한 상태 저장(선택)
last_triggers = []

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=True, use_reloader=True)
