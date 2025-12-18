# VRステレオ映像配信システム設計書

## 1. 概要

Raspberry Pi 5に接続した2台のカメラからステレオ映像をOculus Questに配信し、VR空間でPiCarXを操作するシステム。

```
[Raspberry Pi 5]                    [EC2 Server]              [Oculus Quest]
 ├─ Camera 0 (左目) ─┐               │                          │
 │                   ├─ Side-by-Side ─→ LiveKit ─────────────────→ VR Viewer
 └─ Camera 1 (右目) ─┘   3840x1080      Ingress                  (ステレオ表示)
                          RTMP
```

## 2. 必要な映像仕様

| 項目 | 値 | 備考 |
|------|-----|------|
| 解像度 | 3840x1080 | 左右1920x1080を横並び（Side-by-Side） |
| コーデック | H.264 | Main Profile, Level 4.1 |
| フレームレート | 30fps | 低遅延を優先する場合は24fps |
| ビットレート | 6-8 Mbps | 両目合計 |

## 3. アーキテクチャ選択肢

### 方式A: LiveKit Spatial Video（推奨）

LiveKit公式の[spatial-video](https://github.com/livekit-examples/spatial-video)サンプルを活用。

**メリット:**
- 既存のLiveKitインフラを流用可能
- Meta Quest用ネイティブアプリあり
- 低遅延（WebRTC）

**構成:**
```
Raspberry Pi → RTMP → LiveKit Ingress → WebRTC → Quest Native App
```

### 方式B: WebXR（ブラウザベース）

Questのブラウザ + WebXR APIを使用。

**メリット:**
- アプリインストール不要
- 既存のviewer.combined.htmlを拡張可能

**デメリット:**
- ブラウザ経由のため若干遅延増
- WebXR対応の実装が必要

## 4. 実装計画

### Phase 1: Raspberry Pi デュアルカメラ配信

#### 4.1 カメラ接続確認

```bash
# カメラ検出
libcamera-hello --list-cameras

# 期待される出力
# 0 : imx708 [4608x2592] (camera0)
# 1 : imx708 [4608x2592] (camera1)
```

#### 4.2 サイドバイサイド映像の生成・配信スクリプト

**方式1: 2つのrpicam-vidをFFmpegで合成**

```bash
#!/bin/bash
# stereo_stream.sh

RTMP_URL="rtmp://relay.yuru-yuru.net:1935/x/STREAMKEY"
WIDTH=1920
HEIGHT=1080
FPS=30

# 名前付きパイプを作成
mkfifo /tmp/cam0.h264 /tmp/cam1.h264

# カメラ0（左目）を起動
rpicam-vid -t 0 --camera 0 --width $WIDTH --height $HEIGHT --framerate $FPS \
  --codec h264 --bitrate 3000000 --inline --profile main --level 4.1 \
  --nopreview -o /tmp/cam0.h264 &

# カメラ1（右目）を起動
rpicam-vid -t 0 --camera 1 --width $WIDTH --height $HEIGHT --framerate $FPS \
  --codec h264 --bitrate 3000000 --inline --profile main --level 4.1 \
  --nopreview -o /tmp/cam1.h264 &

# FFmpegで合成してRTMP配信
ffmpeg -y \
  -f h264 -i /tmp/cam0.h264 \
  -f h264 -i /tmp/cam1.h264 \
  -filter_complex "[0:v][1:v]hstack=inputs=2[outv]" \
  -map "[outv]" \
  -c:v libx264 -preset ultrafast -tune zerolatency \
  -b:v 6000k -maxrate 6000k -bufsize 3000k \
  -f flv "$RTMP_URL"
```

**方式2: Picamera2 + OpenCV（より同期精度が高い）**

```python
#!/usr/bin/env python3
# stereo_stream.py

import cv2
import numpy as np
from picamera2 import Picamera2
import subprocess

WIDTH, HEIGHT, FPS = 1920, 1080, 30
RTMP_URL = "rtmp://relay.yuru-yuru.net:1935/x/STREAMKEY"

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

# FFmpegプロセス
ffmpeg_cmd = [
    'ffmpeg', '-y',
    '-f', 'rawvideo',
    '-pix_fmt', 'rgb24',
    '-s', f'{WIDTH*2}x{HEIGHT}',
    '-r', str(FPS),
    '-i', '-',
    '-c:v', 'libx264',
    '-preset', 'ultrafast',
    '-tune', 'zerolatency',
    '-b:v', '6000k',
    '-f', 'flv',
    RTMP_URL
]
ffmpeg = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

try:
    while True:
        frame0 = cam0.capture_array()
        frame1 = cam1.capture_array()
        stereo = np.hstack([frame0, frame1])
        ffmpeg.stdin.write(stereo.tobytes())
except KeyboardInterrupt:
    pass
finally:
    ffmpeg.stdin.close()
    ffmpeg.wait()
    cam0.stop()
    cam1.stop()
```

### Phase 2: Oculus Quest VRビューワー

#### 方式A: LiveKit Spatial Video App

1. [livekit-examples/spatial-video](https://github.com/livekit-examples/spatial-video) をクローン
2. Android Studioで `LiveKitStereoViewer/` を開く
3. `ImmersiveActivity.kt` で接続情報を設定:
   ```kotlin
   const val LK_SERVER = "wss://relay.yuru-yuru.net"
   const val LK_TOKEN = "YOUR_JOIN_TOKEN"
   ```
4. Quest にビルド＆デプロイ

#### 方式B: WebXR拡張（viewer.combined.html）

```javascript
// WebXR対応のステレオビデオ表示
async function enterVR() {
  if (!navigator.xr) {
    alert('WebXR not supported');
    return;
  }

  const session = await navigator.xr.requestSession('immersive-vr');
  // ステレオ映像を左右の目に分割表示
  // A-Frame または Three.js を使用して実装
}
```

### Phase 3: 操作統合

既存のMQTT操作UIをVR空間内に統合：
- Quest コントローラーで操作
- または視線＋ジェスチャー操作

## 5. 必要なハードウェア

| 項目 | 数量 | 備考 |
|------|------|------|
| Raspberry Pi 5 | 1 | 8GB推奨 |
| カメラモジュール（IMX708等） | 2 | 同一モデル推奨 |
| CSI変換ケーブル | 2 | Pi 5用の細いコネクタ対応 |
| Oculus Quest 2/3 | 1 | |
| 18650バッテリー | 2 | PiCarX用 |

## 6. 課題と対策

| 課題 | 対策 |
|------|------|
| 2カメラの同期 | Picamera2でソフトウェア同期、または Arducam Stereo HAT |
| エンコード負荷 | Pi 5はソフトウェアエンコード。解像度/FPS調整 |
| 遅延 | ultrafast preset、zerolatency tuning、WebRTC使用 |
| 左右の位置調整 | カメラ間隔を人間の瞳孔間距離（約65mm）に合わせる |

## 7. 参考リンク

- [LiveKit Spatial Video Example](https://github.com/livekit-examples/spatial-video)
- [StereoPi Documentation](https://stereopi.com/blog/diy-vr-headset-stereopi-10-ms-latency-just-135)
- [Raspberry Pi Dual Camera Tutorial](https://www.tomshardware.com/raspberry-pi/how-to-use-dual-cameras-on-the-raspberry-pi-5)
- [FFmpeg hstack Filter](https://www.baeldung.com/linux/ffmpeg-stitch-videos-horizontally)
- [Arducam Stereo Camera HAT](https://blog.arducam.com/dual-camera-hat-synchronize-stereo-pi-raspberry/)
