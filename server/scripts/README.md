# LiveKit API スクリプト

トークン生成やIngress管理のためのユーティリティスクリプト。

## セットアップ

```bash
cd server/scripts
npm install
```

## 環境変数

```bash
export LK_API_KEY=LK_API_KEY
export LK_API_SECRET=your_api_secret
export LIVEKIT_URL=https://your-domain.com
```

## トークン生成

### 管理者トークン（12時間有効）

```bash
node create-token-admin.js
```

用途: Ingress作成、Room管理、Participant一覧など

### 視聴者トークン（30日有効）

```bash
node create-token-viewer.js [identity]
```

用途: VR Viewerからの接続

### 配信者トークン（30日有効）

```bash
node create-token-publish.js [identity]
```

用途: Raspberry Piからの映像配信

## Ingress管理

### WHIP Ingress作成

```bash
export ADMIN_JWT=$(node create-token-admin.js)

curl -sS "${LIVEKIT_URL}/twirp/livekit.Ingress/CreateIngress" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d @whip-ingress.json | jq
```

### RTMP Ingress作成

```bash
curl -sS "${LIVEKIT_URL}/twirp/livekit.Ingress/CreateIngress" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d @rtmp-ingress.json | jq
```

### Ingress一覧

```bash
curl -sS "${LIVEKIT_URL}/twirp/livekit.Ingress/ListIngress" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{}' | jq
```

### Ingress削除

```bash
curl -sS "${LIVEKIT_URL}/twirp/livekit.Ingress/DeleteIngress" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"ingress_id": "IN_xxxxx"}' | jq
```

## Room管理

### 参加者一覧

```bash
curl -sS "${LIVEKIT_URL}/twirp/livekit.RoomService/ListParticipants" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"room": "vr-demo"}' | jq
```

### Room一覧

```bash
curl -sS "${LIVEKIT_URL}/twirp/livekit.RoomService/ListRooms" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{}' | jq
```
