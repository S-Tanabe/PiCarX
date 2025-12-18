#!/bin/bash
# stream_whip.sh - WHIP経由でLiveKitへ低遅延配信

# ============ 設定 ============
# WHIP URL（Ingress作成時に取得したURLに置き換え）
WHIP_URL="https://relay.yuru-yuru.net/w/BzFvPBp4pcWs"

# 映像設定
WIDTH=1280
HEIGHT=720
FPS=30
BITRATE=3000000  # 3Mbps
# ==============================

echo "Starting WHIP stream to: $WHIP_URL"
echo "Resolution: ${WIDTH}x${HEIGHT} @ ${FPS}fps"

# rpicam-vid → FFmpeg → WHIP
# --low-latency: Pi 5ソフトエンコーダの遅延削減（重要）
# --inline: IDR毎にSPS/PPS付加
# --profile baseline: 低遅延向けプロファイル
rpicam-vid -t 0 -n \
    --width $WIDTH --height $HEIGHT --framerate $FPS \
    --codec h264 --bitrate $BITRATE \
    --low-latency --inline \
    --profile baseline --level 4.0 \
    --autofocus-mode continuous \
    -g 30 \
    -o - \
| ffmpeg \
    -fflags nobuffer -flags low_delay \
    -f h264 -i - \
    -c:v copy \
    -f whip "$WHIP_URL"
