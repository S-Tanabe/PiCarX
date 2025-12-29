#!/usr/bin/env node
/**
 * 管理者用トークン生成スクリプト
 *
 * 使い方:
 *   export LK_API_KEY=your_api_key
 *   export LK_API_SECRET=your_api_secret
 *   node create-token-admin.js
 *
 * 用途:
 *   - ListIngress, CreateIngress などの管理API呼び出し
 *   - ListParticipants などのRoom管理
 */
const { AccessToken } = require('livekit-server-sdk');

const apiKey = process.env.LK_API_KEY;
const apiSecret = process.env.LK_API_SECRET;

if (!apiKey || !apiSecret) {
  console.error('Error: LK_API_KEY and LK_API_SECRET must be set');
  process.exit(1);
}

(async () => {
  const at = new AccessToken(apiKey, apiSecret, {
    identity: 'cli-admin',
    ttl: 3600 * 12, // 12時間
  });
  at.addGrant({
    room: 'vr-demo',
    roomAdmin: true,
    roomCreate: true,
    ingressAdmin: true,
  });
  console.log(await at.toJwt());
})();
