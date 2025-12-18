#!/usr/bin/env python3
"""
LiveKit Python SDK を使ったステレオ映像配信（Side-by-Side）
2台のPi Camera V3からの映像を横並びで配信
"""

import asyncio
import numpy as np
from livekit import rtc
from picamera2 import Picamera2

# ============ 設定 ============
LIVEKIT_URL = "wss://relay.yuru-yuru.net"
# canPublish: true, canSubscribe: true のトークン
LIVEKIT_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJ2aWRlbyI6eyJyb29tSm9pbiI6dHJ1ZSwicm9vbSI6InZyLWRlbW8iLCJjYW5QdWJsaXNoIjp0cnVlLCJjYW5TdWJzY3JpYmUiOnRydWV9LCJpc3MiOiJMS19BUElfS0VZIiwiZXhwIjoxNzY4NjMwOTkyLCJuYmYiOjAsInN1YiI6InBpLWNhbWVyYS12MiJ9.P1JQ5XBNln9mB_rLAPM-F1NrVZMujcTuxAjqNfdTbx8"

# 各カメラの解像度（Side-by-Sideなので合計は WIDTH*2 x HEIGHT）
# 低: 1280x720, 中: 1920x1080, 高: 2304x1296
WIDTH = 1920   # 各目の幅
HEIGHT = 1080  # 各目の高さ
FPS = 30       # 負荷が高い場合は24に下げる

# カメラID（左目=0, 右目=1）
LEFT_CAM_ID = 0
RIGHT_CAM_ID = 1
# ==============================


def setup_camera(cam_id: int) -> Picamera2:
    """カメラを初期化"""
    cam = Picamera2(cam_id)
    config = cam.create_video_configuration(
        main={"size": (WIDTH, HEIGHT), "format": "RGB888"},
        controls={"FrameRate": FPS}
    )
    cam.configure(config)
    return cam


async def main():
    print("Initializing cameras...")

    # 2台のカメラを初期化
    try:
        cam_left = setup_camera(LEFT_CAM_ID)
        cam_right = setup_camera(RIGHT_CAM_ID)
    except Exception as e:
        print(f"Camera initialization failed: {e}")
        print("Make sure both cameras are connected.")
        return

    # カメラ開始
    cam_left.start()
    cam_right.start()
    print(f"Cameras started: {WIDTH}x{HEIGHT} @ {FPS}fps each")
    print(f"Output resolution: {WIDTH*2}x{HEIGHT} (Side-by-Side)")

    # LiveKit接続
    room = rtc.Room()

    @room.on("disconnected")
    def on_disconnected():
        print("Disconnected from room")

    print(f"Connecting to {LIVEKIT_URL}...")
    try:
        await room.connect(LIVEKIT_URL, LIVEKIT_TOKEN)
    except Exception as e:
        print(f"Connection failed: {e}")
        cam_left.stop()
        cam_right.stop()
        return

    print(f"Connected to room: {room.name}")

    # ビデオソース作成（Side-by-Side: 幅が2倍）
    stereo_width = WIDTH * 2
    source = rtc.VideoSource(stereo_width, HEIGHT)
    track = rtc.LocalVideoTrack.create_video_track("stereo-camera", source)

    # トラックをPublish（高画質設定）
    options = rtc.TrackPublishOptions()
    options.source = rtc.TrackSource.SOURCE_CAMERA
    # ビデオエンコード設定（ビットレートを上げる）
    options.video_encoding = rtc.VideoEncoding(
        max_bitrate=8_000_000,  # 8 Mbps
        max_framerate=FPS,
    )
    # Simulcast無効（単一の高画質ストリーム）
    options.simulcast = False
    publication = await room.local_participant.publish_track(track, options)
    print(f"Published track: {publication.sid}")
    print(f"Video encoding: 8 Mbps, {FPS} fps")

    interval = 1.0 / FPS
    frame_count = 0

    try:
        print("Streaming stereo video... (Ctrl+C to stop)")
        while True:
            start = asyncio.get_event_loop().time()

            # 両カメラから同時にフレーム取得
            frame_left = cam_left.capture_array()   # RGB888
            frame_right = cam_right.capture_array() # RGB888

            # BGR → RGB 変換（Picamera2はBGR順で出力する場合がある）
            frame_left = frame_left[:, :, ::-1]
            frame_right = frame_right[:, :, ::-1]

            # 180度回転（カメラが上下逆に設置されている場合）
            frame_left = frame_left[::-1, ::-1]
            frame_right = frame_right[::-1, ::-1]

            # 横に結合（Side-by-Side）
            stereo_frame = np.hstack([frame_left, frame_right])

            # RGB → RGBA変換（LiveKit SDKはRGBAを期待）
            stereo_rgba = np.dstack([stereo_frame, np.full((HEIGHT, stereo_width), 255, dtype=np.uint8)])

            # VideoFrameを作成
            video_frame = rtc.VideoFrame(
                stereo_width, HEIGHT,
                rtc.VideoBufferType.RGBA,
                stereo_rgba.tobytes()
            )
            source.capture_frame(video_frame)

            frame_count += 1
            if frame_count % (FPS * 5) == 0:  # 5秒ごとにログ
                print(f"Streamed {frame_count} frames")

            # フレームレート維持
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed < interval:
                await asyncio.sleep(interval - elapsed)

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        cam_left.stop()
        cam_right.stop()
        await room.disconnect()
        print("Cameras stopped, disconnected from room")


if __name__ == "__main__":
    asyncio.run(main())
