#!/usr/bin/env python3
"""
LiveKit Python SDK を使った低遅延映像配信
FFmpeg/GStreamerのWHIP対応不要
"""

import asyncio
import subprocess
import numpy as np
from livekit import rtc

# ============ 設定 ============
LIVEKIT_URL = "wss://relay.yuru-yuru.net"
# canPublish: true, canSubscribe: true のトークン
LIVEKIT_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJ2aWRlbyI6eyJyb29tSm9pbiI6dHJ1ZSwicm9vbSI6InZyLWRlbW8iLCJjYW5QdWJsaXNoIjp0cnVlLCJjYW5TdWJzY3JpYmUiOnRydWV9LCJpc3MiOiJMS19BUElfS0VZIiwiZXhwIjoxNzY4NjMwOTkyLCJuYmYiOjAsInN1YiI6InBpLWNhbWVyYS12MiJ9.P1JQ5XBNln9mB_rLAPM-F1NrVZMujcTuxAjqNfdTbx8"

WIDTH = 1280
HEIGHT = 720
FPS = 30
# ==============================


async def main():
    room = rtc.Room()

    @room.on("disconnected")
    def on_disconnected():
        print("Disconnected from room")

    print(f"Connecting to {LIVEKIT_URL}...")
    await room.connect(LIVEKIT_URL, LIVEKIT_TOKEN)
    print(f"Connected to room: {room.name}")

    # ビデオソース作成
    source = rtc.VideoSource(WIDTH, HEIGHT)
    track = rtc.LocalVideoTrack.create_video_track("camera", source)

    # トラックをPublish
    options = rtc.TrackPublishOptions()
    options.source = rtc.TrackSource.SOURCE_CAMERA
    publication = await room.local_participant.publish_track(track, options)
    print(f"Published track: {publication.sid}")

    # rpicam-vid からフレームを取得
    # YUV420 (I420) で出力し、RGBに変換
    cmd = [
        "rpicam-vid",
        "-t", "0",
        "-n",
        "--width", str(WIDTH),
        "--height", str(HEIGHT),
        "--framerate", str(FPS),
        "--codec", "yuv420",
        "--low-latency",
        "-o", "-"
    ]

    print(f"Starting camera: {WIDTH}x{HEIGHT} @ {FPS}fps")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    frame_size = WIDTH * HEIGHT * 3 // 2  # YUV420
    interval = 1.0 / FPS

    try:
        while True:
            start = asyncio.get_event_loop().time()

            # YUV420フレーム読み取り
            yuv_data = process.stdout.read(frame_size)
            if len(yuv_data) < frame_size:
                print("Camera stream ended")
                break

            # YUV420 → I420 VideoFrame
            video_frame = rtc.VideoFrame(
                WIDTH, HEIGHT,
                rtc.VideoBufferType.I420,
                yuv_data
            )
            source.capture_frame(video_frame)

            # フレームレート維持
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed < interval:
                await asyncio.sleep(interval - elapsed)

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        process.terminate()
        await room.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
