#!/usr/bin/env python3
"""
LiveKit Python SDK を使ったステレオ映像配信（Side-by-Side）+ 双方向音声
2台のPi Camera V3からの映像を横並びで配信し、VRヘッドセットと双方向で音声通信
"""

import asyncio
import concurrent.futures
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

# 音声設定
AUDIO_SAMPLE_RATE = 48000
AUDIO_CHANNELS = 1
AUDIO_FRAME_SIZE = 480  # 10ms @ 48kHz
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
    """VRからの音声を再生するクラス（低遅延設定）"""
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
                    dtype='int16',
                    latency='low',  # 低遅延モード
                    blocksize=480,  # 10ms分のサンプル (48000Hz * 0.01)
                )
                self.stream.start()
                print(f"[Audio] Output initialized: {sample_rate}Hz, {channels}ch (low latency)")
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


class MicrophoneCapture:
    """マイクから音声をキャプチャしてLiveKitに送信するクラス（キューベース）"""
    def __init__(self, audio_source: rtc.AudioSource, sample_rate=48000, channels=1):
        self.audio_source = audio_source
        self.sample_rate = sample_rate
        self.channels = channels
        self.running = False
        self.stream = None
        self.frame_count = 0
        self.queue = asyncio.Queue(maxsize=50)  # フレームキュー
        self.task = None

    async def start(self):
        if not AUDIO_AVAILABLE:
            print("[Mic] sounddevice not available, microphone disabled")
            return False

        try:
            self.running = True
            # 音声処理タスクを開始
            self.task = asyncio.create_task(self._process_audio())

            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype='int16',
                blocksize=AUDIO_FRAME_SIZE,
                latency='low',
                callback=self._audio_callback
            )
            self.stream.start()
            print(f"[Mic] Capture started: {self.sample_rate}Hz, {self.channels}ch")
            return True
        except Exception as e:
            print(f"[Mic] Failed to start: {e}")
            self.running = False
            return False

    def _audio_callback(self, indata, frames, time_info, status):
        """sounddeviceのコールバック（同期）- キューにデータを追加"""
        if status:
            print(f"[Mic] Status: {status}")
        if self.running:
            try:
                # データをコピーしてキューに追加（キューがいっぱいなら古いのを捨てる）
                audio_data = indata.copy()
                try:
                    self.queue.put_nowait(audio_data)
                except asyncio.QueueFull:
                    pass  # キューがいっぱいなら破棄
            except Exception as e:
                if self.frame_count == 0:
                    print(f"[Mic] Callback error: {e}")

    async def _process_audio(self):
        """キューから音声を取り出してLiveKitに送信（非同期）"""
        print("[Mic] Audio processing task started")
        while self.running:
            try:
                # タイムアウト付きでキューから取得
                try:
                    audio_data = await asyncio.wait_for(self.queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue

                # AudioFrame を作成して送信
                audio_data = audio_data.flatten().astype(np.int16)
                audio_frame = rtc.AudioFrame(
                    data=audio_data.tobytes(),
                    sample_rate=self.sample_rate,
                    num_channels=self.channels,
                    samples_per_channel=len(audio_data) // self.channels,
                )
                await self.audio_source.capture_frame(audio_frame)
                self.frame_count += 1
            except Exception as e:
                if self.frame_count == 0:
                    print(f"[Mic] Process error: {e}")
        print("[Mic] Audio processing task ended")

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
        if self.task:
            self.task.cancel()
        print(f"[Mic] Stopped (captured {self.frame_count} frames)")


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

    audio_streams = []  # AudioStreamを保持するリスト

    async def process_audio_stream(track):
        """音声ストリームを処理する非同期タスク"""
        nonlocal audio_player, audio_frame_count

        print(f"[Audio] Starting audio stream processing for track: {track.sid}")
        print(f"[Audio] Track type: {type(track)}")

        if AUDIO_AVAILABLE and audio_player is None:
            audio_player = AudioPlayer(sample_rate=48000, channels=1)

        try:
            audio_stream = rtc.AudioStream(track)
            audio_streams.append(audio_stream)  # 参照を保持
            print(f"[Audio] AudioStream created: {audio_stream}")
            print(f"[Audio] Waiting for frames...")

            async for frame_event in audio_stream:
                audio_frame_count += 1
                if audio_player:
                    audio_player.play(frame_event.frame.data.tobytes())
                if audio_frame_count % 500 == 1:
                    print(f"[Audio] Received {audio_frame_count} frames")

            print(f"[Audio] Audio stream ended")
        except Exception as e:
            import traceback
            print(f"[Audio] Error in audio stream: {e}")
            traceback.print_exc()

    # LiveKit接続
    room = rtc.Room()

    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        nonlocal audio_task
        print(f"[Track] Subscribed: kind={track.kind}, name={track.name}, sid={track.sid} from {participant.identity}")
        print(f"[Track] KIND_AUDIO={rtc.TrackKind.KIND_AUDIO}, KIND_VIDEO={rtc.TrackKind.KIND_VIDEO}")

        if track.kind == rtc.TrackKind.KIND_AUDIO:
            print(f"[Track] This is an AUDIO track, starting processing...")
            # 音声トラック受信 - 非同期タスクを起動
            audio_task = asyncio.create_task(process_audio_stream(track))

        elif track.kind == rtc.TrackKind.KIND_VIDEO:
            print(f"[Track] This is a VIDEO track (not displaying)")

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

    # イベントループを取得（async関数内では get_running_loop を使用）
    loop = asyncio.get_running_loop()

    # 音声ソース作成とトラック公開
    audio_source = rtc.AudioSource(AUDIO_SAMPLE_RATE, AUDIO_CHANNELS)
    audio_track = rtc.LocalAudioTrack.create_audio_track("pi-microphone", audio_source)
    audio_options = rtc.TrackPublishOptions(
        source=rtc.TrackSource.SOURCE_MICROPHONE,
    )
    audio_publication = await room.local_participant.publish_track(audio_track, audio_options)
    print(f"Published audio track: {audio_publication.sid}")

    # マイクキャプチャ開始
    mic_capture = MicrophoneCapture(audio_source, AUDIO_SAMPLE_RATE, AUDIO_CHANNELS)
    await mic_capture.start()

    print("-" * 60)
    print("Streaming stereo video + audio... (Ctrl+C to stop)")
    print("Bidirectional audio enabled")
    print("-" * 60)

    interval = 1.0 / FPS
    frame_count = 0

    # カメラキャプチャ用のスレッドプールを作成
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

    def capture_frame_sync(cam_left, cam_right):
        """同期的にカメラからフレームを取得（別スレッドで実行）"""
        frame_left = cam_left.capture_array()
        frame_right = cam_right.capture_array()
        return frame_left, frame_right

    print("[Video] Starting capture loop...")
    try:
        while True:
            start = loop.time()

            # 10秒ごとに参加者とトラックの状態を確認
            if frame_count % (FPS * 10) == 0 and frame_count > 0:
                print(f"[Debug] Remote participants: {len(room.remote_participants)}")
                for identity, participant in room.remote_participants.items():
                    print(f"[Debug]   Participant: {identity}")
                    for sid, pub in participant.track_publications.items():
                        print(f"[Debug]     Track: sid={sid}, kind={pub.kind}, subscribed={pub.subscribed}")

            # 両カメラから同時にフレーム取得（別スレッドで実行してイベントループをブロックしない）
            frame_left, frame_right = await loop.run_in_executor(
                executor, capture_frame_sync, cam_left, cam_right
            )

            if frame_count == 0:
                print(f"[Video] First frame captured: {frame_left.shape}")

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
                print(f"[Video] Streamed {frame_count} frames | [Mic] Sent {mic_capture.frame_count} frames | [Audio] Received {audio_frame_count} frames")

            # フレームレート維持
            elapsed = loop.time() - start
            if elapsed < interval:
                await asyncio.sleep(interval - elapsed)
            else:
                # カメラ処理が遅い場合でも他のタスクに制御を渡す
                await asyncio.sleep(0)

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        executor.shutdown(wait=False)
        mic_capture.stop()
        cam_left.stop()
        cam_right.stop()
        if audio_player:
            audio_player.close()
        await room.disconnect()
        print("Cameras and microphone stopped, disconnected from room")


if __name__ == "__main__":
    asyncio.run(main())
