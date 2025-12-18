# VRステレオ映像配信 実装計画書

## 概要

Raspberry Pi 5に接続した2台のカメラからステレオ映像をOculus Questに配信し、VR空間でPiCarXを操作するシステムを段階的に構築する。

## 重要: プロトコル選択と遅延

| プロトコル | トランスコード | 遅延目安 | 推奨度 |
|------------|---------------|----------|--------|
| **WHIP** | なし（パススルー） | **< 1秒** | **推奨** |
| RTMP | **常に必要** | 2-4秒 | 非推奨 |

> **RTMPは常時トランスコード必須**（GStreamerパイプライン経由）のため、根本的に遅延が嵩む。
> WHIPは `enable_transcoding: false` がデフォルトで適用され、WebRTCにパススルーできる。

## システム構成図（WHIP推奨）

```
[Raspberry Pi 5]                       [EC2 Server]              [Oculus Quest]
 ├─ Camera 0 (左目) ─┐                    │                          │
 │                   ├─ WHIP (WebRTC) ──→ LiveKit ──────────────────→ WebXR Viewer
 └─ Camera 1 (右目) ─┘   パススルー        Ingress    < 1秒遅延       (Three.js)

[Quest Controller] ─── DataChannel ──→ [LiveKit] ──→ [Pi: PiCarX制御]
```

---

## フェーズ0: 環境準備

### 0.1 FFmpegのWHIP対応確認

```bash
# FFmpegのWHIP muxer対応確認
ffmpeg -muxers | grep whip

# 出力例: E whip WebRTC over HTTP
# 出力がなければFFmpegのアップグレードまたはビルドが必要
```

**FFmpeg 6.1以上**でWHIP muxerが利用可能。

### 0.2 Raspberry Pi 5 カメラ確認

```bash
# カメラ確認（毎回実行推奨）
rpicam-hello --list-cameras

# 期待される出力:
# 0 : imx708 [4608x2592] (/base/soc/i2c0mux/i2c@1/imx708@1a)
# 1 : imx708 [4608x2592] (/base/soc/i2c0mux/i2c@0/imx708@1a)

# 2台出ない場合：FPCケーブルの向き・固定を確認
```

---

## フェーズ1: WHIP SBS（推奨・最短で低遅延）

### 目標
- 2台のカメラ映像をSBS（横並び）で合成
- **WHIPでLiveKit Ingressに送信**（< 1秒遅延）
- Quest ブラウザでVR表示確認

### 1.1 WHIP Ingress作成（EC2側）

```bash
cd ~/lk-api
export ADMIN_JWT=$(node create-token.js)

# WHIP用Ingress（SBS）
cat > whip-sbs-ingress.json <<'JSON'
{
  "input_type": "WHIP_INPUT",
  "room_name": "vr-demo",
  "participant_identity": "stereo-camera",
  "participant_name": "Stereo Camera (SBS/WHIP)",
  "reusable": true,
  "video": {},
  "audio": {}
}
JSON

curl -sS http://127.0.0.1:7880/twirp/livekit.Ingress/CreateIngress \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d @whip-sbs-ingress.json | jq

# レスポンスから url と stream_key を取得
# 例: "url": "http://localhost:7885/whip/xxxxx"
```

### 1.2 Pi側 配信スクリプト（WHIP SBS）

