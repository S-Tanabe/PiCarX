#!/usr/bin/env node
/**
 * 視聴者用トークン生成スクリプト
 *
 * 使い方:
 *   export LK_API_KEY=your_api_key
 *   export LK_API_SECRET=your_api_secret
 *   node create-token-viewer.js [identity]
 *
 * 用途:
 *   - VR Viewerからの接続
 *   - 映像の視聴のみ（配信不可）
 */
const { AccessToken } = require('livekit-server-sdk');

const apiKey = process.env.LK_API_KEY;
const apiSecret = process.env.LK_API_SECRET;

if (!apiKey || !apiSecret) {
  console.error('Error: LK_API_KEY and LK_API_SECRET must be set');
  process.exit(1);
}

// 任意の視聴者ID（引数で指定可能）
const viewerIdentity = process.argv[2] || `viewer-${Math.random().toString(36).slice(2, 8)}`;

(async () => {
  const at = new AccessToken(apiKey, apiSecret, {
    identity: viewerIdentity,
    ttl: 3600 * 24 * 30, // 30日
  });
  at.addGrant({
    roomJoin: true,
    room: 'vr-demo',
    canSubscribe: true,
    canPublish: false,
    canPublishData: false,
  });
  console.log(await at.toJwt());
})();
