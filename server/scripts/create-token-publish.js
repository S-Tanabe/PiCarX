#!/usr/bin/env node
/**
 * 配信者用トークン生成スクリプト
 *
 * 使い方:
 *   export LK_API_KEY=your_api_key
 *   export LK_API_SECRET=your_api_secret
 *   node create-token-publish.js [identity]
 *
 * 用途:
 *   - Raspberry Piからの映像配信
 *   - カメラ映像のPublish
 */
const { AccessToken } = require('livekit-server-sdk');

const apiKey = process.env.LK_API_KEY;
const apiSecret = process.env.LK_API_SECRET;

if (!apiKey || !apiSecret) {
  console.error('Error: LK_API_KEY and LK_API_SECRET must be set');
  process.exit(1);
}

const identity = process.argv[2] || 'pi-camera';

(async () => {
  const at = new AccessToken(apiKey, apiSecret, {
    identity: identity,
    ttl: 3600 * 24 * 30, // 30日
  });
  at.addGrant({
    roomJoin: true,
    room: 'vr-demo',
    canPublish: true,
    canSubscribe: true,
  });
  console.log(await at.toJwt());
})();