```bash
#!/bin/bash
# stereo_whip_sbs.sh - SBS形式でWHIP Ingressへ配信（低遅延）

# LiveKit WHIP エンドポイント（Ingress作成時に取得）
WHIP_URL="http://relay.yuru-yuru.net:7885/whip/YOUR_STREAM_KEY"

# 解像度設定（左右それぞれ）
WIDTH=640    # まず低解像度から開始（安定性優先）
HEIGHT=360
FPS=30

# 名前付きパイプを作成
rm -f /tmp/left.h264 /tmp/right.h264
mkfifo /tmp/left.h264 /tmp/right.h264

cleanup() {
    echo "Stopping..."
    kill $(jobs -p) 2>/dev/null
    rm -f /tmp/left.h264 /tmp/right.h264
    exit 0
}
trap cleanup SIGINT SIGTERM

# 左カメラ（camera 0）
# --low-latency: Pi 5ソフトエンコーダの遅延削減（重要）
# --inline: IDR毎にSPS/PPS付加
rpicam-vid --camera 0 -t 0 -n \
    --width $WIDTH --height $HEIGHT --framerate $FPS \
    --codec h264 --bitrate 1500000 \
    --low-latency --inline \
    --profile baseline --level 4.0 \
    --autofocus-mode continuous --awb auto \
    -g 30 \
    -o /tmp/left.h264 &

# 右カメラ（camera 1）- 同じ設定
rpicam-vid --camera 1 -t 0 -n \
    --width $WIDTH --height $HEIGHT --framerate $FPS \
    --codec h264 --bitrate 1500000 \
    --low-latency --inline \
    --profile baseline --level 4.0 \
    --autofocus-mode continuous --awb auto \
    -g 30 \
    -o /tmp/right.h264 &

sleep 2  # カメラ起動待ち

# FFmpegでSBS合成 → WHIP送信
ffmpeg -y \
    -fflags nobuffer -flags low_delay \
    -thread_queue_size 512 -f h264 -i /tmp/left.h264 \
    -thread_queue_size 512 -f h264 -i /tmp/right.h264 \
    -filter_complex "[0:v][1:v]hstack=inputs=2[out]" \
    -map "[out]" \
    -c:v libx264 -preset ultrafast -tune zerolatency \
    -b:v 3M -maxrate 3M -bufsize 1M \
    -g 30 \
    -f whip "$WHIP_URL"
```

### 1.3 解像度の段階的アップ

| 段階 | 左右各 | SBS合計 | 推奨ビットレート |
|------|--------|---------|-----------------|
| 初期 | 640x360 | 1280x360 | 3 Mbps |
| 安定後 | 960x540 | 1920x540 | 4-5 Mbps |
| 最終 | 1280x720 | 2560x720 | 6-8 Mbps |

**まず640x360で安定性を確認してから段階的に上げる。**

---

## フェーズ2: WHIP 2トラック（高品質版）

### 目標
- 左右カメラを別々のトラックとして配信
- 合成ロスなし、フル解像度
- 各目1280x720

### 2.1 左右用WHIP Ingress作成（2つ必要）

```bash
# 左目用Ingress
cat > whip-left.json <<'JSON'
{
  "input_type": "WHIP_INPUT",
  "room_name": "vr-demo",
  "participant_identity": "left",
  "participant_name": "Left Eye Camera",
  "reusable": true,
  "video": {},
  "audio": {}
}
JSON

curl -sS http://127.0.0.1:7880/twirp/livekit.Ingress/CreateIngress \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d @whip-left.json | jq

# 右目用Ingress
cat > whip-right.json <<'JSON'
{
  "input_type": "WHIP_INPUT",
  "room_name": "vr-demo",
  "participant_identity": "right",
  "participant_name": "Right Eye Camera",
  "reusable": true,
  "video": {},
  "audio": {}
}
JSON

curl -sS http://127.0.0.1:7880/twirp/livekit.Ingress/CreateIngress \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d @whip-right.json | jq
```

### 2.2 Pi側 配信スクリプト（WHIP 2トラック）

