# VR Remote Demo (LiveKit + Python SDK + Raspberry Pi + MQTT Control)

最終更新: 2025-12-18 (JST)

このリポジトリは以下を一式で動かすためのメモです。

- **EC2** 上の LiveKit サーバ（`relay.yuru-yuru.net` 経由、TURN有効）
- **LiveKit Python SDK** を使った低遅延映像配信（部屋: `vr-demo`）
- **Raspberry Pi 5 + デュアルカメラ (imx708_wide ×2)** からの WebRTC ステレオ配信
- **VR Viewer**（WebXR対応ステレオビューワー） … https://relay.yuru-yuru.net/vr
- **ブラウザ Viewer**（映像購読 + **MQTT操作UI**） … `viewer.combined.html`
- **Mosquitto (WebSocket)** による遠隔操作 (topic: `demo/picarx/cmd`)
- **PiCar-X** 側の操作受信スクリプト … `pi_picarx_mqtt.py`

---

## 1. 構成図

```
[Raspberry Pi 5 Dual Camera] --(WebRTC via Python SDK)--> [EC2: LiveKit + TURN] --(WebRTC)--> [VR Viewer]
        (Side-by-Side Stereo)                                     |                    relay.yuru-yuru.net/vr
                                                                  +--(Room: vr-demo)

[Viewer 操作UI] --(MQTT over WebSocket 9001)--> [EC2: Mosquitto] --(TCP 1883)--> [Raspberry Pi 5]
                                                                                      |
                                                                                      +--> [PiCar-X]
```

**遅延性能:**
- 旧方式（RTMP Ingress）: 約10秒
- 新方式（Python SDK WebRTC直接）: **1秒以下**

---

## 2. LiveKit サーバ（EC2）

### 2.1 設定ファイル

`/opt/livekit/livekit.yaml`:
```yaml
port: 7880
log_level: info
rtc:
  tcp_port: 7881
  use_external_ip: true
  port_range_start: 50000
  port_range_end: 60000
  node_ip: 3.112.216.187
  enable_loopback_candidate: false

keys:
  LK_API_KEY: <your-api-secret>

redis:
  address: 127.0.0.1:6379

ingress:
  rtmp_base_url: rtmp://127.0.0.1:1935/x
  whip_base_url: https://relay.yuru-yuru.net/w

# TURN設定（NAT越え用、必須）
turn:
  enabled: true
  domain: relay.yuru-yuru.net
  tls_port: 5349
  udp_port: 3478
  cert_file: /opt/livekit/turn.crt
  key_file: /opt/livekit/turn.key
  external_tls: true
```

### 2.2 必要なセキュリティグループ（UDP/TCP）

| ポート | プロトコル | 用途 |
|--------|------------|------|
| 443 | TCP | HTTPS/WSS (Caddy) |
| 7880 | TCP | LiveKit HTTP API |
| 7881 | TCP | ICE-TCP |
| 3478 | UDP | TURN/STUN |
| 5349 | TCP | TURN TLS |
| 30000-40000 | UDP | TURN リレー |
| 50000-60000 | UDP | WebRTC メディア |
| 1883 | TCP | MQTT |
| 9001 | TCP | MQTT WebSocket |

### 2.3 Publish トークン生成

**重要:** `canSubscribe: true` が必須です（`false`だとWebRTC接続が確立できない）。

`/home/ec2-user/lk-api/create-token-publish.js`:
```javascript
const { AccessToken } = require('livekit-server-sdk');

const apiKey = "LK_API_KEY";
const apiSecret = "<your-api-secret>";

async function main() {
  const at = new AccessToken(apiKey, apiSecret, {
    identity: 'pi-camera',
    ttl: '30d',
  });
  at.addGrant({
    roomJoin: true,
    room: 'vr-demo',
    canPublish: true,
    canSubscribe: true,  // 必須！falseだと接続失敗
  });
  console.log(await at.toJwt());
}
main();
```

実行:
```bash
cd ~/lk-api && node create-token-publish.js
```

### 2.4 サービス再起動

```bash
cd /opt/livekit
docker compose restart livekit
docker compose logs livekit --tail 20
```

---

## 3. Mosquitto（EC2, Docker）

### 3.1 設定と起動

```bash
sudo mkdir -p /opt/mosquitto
cat > /opt/mosquitto/mosquitto.conf <<'CONF'
persistence true
persistence_location /mosquitto/data/
log_dest stderr

# TCP
listener 1883

# WebSocket
listener 9001
protocol websockets
CONF

sudo docker run -d --name mosquitto \
  -p 1883:1883 -p 9001:9001 \
  -v /opt/mosquitto:/mosquitto \
  --restart unless-stopped \
  eclipse-mosquitto:2
```

---

## 4. Raspberry Pi 5（配信 & PiCar-X制御）

### 4.1 Python SDK 環境構築

```bash
# 仮想環境作成
python3 -m venv ~/livekit-venv
source ~/livekit-venv/bin/activate

# LiveKit SDK インストール
pip install livekit numpy
```

### 4.2 映像配信スクリプト

