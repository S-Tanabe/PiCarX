# VR Remote Demo (LiveKit + RTMP Ingress + Raspberry Pi + MQTT Control)

最終更新: 2025-12-18 (JST)

このリポジトリ／手順は以下を一式で動かすためのメモです。

- **EC2** 上の LiveKit サーバ（`relay.yuru-yuru.net` 経由）
- **Ingress (RTMP)** を使った配信取り込み（部屋: `vr-demo` / 参加者: `robot-rtmp`）
- **Raspberry Pi 5 + カメラ (imx708_wide)** からの **H.264 + 音声** 送出
- **ブラウザ Viewer**（映像/音声購読 + **MQTT操作UI**） … `viewer.combined.html`
- **Mosquitto (WebSocket)** による遠隔操作 (topic: `picarx/cmd`)
- **PiCar-X** 側の操作受信スクリプト … `pi_picarx_mqtt.py`

---

## 1. ざっくり構成図

```
[Raspberry Pi 5 Camera] --(H.264+AAC via RTMP)--> [EC2: LiveKit Ingress] --(WebRTC)--> [Viewer]
                                                     |
                                                     +--(Room: vr-demo, Participant: robot-rtmp)

[Viewer 操作UI] --(MQTT over WebSocket 9001)--> [EC2: Mosquitto] --(TCP 1883)--> [Raspberry Pi 5]
```

---

## 2. LiveKit サーバ（EC2）

### 2.1 Ingress の起動確認とログ

```bash
# ingress コンテナ再起動
cd /opt/livekit
sudo docker compose restart ingress

# 主要ログ grep（接続や開始・終了、状態系）
sudo docker logs -f livekit-ingress-1 | egrep -i 'Received a new published stream|key frame|ingress started|ingress ended|status|ACTIVE|Publish'
```

### 2.2 Ingress 作成（RTMP）

`lk-api` ディレクトリで管理 JWT を生成し、Twirp API で Ingress を作成。

```bash
cd ~/lk-api
export ADMIN_JWT=$(node create-token.js)  # すでに作成済みAPIキー/シークレットに基づく管理JWT

# Ingress作成（rtmp.json の例）
cat > rtmp.json <<'JSON'
{
  "input_type": "RTMP_INPUT",
  "room_name": "vr-demo",
  "participant_identity": "robot-rtmp",
  "participant_name": "Robot (RTMP)",
  "reusable": true,
  "enable_transcoding": true,
  "video": {},
  "audio": {}
}
JSON

curl -sS http://127.0.0.1:7880/twirp/livekit.Ingress/CreateIngress   -H "Authorization: Bearer $ADMIN_JWT"   -H "Content-Type: application/json"   -d @rtmp.json | jq
```

レスポンス例（重要な値のみ）:
- `ingress_id`: `IN_xxxxxxx`
- `url`: `rtmp://127.0.0.1:1935/x`
- `stream_key`: `YYYYYYYY`

**RTMP URL** は `rtmp://127.0.0.1:1935/x/<stream_key>` です。

### 2.3 状態確認 / 参加者確認

```bash
# Ingress 状態
curl -sS http://127.0.0.1:7880/twirp/livekit.Ingress/ListIngress   -H "Authorization: Bearer $ADMIN_JWT"   -H "Content-Type: application/json" -d '{}' | jq '.items[] | {id: .ingress_id, status: .state.status, room: .room_name}'

# ルームの参加者確認（管理 JWT には roomAdmin 等の権限が必要）
curl -sS http://127.0.0.1:7880/twirp/livekit.RoomService/ListParticipants   -H "Authorization: Bearer $ADMIN_JWT"   -H "Content-Type: application/json"   -d '{"room":"vr-demo"}' | jq
```

**よくあるエラー**:  
- `permissions denied` → 管理 JWT に `roomAdmin` 権限がない/不正。JWT 発行ロジックを確認。
- `invalid token ... token is expired (exp)` → **Join用トークン** の有効期限切れ。後述の「Viewer トークン」を再生成。

---

## 3. Mosquitto（EC2, Docker）

