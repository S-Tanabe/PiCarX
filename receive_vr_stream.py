#!/usr/bin/env python3
"""
VRヘッドセットからの映像・音声を受信して再生するスクリプト
LiveKit Python SDK を使用
"""

import asyncio
import numpy as np
from livekit import rtc

# ============ 設定 ============
LIVEKIT_URL = "wss://relay.yuru-yuru.net"
# canSubscribe: true のトークン（Pi Camera用と同じでOK）
LIVEKIT_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJ2aWRlbyI6eyJyb29tSm9pbiI6dHJ1ZSwicm9vbSI6InZyLWRlbW8iLCJjYW5QdWJsaXNoIjp0cnVlLCJjYW5TdWJzY3JpYmUiOnRydWV9LCJpc3MiOiJMS19BUElfS0VZIiwiZXhwIjoxNzY5Njk5NzUzLCJuYmYiOjAsInN1YiI6InBpLWNhbWVyYS12MiJ9.LKRJt8FNFqwHF8PG1YocBZSzTUri4VVGomyfiV--0ZA"
# ==============================

# 音声再生用（オプション）
try:
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("Warning: sounddevice not installed. Audio playback disabled.")
    print("Install with: pip install sounddevice")


class AudioPlayer:
    """音声再生用クラス"""
    def __init__(self, sample_rate=48000, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.stream = None
        if AUDIO_AVAILABLE:
            try:
                self.stream = sd.OutputStream(
                    samplerate=sample_rate,
                    channels=channels,
                    dtype='int16'
                )
                self.stream.start()
                print(f"Audio output initialized: {sample_rate}Hz, {channels}ch")
            except Exception as e:
                print(f"Audio output failed: {e}")
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
            except Exception as e:
                print(f"Audio playback error: {e}")

    def close(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()


async def main():
    print("=" * 50)
    print("VR Stream Receiver")
    print("=" * 50)

    # LiveKit接続
    room = rtc.Room()
    audio_player = None
    video_frame_count = 0
    audio_frame_count = 0

    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        nonlocal audio_player
        print(f"Track subscribed: {track.kind} from {participant.identity}")

        if track.kind == rtc.TrackKind.KIND_VIDEO:
            # ビデオトラック受信
            @track.on("frame_received")
            def on_video_frame(frame: rtc.VideoFrame):
                nonlocal video_frame_count
                video_frame_count += 1
                if video_frame_count % 30 == 1:  # 1秒ごとにログ
                    print(f"Video frame received: {frame.width}x{frame.height} (total: {video_frame_count})")

        elif track.kind == rtc.TrackKind.KIND_AUDIO:
            # オーディオトラック受信
            if AUDIO_AVAILABLE and audio_player is None:
                audio_player = AudioPlayer(sample_rate=48000, channels=1)

            @track.on("frame_received")
            def on_audio_frame(frame: rtc.AudioFrame):
                nonlocal audio_frame_count
                audio_frame_count += 1
                if audio_player:
                    audio_player.play(frame.data.tobytes())
                if audio_frame_count % 100 == 1:  # 定期的にログ
                    print(f"Audio frames received: {audio_frame_count}")

    @room.on("track_unsubscribed")
    def on_track_unsubscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        print(f"Track unsubscribed: {track.kind} from {participant.identity}")

    @room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant):
        print(f"Participant connected: {participant.identity}")

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        print(f"Participant disconnected: {participant.identity}")

    @room.on("disconnected")
    def on_disconnected():
        print("Disconnected from room")

    print(f"Connecting to {LIVEKIT_URL}...")
    try:
        await room.connect(LIVEKIT_URL, LIVEKIT_TOKEN)
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    print(f"Connected to room: {room.name}")
    print(f"Local participant: {room.local_participant.identity}")
    print("-" * 50)
    print("Waiting for VR headset to publish streams...")
    print("(Press Ctrl+C to stop)")
    print("-" * 50)

    # 既存の参加者のトラックを処理
    for participant in room.remote_participants.values():
        print(f"Existing participant: {participant.identity}")
        for publication in participant.track_publications.values():
            if publication.track:
                on_track_subscribed(publication.track, publication, participant)

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        if audio_player:
            audio_player.close()
        await room.disconnect()
        print("Disconnected")


if __name__ == "__main__":
    asyncio.run(main())