`stream_livekit.py` の設定:
```python
LIVEKIT_URL = "wss://relay.yuru-yuru.net"
LIVEKIT_TOKEN = "<publish-token>"  # canSubscribe: true のトークン

WIDTH = 1280
HEIGHT = 720
FPS = 30
```

実行:
```bash
source ~/livekit-venv/bin/activate
cd ~/programs/vr-controller
python3 stream_livekit.py
```

### 4.3 PiCar-X 制御スクリプト

`pi_picarx_mqtt.py` の設定:
```python
BROKER_HOST = "3.112.216.187"
BROKER_PORT = 1883
TOPIC_CMD   = "demo/picarx/cmd"
TOPIC_PT    = "demo/picarx/camera"
```

実行:
```bash
python3 ~/programs/vr-controller/pi_picarx_mqtt.py
```

**受信ペイロード（JSON）:**
- 走行: `{"throttle": 0.5, "steer": 0.0}` (throttle/steer: -1.0〜1.0)
- 停止: `{"throttle": 0, "steer": 0}`
- カメラ: `{"pan": 0, "tilt": 0}` (度数)

### 4.4 同時起動（推奨）

ターミナル1（映像配信）:
```bash
source ~/livekit-venv/bin/activate && python3 ~/programs/vr-controller/stream_livekit.py
```

ターミナル2（MQTT制御）:
```bash
python3 ~/programs/vr-controller/pi_picarx_mqtt.py
```

---

## 5. Viewer（映像 + 操作UI 統合）

### 5.1 ファイル

- `viewer.combined.html` … 映像購読 + MQTT 操作 UI（ローカル）
- `viewer.vr.html` … VRステレオビューワー（WebXR対応）

### 5.2 VR Viewer（オンライン）

**URL:** https://relay.yuru-yuru.net/vr

1. 「Connect to LiveKit」でライブ映像に接続
2. 「Enter VR」でVRモードに入る（Quest等のVRデバイスで使用）
3. 「Preview Stereo」でPC上でステレオ映像をプレビュー

### 5.3 viewer.combined.html の使い方

1. ファイル内の `token` を **Viewerトークン** に設定（`canSubscribe: true`）
2. MQTT URL を `ws://<EC2のPublic IP>:9001` に設定
3. **Connect** ボタンを押す（LiveKit + MQTT 同時接続）
4. 矢印キー or ボタンで操作（Space で停止）

### 5.4 Viewer トークン生成

```javascript
at.addGrant({
  roomJoin: true,
  room: 'vr-demo',
  canPublish: false,
  canSubscribe: true,
});
```

---

## 6. トラブルシュート

### 6.1 Python SDK 接続エラー

**症状:** `wait_pc_connection timed out`

**原因と対策:**
1. **トークンに `canSubscribe: false`** → `canSubscribe: true` に修正
2. **TURN未設定** → EC2のlivekit.yamlでTURN有効化
3. **セキュリティグループ** → UDP 3478, 30000-40000, 50000-60000 を開放

### 6.2 MQTT 操作が効かない

1. `pi_picarx_mqtt.py` が実行中か確認
2. ブラウザ側で `MQTT publish: demo/picarx/cmd ...` ログが出ているか確認
3. Pi側で `RX demo/picarx/cmd ...` ログが出ているか確認

### 6.3 遅延が大きい

- RTMP Ingress（約10秒）ではなく Python SDK（1秒以下）を使用しているか確認
- `stream_livekit.py` を使用

---

## 7. ファイル一覧

| ファイル | 説明 |
|----------|------|
| `stream_livekit.py` | Python SDK による低遅延映像配信（シングルカメラ） |
| `stream_stereo_livekit.py` | ステレオ映像配信（2カメラ Side-by-Side） |
| `stream_whip.sh` | WHIP配信スクリプト（参考、FFmpegにWHIP非対応の場合あり） |
| `pi_picarx_mqtt.py` | PiCar-X MQTT 制御 |
| `viewer.combined.html` | ブラウザビューワー + 操作UI |
| `viewer.vr.html` | VRステレオビューワー（WebXR対応） |
| `test_livekit_connect.py` | 接続テスト用 |
| `test_new_token.py` | 新トークンテスト用 |

---

## 8. 参考値

### シングルカメラ（stream_livekit.py）
- 解像度/フレーム: `1280x720@30fps`
- 映像コーデック: VP8/VP9（Python SDK デフォルト）
- 遅延: 1秒以下（WebRTC直接）

### ステレオカメラ（stream_stereo_livekit.py）
- 解像度/フレーム: `3840x1080@30fps`（Side-by-Side: 1920x1080 × 2）
- ビットレート: 8 Mbps
- 遅延: 1秒以下（WebRTC直接）

---

## 9. 実装完了

- [x] VRステレオ対応（2カメラ Side-by-Side）
- [x] Oculus Quest WebXR ビューワー（https://relay.yuru-yuru.net/vr）

---

## 10. ライセンス / 注意

- 各種 OSS（LiveKit, mosquitto, mqtt.js 等）のライセンスに従うこと。
- 長期有効のトークンは第三者流出リスクが高まるため、本番運用では短期 or API 経由で都度発行を推奨。