### 3.1 コンテナ起動（WebSocket 有効）

```bash
# 設定配置
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

# 起動
sudo docker run -d --name mosquitto   -p 1883:1883 -p 9001:9001   -v /opt/mosquitto:/mosquitto   --restart unless-stopped   eclipse-mosquitto:2
```

### 3.2 疎通確認（どちらかでOK）

- WebSocket (9001) ― HiveMQ CLI（Docker）:
  ```bash
  sudo docker run --rm -it --network host hivemq/mqtt-cli:latest     shell
  # シェル起動後に:
  mqtt> con -h 127.0.0.1 -p 9001 -V 3 -ws
  mqtt> sub -t demo/ws
  mqtt> pub -t demo/ws -m hello
  ```

- TCP (1883) ― mosquitto-clients（あるいは Docker 版）:
  ```bash
  # 別端末1: 受信
  docker run --rm -it --network host efrecon/mqtt-client sub -h 127.0.0.1 -p 1883 -t demo/tcp -v
  # 別端末2: 送信
  docker run --rm -it --network host efrecon/mqtt-client pub -h 127.0.0.1 -p 1883 -t demo/tcp -m "hello"
  ```

**注意**: SG/Firewall で **9001/tcp**（WebSocket）と **1883/tcp**（TCP）を必要に応じて解放。ALB 越しは WebSocket パススルー設定が必要です。

---

## 4. Raspberry Pi 5（配信＆PiCar-X制御）

### 4.1 映像 + 無音での送出（基本）

`RTMP_URL="rtmp://relay.yuru-yuru.net:1935/x/<stream_key>"` をセットして実行。

```bash
export RTMP_URL='rtmp://relay.yuru-yuru.net:1935/x/STREAMKEY'

rpicam-vid -t 0 --width 1280 --height 720 --framerate 30   --codec h264 --bitrate 3000000 --inline --profile main --level 4.1   --nopreview --libav-format h264 -o - | ffmpeg -re -thread_queue_size 512   -f h264 -r 30 -i -   -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=48000   -shortest   -c:v copy -c:a aac -b:a 128k -ar 48000 -ac 2   -f flv "$RTMP_URL"
```

**ポイント**  
- `--libav-format h264 -o -` でパイプ出力を **Annex B + PTS 補正**（`ffmpeg` 側で Mux）に合わせる。
- `anullsrc` で無音トラックを強制挿入（ブラウザ側の自動再生ガード回避・音声メディア必須ケース対策）。
- もし `Packet is missing PTS` が出る場合は、`-fflags +genpts -use_wallclock_as_timestamps 1` を `ffmpeg` 末尾に追加。

### 4.2 マイク入力での送出（例：USBマイク）

```bash
# デバイス確認
arecord -l
arecord -L

# 例: default デバイスを使う場合
rpicam-vid -t 0 --width 1280 --height 720 --framerate 30   --codec h264 --bitrate 3000000 --inline --profile main --level 4.1   --nopreview --libav-format h264 -o - | ffmpeg -re -thread_queue_size 512   -f h264 -r 30 -i -   -f alsa -thread_queue_size 2048 -ar 48000 -channels 2 -i default   -c:v copy -c:a aac -b:a 128k -ar 48000 -ac 2   -f flv "$RTMP_URL"
```

**うまく行かないとき**: `ALSA lib pcm.c:...` が出る → デバイス名（例: `plughw:1,0`）に変更、サンプリングレートやチャンネル数を対応値に合わせる。

### 4.3 PiCar-X 制御スクリプト

- 依存パッケージ（Debian Bookworm は **PEP 668** により `pip` でなく `apt` を推奨）:
  ```bash
  sudo apt update
  sudo apt install -y python3-paho-mqtt
  ```

- `pi_picarx_mqtt.py` の主要設定:
  ```python
  BROKER_HOST = "<EC2のPublicIPまたはホスト名>"
  BROKER_PORT = 1883  # Pi側はTCPでOK
  TOPIC_BASE  = "picarx/cmd"
  ```

