# VR Controller サーバー構成

このディレクトリには、VR Controllerを動作させるためのサーバー構成ファイルが含まれています。

## 構成要素

- **LiveKit**: WebRTC SFUサーバー（映像配信）
- **Caddy**: リバースプロキシ + 自動SSL証明書
- **Redis**: LiveKitのセッション管理
- **Ingress**: WHIP/RTMP入力サポート
- **Mosquitto**: MQTTブローカー（ロボット制御）

## 前提条件

- Docker & Docker Compose
- ドメイン名（SSL証明書取得のため）
- 以下のポートが開放されていること:
  - 80, 443 (HTTP/HTTPS)
  - 1883 (MQTT TCP)
  - 9001 (MQTT WebSocket)
  - 3478/UDP (TURN)
  - 5349/TCP (TURNS)
  - 7880-7881/TCP (LiveKit)
  - 50000-60000/UDP (WebRTC メディア)

## セットアップ手順

### 1. 設定ファイルの準備

```bash
cd server/livekit

# 設定ファイルをコピー
cp livekit.yaml.example livekit.yaml
cp Caddyfile.example Caddyfile
cp ../.env.example .env

# 各ファイルを編集して以下を置き換え:
# - YOUR_DOMAIN → 実際のドメイン
# - YOUR_SERVER_IP → サーバーのパブリックIP
# - YOUR_API_SECRET → ランダムな秘密鍵（64文字以上推奨）
```

### 2. API秘密鍵の生成

```bash
# ランダムな秘密鍵を生成
openssl rand -base64 48
```

### 3. TURN証明書の準備

Caddyが自動取得した証明書を使用するか、別途用意:

```bash
# 自己署名証明書の場合（開発用）
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout turn.key -out turn.crt \
  -subj "/CN=your-domain.example.com"
```

### 4. ディレクトリ構造の作成

```bash
# サーバー上で
mkdir -p /opt/livekit/www
mkdir -p /opt/mosquitto/{config,data,log}
mkdir -p /opt/caddy-data

# 設定ファイルをコピー
cp -r server/livekit/* /opt/livekit/
cp server/mosquitto/mosquitto.conf /opt/mosquitto/config/
```

### 5. Viewerファイルのデプロイ

```bash
cp viewer.vr.html /opt/livekit/www/
cp viewer.combined.html /opt/livekit/www/
```

### 6. 起動

```bash
cd /opt/livekit
docker compose up -d
```

### 7. トークン生成

```bash
cd /opt/livekit
export LIVEKIT_API_KEY=LK_API_KEY
export LIVEKIT_API_SECRET=your_secret
node create-token.js
```

## URL

セットアップ完了後、以下のURLでアクセス可能:

- VR Viewer: `https://your-domain/vr`
- Control UI: `https://your-domain/control`
- MQTT WebSocket: `wss://your-domain/mqtt`

## トラブルシューティング

### 証明書エラー

```bash
# Caddyのログを確認
docker compose logs caddy
```

### LiveKit接続エラー

```bash
# LiveKitのログを確認
docker compose logs livekit

# トークンの有効期限を確認
# JWT.io などでデコード
```

### MQTT接続エラー

```bash
# Mosquittoのログを確認
docker compose logs mosquitto

# ポート確認
netstat -tlnp | grep -E '1883|9001'
```

## セキュリティ注意事項

- `mosquitto.conf`の`allow_anonymous true`は本番環境では無効化してください
- API秘密鍵は必ず変更してください
- ファイアウォールで必要なポートのみ開放してください
