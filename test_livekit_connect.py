#!/usr/bin/env python3
"""
LiveKit Python SDK 接続テスト（映像なし）
"""

import asyncio
import logging
from livekit import rtc

# デバッグログ有効化
logging.basicConfig(level=logging.DEBUG)

LIVEKIT_URL = "wss://relay.yuru-yuru.net"
# ↓実際のPublishトークンに置き換えてください
LIVEKIT_TOKEN = "YOUR_PUBLISH_TOKEN_HERE"


async def main():
    print(f"LiveKit SDK version: {rtc.__version__ if hasattr(rtc, '__version__') else 'unknown'}")

    # シンプルな接続テスト
    room = rtc.Room()

    @room.on("connected")
    def on_connected():
        print("EVENT: Connected to room!")

    @room.on("disconnected")
    def on_disconnected():
        print("EVENT: Disconnected from room")

    @room.on("connection_state_changed")
    def on_state_changed(state):
        print(f"EVENT: Connection state changed: {state}")

    print(f"Connecting to {LIVEKIT_URL}...")
    print(f"Token (first 50 chars): {LIVEKIT_TOKEN[:50]}...")

    try:
        # タイムアウトを長めに設定
        await asyncio.wait_for(
            room.connect(LIVEKIT_URL, LIVEKIT_TOKEN),
            timeout=30.0
        )
        print(f"SUCCESS: Connected to room: {room.name}")
        print(f"Local participant: {room.local_participant.sid}")

        # 5秒待機してから切断
        await asyncio.sleep(5)

    except asyncio.TimeoutError:
        print("ERROR: Connection timed out (30s)")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
    finally:
        await room.disconnect()
        print("Disconnected")


if __name__ == "__main__":
    asyncio.run(main())