- 実行:
  ```bash
  python3 pi_picarx_mqtt.py
  # ログ: "MQTT connected: 0" が出れば接続成功
  ```

**受信ペイロード（JSON）例**  
- 走行: `{"action":"move","dir":"forward|backward|left|right","speed":50}`
- 停止: `{"action":"stop"}`
- サーボ: `{"action":"servo","pan":0,"tilt":0}`

---

## 5. Viewer（映像＋音声＋操作UI 統合）

### 5.1 ファイル

- `viewer.combined.html` … 本統合版（**このファイルを使う**）
- 旧：`viewer.html`（映像のみ）、`viewer.audio.*.html`（試験版）

### 5.2 使い方

1. ファイルを開く前に、**ソース内 `TOKEN_HERE` を Joinトークン に置換**  
   - 管理JWTではなく **Joinトークン**（`room: vr-demo`, `canSubscribe: true`, `canPublish: false` 推奨）
   - 期限（`exp`）は運用方針に応じて設定。検証用途なら長めでも可（セキュリティ注意）。
2. 右上の **MQTT URL** を `ws://<EC2のPublic IP>:9001` に変更。
3. **Connect** → **Join** を押す。
4. 画面左のボタン or 矢印キーで操作（Spaceで停止）。スライダーで速度／パン・チルト送出。

### 5.3 Join トークン生成（例）

`lk-api` 側の簡易スクリプト（例：`create-join-token.js`）で生成し、`TOKEN_HERE` に貼り付け。

- 期限切れエラー例:  
  `could not establish signal connection: invalid token ... token is expired (exp)` → トークン再発行。
- 音が出ない場合:  
  ブラウザの自動再生ポリシーで **ユーザ操作後の再生** が必要。Join時に `AudioContext.resume()` を呼んでいるが、タブのミュート等も確認。

---

## 6. 運用メモ & トラブルシュート

- **Ingress 状態**: `ENDPOINT_PUBLISHING` であれば Pi→Ingress の送出は成立。Viewer 側で映像/音声が見えなければ Join/購読側の問題。
- **RTMP エラー** `Publish failed` → `stream_key` が一致していない / Ingress が存在しない / 再作成後に古いキーへ送っている。
- **PTS/タイムスタンプ警告** → `-fflags +genpts -use_wallclock_as_timestamps 1` を `ffmpeg` に付与。
- **音声無音** → Pi 側で `anullsrc` を使っている（意図的無音）/ マイク入力の ALSA デバイス名が不正。
- **MQTT 未接続** → `ws://...:9001` / `tcp://...:1883` のいずれかで疎通確認。セキュリティグループ/Firewall/ALB設定を再確認。
- **トークン関連**  
  - Viewer には **Joinトークン**（短期or長期）を使用。  
  - 管理API（ListParticipants等）は **管理JWT** が必要。用途に応じて使い分け。

---

## 7. 付属ファイル（本リポジトリに含める想定）

- `viewer.combined.html` … **映像/音声購読 + MQTT 操作 UI**（CDN は UMD 固定参照）
- `pi_picarx_mqtt.py` … PiCar-X を MQTT で制御
- `mosquitto_websockets.conf`（または `mosquitto.conf`） … WebSocket 有効設定

> 参考: 動作確認済み例では、`viewer.combined.html` から `topic: picarx/cmd` に JSON を Publish、`pi_picarx_mqtt.py` が受信して走行/停止/サーボ制御しました。

---

## 8. 既知の良い値（参考）

- 解像度/フレーム: `1280x720@30`
- H.264 プロファイル/レベル: `main / 4.1`
- 映像ビットレート: `3,000 kbps`
- 音声: AAC LC, 48kHz, 128kbps, stereo

---

## 9. ライセンス / 注意

- 各種 OSS（LiveKit, mosquitto, mqtt.js 等）のライセンスに従うこと。
- 長期有効の Joinトークンは **第三者流出リスク** が高まるため、本番運用では短期 or API 経由で都度発行を推奨。
- 映像/音声の取り扱いは関連法規・社内規程に従うこと。