```bash
#!/bin/bash
# stereo_whip_dual.sh - 左右別々にWHIP Ingressへ配信

WHIP_URL_L="http://relay.yuru-yuru.net:7885/whip/STREAM_KEY_LEFT"
WHIP_URL_R="http://relay.yuru-yuru.net:7885/whip/STREAM_KEY_RIGHT"

WIDTH=1280
HEIGHT=720
FPS=30

cleanup() {
    kill $(jobs -p) 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

# 左目（camera 0）
rpicam-vid --camera 0 -t 0 -n \
    --width $WIDTH --height $HEIGHT --framerate $FPS \
    --codec h264 --bitrate 3000000 \
    --low-latency --inline \
    --profile baseline --level 4.0 \
    --autofocus-mode continuous --awb auto \
    -g 30 \
    -o - | ffmpeg -fflags nobuffer -flags low_delay \
    -f h264 -i - \
    -c:v copy \
    -f whip "$WHIP_URL_L" &

# 右目（camera 1）
rpicam-vid --camera 1 -t 0 -n \
    --width $WIDTH --height $HEIGHT --framerate $FPS \
    --codec h264 --bitrate 3000000 \
    --low-latency --inline \
    --profile baseline --level 4.0 \
    --autofocus-mode continuous --awb auto \
    -g 30 \
    -o - | ffmpeg -fflags nobuffer -flags low_delay \
    -f h264 -i - \
    -c:v copy \
    -f whip "$WHIP_URL_R" &

wait
```

### 2.3 Quest側：2トラックを左右の目に割り当て

```javascript
// viewer.vr.html のLiveKit部分
room.on(LivekitClient.RoomEvent.TrackSubscribed, (track, pub, participant) => {
  if (track.kind === 'video') {
    const el = track.attach();
    el.muted = true;
    el.playsInline = true;
    el.play().catch(() => {});

    const texture = new THREE.VideoTexture(el);
    texture.minFilter = THREE.LinearFilter;
    texture.magFilter = THREE.LinearFilter;

    // participant.identity で左右を判別
    if (participant.identity === 'left') {
      screenL.material.map = texture;
      console.log('Left eye video attached');
    } else if (participant.identity === 'right') {
      screenR.material.map = texture;
      console.log('Right eye video attached');
    }
  }
});
```

---

## フェーズ3: Python SDK直接Publish（最小遅延）

### 目標
- WHIP/Ingressをバイパス
- **100-300ms**の最小遅延
- PiCarX制御と同一プロセス化

### 3.1 インストール

```bash
pip install livekit
```

### 3.2 統合スクリプト（映像配信 + PiCarX制御）

