#!/usr/bin/env node
/**
 * LiveKit トークン生成スクリプト
 *
 * 使い方:
 *   export LIVEKIT_API_KEY=your_api_key
 *   export LIVEKIT_API_SECRET=your_api_secret
 *   node create-token.js
 */
const jwt = require('jsonwebtoken');

const apiKey = process.env.LIVEKIT_API_KEY;
const apiSecret = process.env.LIVEKIT_API_SECRET;

if (!apiKey || !apiSecret) {
  console.error('Error: LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set');
  process.exit(1);
}

// 管理者トークン（5分有効）
const adminToken = jwt.sign(
  {
    vid: apiKey,
    grants: {
      roomCreate: true,
      roomJoin: true,
      ingressAdmin: true
    }
  },
  apiSecret,
  { expiresIn: '5m', issuer: apiKey, subject: 'admin' }
);

console.log('Admin Token (5min):');
console.log(adminToken);
console.log('');

// ビューワートークン（30日有効）
const viewerToken = jwt.sign(
  {
    video: {
      roomJoin: true,
      room: 'vr-demo',
      canSubscribe: true,
      canPublish: false,
      canPublishData: false
    }
  },
  apiSecret,
  {
    expiresIn: '30d',
    issuer: apiKey,
    subject: 'viewer-' + Math.random().toString(36).substring(2, 8)
  }
);

console.log('Viewer Token (30 days):');
console.log(viewerToken);
