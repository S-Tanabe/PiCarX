#!/usr/bin/env python3
import asyncio
from livekit import rtc

LIVEKIT_URL = 'wss://relay.yuru-yuru.net'
TOKEN = 'eyJhbGciOiJIUzI1NiJ9.eyJ2aWRlbyI6eyJyb29tSm9pbiI6dHJ1ZSwicm9vbSI6InZyLWRlbW8iLCJjYW5QdWJsaXNoIjp0cnVlLCJjYW5TdWJzY3JpYmUiOnRydWV9LCJpc3MiOiJMS19BUElfS0VZIiwiZXhwIjoxNzY4NjMwOTkyLCJuYmYiOjAsInN1YiI6InBpLWNhbWVyYS12MiJ9.P1JQ5XBNln9mB_rLAPM-F1NrVZMujcTuxAjqNfdTbx8'

async def main():
    room = rtc.Room()
    try:
        await asyncio.wait_for(room.connect(LIVEKIT_URL, TOKEN), timeout=30)
        print(f'SUCCESS: {room.name}')
        await asyncio.sleep(2)
    except Exception as e:
        print(f'ERROR: {e}')
    finally:
        await room.disconnect()

asyncio.run(main())
