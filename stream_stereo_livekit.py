#!/usr/bin/env python3
"""
LiveKit Python SDK を使ったステレオ映像配信（Side-by-Side）+ VR音声受信
2台のPi Camera V3からの映像を横並びで配信し、VRヘッドセットからの音声を受信・再生
"""

import asyncio
import numpy as np
from livekit import rtc
from picamera2 import Picamera2

# ============ 設定 ============
LIVEKIT_URL = "wss://relay.yuru-yuru.net"
# canPublish: true, canSubscribe: true のトークン
LIVEKIT_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJ2aWRlbyI6eyJyb29tSm9pbiI6dHJ1ZSwicm9vbSI6InZyLWRlbW8iLCJjYW5QdWJsaXNoIjp0cnVlLCJjYW5TdWJzY3JpYmUiOnRydWV9LCJpc3MiOiJMS19BUElfS0VZIiwiZXhwIjoxNzY5Njk5NzUzLCJuYmYiOjAsInN1YiI6InBpLWNhbWVyYS12MiJ9.LKRJt8FNFqwHF8PG1YocBZSzTUri4VVGomyfiV--0ZA"

# 各カメラの解像度（Side-by-Sideなので合計は WIDTH*2 x HEIGHT）
# 低: 1280x720, 中: 1920x1080, 高: 2304x1296
WIDTH = 1920   # 各目の幅
HEIGHT = 1080  # 各目の高さ
FPS = 30       # 負荷が高い場合は24に下げる

# カメラID（左目=0, 右目=1）
LEFT_CAM_ID = 0
RIGHT_CAM_ID = 1
# ==============================

# 音声再生用（オプション）
try:
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("Note: sounddevice not installed. Audio playback disabled.")
    print("Install with: pip install sounddevice")


class AudioPlayer:
    """VRからの音声を再生するクラス"""
    def __init__(self, sample_rate=48000, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.stream = None
        self.frame_count = 0

        if AUDIO_AVAILABLE:
            try:
                self.stream = sd.OutputStream(
                    samplerate=sample_rate,
                    channels=channels,
                    dtype='int16'
                )
                self.stream.start()
                print(f"[Audio] Output initialized: {sample_rate}Hz, {channels}ch")
            except Exception as e:
                print(f"[Audio] Output failed: {e}")
                self.stream = None

    def play(self, data: bytes):
        if self.stream:
            try:
                audio_array = np.frombuffer(data, dtype=np.int16)
                if self.channels == 1:
                    audio_array = audio_array.reshape(-1, 1)
                else:
                    audio_array = audio_array.reshape(-1, self.channels)
                self.stream.write(audio_array)
                self.frame_count += 1
            except Exception as e:
                if self.frame_count == 0:
                    print(f"[Audio] Playback error: {e}")

    def close(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            print(f"[Audio] Closed (played {self.frame_count} frames)")


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
    print("=" * 60)
    print("PiCarX Stereo Streamer + VR Audio Receiver")
    print("=" * 60)

    print("\nInitializing cameras...")

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

    # 音声プレイヤー
    audio_player = None
    audio_frame_count = 0
    audio_task = None

    async def process_audio_stream(track: rtc.RemoteAudioTrack):
        """音声ストリームを処理する非同期タスク"""
        nonlocal audio_player, audio_frame_count

        if AUDIO_AVAILABLE and audio_player is None:
            audio_player = AudioPlayer(sample_rate=48000, channels=1)

        audio_stream = rtc.AudioStream(track)
        async for frame_event in audio_stream:
            audio_frame_count += 1
            if audio_player:
                audio_player.play(frame_event.frame.data.tobytes())
            if audio_frame_count % 500 == 1:
                print(f"[Audio] Received {audio_frame_count} frames")

    # LiveKit接続
    room = rtc.Room()

    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        nonlocal audio_task
        print(f"[Track] Subscribed: {track.kind} from {participant.identity}")

        if track.kind == rtc.TrackKind.KIND_AUDIO:
            # 音声トラック受信 - 非同期タスクを起動
            audio_task = asyncio.create_task(process_audio_stream(track))

        elif track.kind == rtc.TrackKind.KIND_VIDEO:
            print(f"[Track] Video from VR received (not displaying)")

    @room.on("track_unsubscribed")
    def on_track_unsubscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        print(f"[Track] Unsubscribed: {track.kind} from {participant.identity}")

    @room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant):
        print(f"[Room] Participant connected: {participant.identity}")

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        print(f"[Room] Participant disconnected: {participant.identity}")

    @room.on("disconnected")
    def on_disconnected():
        print("[Room] Disconnected")

    print(f"\nConnecting to {LIVEKIT_URL}...")
    try:
        await room.connect(LIVEKIT_URL, LIVEKIT_TOKEN)
    except Exception as e:
        print(f"Connection failed: {e}")
        cam_left.stop()
        cam_right.stop()
        return

    print(f"Connected to room: {room.name}")
    print(f"Local participant: {room.local_participant.identity}")

    # ビデオソース作成（Side-by-Side: 幅が2倍）
    stereo_width = WIDTH * 2
    source = rtc.VideoSource(stereo_width, HEIGHT)
    track = rtc.LocalVideoTrack.create_video_track("stereo-camera", source)

    # トラックをPublish（高画質設定）
    options = rtc.TrackPublishOptions(
        source=rtc.TrackSource.SOURCE_CAMERA,
        video_encoding=rtc.VideoEncoding(
            max_bitrate=8_000_000,  # 8 Mbps
            max_framerate=FPS,
        ),
        simulcast=False,  # 単一の高画質ストリーム
    )
    publication = await room.local_participant.publish_track(track, options)
    print(f"Published video track: {publication.sid}")
    print(f"Video encoding: 8 Mbps, {FPS} fps")

    print("-" * 60)
    print("Streaming stereo video... (Ctrl+C to stop)")
    print("Waiting for VR audio...")
    print("-" * 60)

    interval = 1.0 / FPS
    frame_count = 0

    try:
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
            if frame_count % (FPS * 10) == 0:  # 10秒ごとにログ
                print(f"[Video] Streamed {frame_count} frames | [Audio] Received {audio_frame_count} frames")

            # フレームレート維持
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed < interval:
                await asyncio.sleep(interval - elapsed)

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        cam_left.stop()
        cam_right.stop()
        if audio_player:
            audio_player.close()
        await room.disconnect()
        print("Cameras stopped, disconnected from room")


if __name__ == "__main__":
    asyncio.run(main())
