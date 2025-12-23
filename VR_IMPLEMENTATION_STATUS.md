# VR Viewer 実装状況レポート

最終更新: 2024-12-19

## 1. 現在の実装状況

### 1.1 動作確認済み機能

| 機能 | 状態 | 備考 |
|------|------|------|
| LiveKit接続 | ✅ 動作 | WebRTC経由で低遅延映像受信 |
| MQTT接続 | ✅ 動作 | WSS経由（Caddyプロキシ経由） |
| ブラウザプレビュー | ✅ 動作 | 右下に映像表示 |
| Preview Stereo（非VR） | ✅ 動作 | Three.jsで左右分離表示 |
| VRモード映像表示 | ✅ 動作 | Side-by-Side映像を平面に表示 |
| VRコントローラー操作 | ✅ 動作 | 走行・パン/チルト対応 |

### 1.2 未解決の課題

| 課題 | 状態 | 詳細 |
|------|------|------|
| VRステレオ分離 | ❌ 未実装 | 左右の目に別々の映像を表示できていない |

## 2. 技術的な詳細

### 2.1 VR映像表示の現状

現在のVRモードでは、Side-by-Side映像をそのまま1枚の平面に表示しています。
両目で同じ映像（左右並んだ状態）が見える状態です。

```
現在の状態:
┌─────────────────────────────────────┐
│  [左目用映像] │ [右目用映像]         │  ← 両目で同じものが見える
└─────────────────────────────────────┘

理想の状態:
左目: [左目用映像のみ]
右目: [右目用映像のみ]
```

### 2.2 試行したステレオ分離アプローチと結果

#### アプローチ1: Three.js Layers
- **方法**: 左目用メッシュをレイヤー1、右目用メッシュをレイヤー2に配置し、XRカメラのレイヤーを設定
- **結果**: ❌ 激しい処理落ち、VRモードに入れない

#### アプローチ2: ビューポート位置判定シェーダー
- **方法**: `gl_FragCoord.x`でピクセル位置から左右の目を判定
- **結果**: ❌ WebXRでは各目のレンダリング時にビューポートがリセットされるため判定不可

#### アプローチ3: WebXR Layers API
- **方法**: `XRMediaBinding.createQuadLayer()`でネイティブステレオレイヤーを作成
- **結果**: ❌ セッション開始時にフリーズ（30秒以上応答なし）

### 2.3 VRコントローラー操作

```
走行操作:
- 左スティック上下: 前進/後退（throttle）
- 右スティック左右: 左右旋回（steer）
- トリガー: 停止

カメラ操作:
- グリップボタン + 右スティック左右: パン（-90°〜+90°）
- グリップボタン + 右スティック上下: チルト（-45°〜+45°）
```

## 3. ファイル構成

```
/home/s-tanabe/programs/vr-controller/
├── viewer.vr.html          # VRビューワー（メイン）
├── viewer.combined.html    # ブラウザビューワー + MQTT操作UI
├── stream_stereo_livekit.py  # Raspberry Pi ステレオ配信スクリプト
├── stream_livekit.py       # Raspberry Pi シングルカメラ配信
├── pi_picarx_mqtt.py       # PiCarX MQTT制御スクリプト
└── README.md               # プロジェクト概要

EC2 (/opt/livekit/www/):
└── viewer.vr.html          # デプロイ済みVRビューワー
```

## 4. 今後の対応予定

### 4.1 VRステレオ分離の解決策候補

#### 候補A: カメラ位置判定方式
- **概要**: WebXRでは左目カメラと右目カメラの位置が異なる（IPD分のオフセット）。シェーダー内でカメラのワールド位置を参照し、左右を判定
- **実装難易度**: 中
- **備考**: `cameraPosition`をuniformとして渡し、X座標で判定

#### 候補B: マルチパスレンダリング
- **概要**: 左目用と右目用で別々のレンダリングパスを実行
- **実装難易度**: 高
- **備考**: Three.jsのWebXR統合との相性要調査

#### 候補C: WebXR Layers API再調査
- **概要**: フリーズの原因を調査し、正しい実装方法を確認
- **実装難易度**: 中〜高
- **備考**: Quest Browser のバージョンやサポート状況を確認

#### 候補D: 2つの平面を左右にオフセット配置
- **概要**: 左目用と右目用の平面を物理的に左右にずらして配置し、片目ずつ見えるようにする
- **実装難易度**: 低
- **備考**: 簡易的だが視差効果は限定的

### 4.2 その他の改善項目

- [ ] VR内でのステータス表示（接続状態、操作ガイド）
- [ ] 映像品質設定（解像度、ビットレート調整）
- [ ] VR内UI（ボタン操作など）
- [ ] 360度球体表示への対応（現在は平面のみ）

## 5. 動作確認環境

- **VRデバイス**: Meta Quest（Quest 2/3/Pro想定）
- **ブラウザ**: Quest Browser
- **サーバー**: EC2 (relay.yuru-yuru.net)
- **配信元**: Raspberry Pi 5 + デュアルカメラ

## 6. 現在のバージョン

- **viewer.vr.html**: v2024-12-19-Q
- **URL**: https://relay.yuru-yuru.net/vr

## 7. 参考情報

### WebXR Layers API
- https://developer.mozilla.org/en-US/docs/Web/API/WebXR_Device_API/Layers
- https://immersive-web.github.io/layers/

### Three.js WebXR
- https://threejs.org/docs/#manual/en/introduction/How-to-create-VR-content

### Quest Browser WebXR対応状況
- https://developer.oculus.com/documentation/web/browser-supported-features/