```python
#!/usr/bin/env python3
# pi_livekit_stereo.py - 映像配信 + PiCarX制御を統合

import asyncio
import json
import numpy as np
from livekit import rtc
from picamera2 import Picamera2
from picarx import Picarx

# 設定
LIVEKIT_URL = "wss://relay.yuru-yuru.net"
LIVEKIT_TOKEN = "YOUR_PUBLISH_TOKEN"  # canPublish: true, canPublishData: true

# まず低解像度から開始（CPU負荷軽減）
WIDTH, HEIGHT, FPS = 640, 360, 30

px = Picarx()

async def publish_stereo(room: rtc.Room):
    """2台のカメラからステレオ映像を配信"""

    # カメラ初期化
    cam0 = Picamera2(0)
    cam1 = Picamera2(1)

    config = cam0.create_video_configuration(
        main={"size": (WIDTH, HEIGHT), "format": "RGB888"},
        controls={"FrameRate": FPS}
    )
    cam0.configure(config)
    cam1.configure(config)

    cam0.start()
    cam1.start()

    # SBS用ビデオソース（横に結合）
    source = rtc.VideoSource(WIDTH * 2, HEIGHT)
    track = rtc.LocalVideoTrack.create_video_track("stereo", source)

    options = rtc.TrackPublishOptions()
    options.source = rtc.TrackSource.SOURCE_CAMERA
    await room.local_participant.publish_track(track, options)

    print(f"Publishing stereo video: {WIDTH*2}x{HEIGHT} @ {FPS}fps")

    # フレーム送信ループ
    interval = 1.0 / FPS
    while True:
        start = asyncio.get_event_loop().time()

        # 両カメラからフレーム取得
        frame0 = cam0.capture_array()
        frame1 = cam1.capture_array()

        # SBS合成（横に結合）
        stereo_frame = np.hstack([frame0, frame1])

        # LiveKitに送信
        video_frame = rtc.VideoFrame(
            WIDTH * 2, HEIGHT,
            rtc.VideoBufferType.RGB24,
            stereo_frame.tobytes()
        )
        source.capture_frame(video_frame)

        # フレームレート維持
        elapsed = asyncio.get_event_loop().time() - start
        if elapsed < interval:
            await asyncio.sleep(interval - elapsed)

async def handle_data(packet: rtc.DataPacket):
    """DataChannelからの操作コマンドを処理"""
    try:
        msg = json.loads(packet.data.decode('utf-8'))
        print(f"[CMD] {msg}")

        if msg.get('type') == 'drive':
            throttle = float(msg.get('throttle', 0))
            steer = float(msg.get('steer', 0))

            steer_angle = int(max(-30, min(30, steer * 30)))
            px.set_dir_servo_angle(steer_angle)

            speed = int(abs(throttle) * 100)
            if throttle > 0.05:
                px.forward(speed)
            elif throttle < -0.05:
                px.backward(speed)
            else:
                px.stop()

        elif msg.get('type') == 'camera':
            pan = float(msg.get('pan', 0))
            tilt = float(msg.get('tilt', 0))
            px.set_cam_pan_angle(pan)
            px.set_cam_tilt_angle(tilt)

    except Exception as e:
        print(f"[ERROR] {e}")

async def main():
    room = rtc.Room()

    @room.on("data_received")
    def on_data(packet):
        asyncio.create_task(handle_data(packet))

    print(f"Connecting to {LIVEKIT_URL}...")
    await room.connect(LIVEKIT_URL, LIVEKIT_TOKEN)
    print("Connected!")

    # 映像配信開始
    await publish_stereo(room)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 低遅延設定チートシート

### rpicam-vid オプション（Pi 5必須）

| オプション | 効果 |
|-----------|------|
| `--low-latency` | **必須**: ソフトエンコーダの遅延削減 |
| `--inline` | IDR毎にSPS/PPS付加 |
| `--profile baseline` | 低遅延向けプロファイル |
| `-g 30` | GOP=30（キーフレーム間隔） |

### FFmpeg オプション

| オプション | 効果 |
|-----------|------|
| `-fflags nobuffer` | 入力バッファ無効 |
| `-flags low_delay` | 低遅延モード |
| `-preset ultrafast` | 最速エンコード |
| `-tune zerolatency` | ゼロ遅延チューニング |

---

## 実装チェックリスト

### フェーズ0（環境準備）
- [ ] FFmpeg WHIP対応確認（`ffmpeg -muxers | grep whip`）
- [ ] Pi: 2台のカメラ確認（`rpicam-hello --list-cameras`）
- [ ] EC2: LiveKit Ingressポート7885/UDP開放

### フェーズ1（WHIP SBS）
- [ ] EC2: WHIP Ingress作成
- [ ] Pi: `stereo_whip_sbs.sh` 作成・テスト
- [ ] 遅延測定（目標: < 1秒）

### フェーズ2（WHIP 2トラック）
- [ ] EC2: 左右用WHIP Ingress 2つ作成
- [ ] Pi: `stereo_whip_dual.sh` 作成
- [ ] Quest: 2トラック対応ビューワー

### フェーズ3（Python SDK）
- [ ] Pi: `livekit` パッケージインストール
- [ ] Pi: `pi_livekit_stereo.py` 作成
- [ ] 遅延測定（目標: 100-300ms）

---

## 参考リンク

- [LiveKit Ingress Overview](https://docs.livekit.io/home/ingress/overview/)
- [LiveKit Python SDK](https://github.com/livekit/python-sdks)
- [Achieving <100ms Latency with WebRTC](https://www.gethopp.app/blog/latency-exploration)
- [FFmpeg WHIP Muxer](https://ffmpeg.org/ffmpeg-formats.html#whip)
- [Raspberry Pi Camera Documentation](https://www.raspberrypi.com/documentation/computers/camera_software.html)
