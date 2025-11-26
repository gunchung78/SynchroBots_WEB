# app/hardware/opcua/webhook.py

import aiohttp
from .config import API_BASE


async def call_webhook(name: str, value, path: str):
    """OPC UA에서 받은 값을 내부 Flask API로 전달"""
    url = API_BASE + path
    payload = {
        "event": name,
        "value": value,  # 숫자/문자열/구조체 그대로 JSON 직렬화
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=5) as resp:
                text = await resp.text()
                print(f"[OPCUA] webhook {url} -> {resp.status}, resp={text}")
    except Exception as e:
        print(f"[OPCUA] webhook error ({url}): {e}")
