# run_opcua_worker.py

import asyncio
from app.hardware.opcua.client import run_opcua_worker

if __name__ == "__main__":
    asyncio.run(run_opcua_worker())
