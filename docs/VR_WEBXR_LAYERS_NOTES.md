# WebXR Layers Stereo Mode Investigation

最終更新: 2025-02-14 (JST)

## 目的
- ブラウザ (Quest Browser) 上の `viewer.vr.html` で LiveKit からのサイドバイサイド映像を左右の目に分離表示したい。
- 既存の Three.js 平面での Side-by-Side 表示は両目同じ映像になるため、WebXR Layers API (`XRMediaBinding`) を使ってネイティブなステレオレイヤーへ貼り付ける作戦を採用。

## 実装概要
1. LiveKit からの `RemoteVideoTrack` を隠し `<video>` にアタッチし、`XRSession` 開始前に `play()` を強制。
2. `navigator.xr.requestSession('immersive-vr', { optionalFeatures: ['local-floor', 'bounded-floor', 'layers'] })` で VR セッションを取得。
3. `XRMediaBinding` を生成し、`createQuadLayer(videoElement, { layout: 'stereo-left-right', width: 4, height: aspect, transform: ... })` でステレオ用 QuadLayer を作成。
4. `session.updateRenderState({ layers: [quadLayer] })` を呼び出し、Three.js のレンダーループを停止。以後の描画は XR ランタイムに任せ、コントローラ入力だけを処理。
5. レガシー表示 (Three.js 球面) と切り替えられるよう、UI ボタンを 2 つ用意 (`Enter VR`, `Enter VR (Stereo Beta)`)。

## 直面している問題
- **XRMediaBinding 未実装扱い**: Quest Browser のバージョンによって `XRMediaBinding` が undefined になり、Layers API 自体が使えない場合がある。
- **セッション即終了**: `createQuadLayer` 呼び出し後に VR セッションが読み込み画面のまま戻されることがあり、ブラウザに制御が戻ってしまう。原因候補は以下。
  - beta レイヤーで `layout: 'stereo-left-right'` を要求すると、WebXR ランタイムが video の寸法 (videoWidth/videoHeight) を検証し、準備中に `session.end()` を発行している。
  - Layers API を使用する際、同時に Three.js の `renderer.xr` もセッションにバインドされているため、非互換の描画パスが混在しクラッシュしている可能性。
- **真っ暗のまま描画されない**: たとえセッションが継続しても、Quest 側で QuadLayer が表示されず、結局黒画面になってしまう。`xrMediaBinding` で生成したレイヤーが見えているかの確認手段がなく、ブラウザのコンソールが見えない環境ではトラブルシュートが難しい。
- **同時に Two Rendering Paths を持てない**: Three.js での legacy 表示と Layers API 表示を同ファイルで切り替えようとしているが、`renderer.xr.setSession` が Layers モードでも走っており、QuadLayer と XRWebGLLayer が競合している可能性が高い。

## 現状の結論
- viewer.vr.html では UI/State だけ Layers 対応にしてあるものの、Quest Browser 側の Layers サポート状況と Three.js との相性問題で安定動作に至っていない。
- ブラウザ単体で確実に左右分離を行うには、Layers API 専用の最小実装 (Three.js 依存を外す) でまず単純な映像を表示できることを確認したうえで viewer.vr.html に統合する必要がある。
- 現在はレガシー VR (球面へ Side-by-Side のまま貼る) をデモ用途として残し、Layers API 版は実験的なボタンとして実装されている状態。

## 次のアクション候補
1. Three.js を介さない最小 HTML (LiveKit 接続 + WebXR Layers のみ) を別途作り、Quest ブラウザで Layers API が動作するか検証する。
2. Layers API が利用できない場合のフォールバック (エラーダイアログ + legacy VR へ誘導) を viewer.vr.html に実装してユーザ混乱を避ける。
3. 根本的にブラウザでのステレオ表現が難しい場合は、Unity/Quest ネイティブアプリや LiveKit Spatial Video App など、No.1 方式（ネイティブ）へリダイレクトする。
