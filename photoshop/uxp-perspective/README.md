# パース線 — Photoshop (UXP) プラグイン（最小プロトタイプ）

開いている PSD を背景に、**アイレベル・消失点・人物垂直線を手で置き**、
消失点へ収束するパースガイドごと **透過の「パース線」レイヤーを PSD に追加**する
Photoshop プラグイン。Web版エディタ（`src/genzu_fix/perspective_editor.py`）の
キャンバスUIを UXP パネルへ移植したもの。

- 自動推定（cv/vision/hybrid）は**無し**＝手置き専用。
- 保存/ダウンロードは**無し**＝結果は PSD のレイヤーとして入る。

> ⚠️ このプロトタイプは Photoshop の無い環境で書いたため**実機未検証**です。
> UXP の公式 API（`require("photoshop")` の `imaging`/`core`/`action`）に沿って
> いますが、Photoshop のバージョン差で API 引数の調整が要ることがあります。
> 動かない箇所があれば「うまくいかない時」を参照してください。

## 必要環境
- Photoshop 2022 (v23) 以降（UXP・manifestVersion 5）。
- [UXP Developer Tool (UDT)](https://developer.adobe.com/photoshop/uxp/2022/guides/devtool/) … 開発中の読み込み用。

## 読み込み方（開発モード）
1. Photoshop を起動し、対象の原図 PSD を開いておく。
2. UXP Developer Tool を起動 → **Add Plugin** → この `manifest.json` を選択。
3. 一覧の行の **•••（Actions）→ Load**。
4. Photoshop の **プラグイン メニュー → パース線** でパネルが開く。
   （ドック/フローティングどちらでも可）

## 使い方
1. PSD を開いた状態で、パネルの **「ドキュメント読込」**。現在のドキュメントが背景に出る。
2. **消失点+（水平）/（鉛直）**、**人物垂直線+** で要素を追加し、ドラッグで配置。
   - アイレベル（シアン線）を掴んで**画像の外へカーソルを出すと傾く**（消失点も連動、
     傾け中は半透明の水平基準線、誤差1°未満は自動で水平へ）。
   - 「地平線へスナップ」ON で水平消失点はアイレベル上に乗る。
   - 「密度」「太さ」スライダで見た目を調整。
3. **「パース線をレイヤーに追加」** → 透過のパース線がドキュメント原寸で
   新規レイヤー **「AI原図修正/パース線」** として挿入される。

座標は正規化（画像比率基準）で扱うため、背景プレビューが縮小表示でも、
出力レイヤーは**ドキュメント原寸でピクセル正確**に描かれる。

## 仕組み（要点）
- 背景読込: `photoshop.imaging.getPixels`（長辺 ~1600px に縮小したプレビューを取得して表示）。
- レイヤー挿入: 原寸の透過キャンバスに線を描く → `createImageDataFromBuffer` →
  新規レイヤーを `batchPlay({_obj:"make"})` で作成 → `imaging.putPixels` で書き込み。
  すべて `core.executeAsModal` 内で実行。

## うまくいかない時（バージョン差の調整ポイント）
- `getPixels` / `putPixels` / `createImageDataFromBuffer` の引数名は PS 版で差がある。
  例: `chunky`、`colorSpace`、`targetSize`、`componentSize`。エラー文言に出た引数を合わせる。
- レイヤー作成後の取得は `doc.activeLayers[0]`。取れない場合は `make` の戻り値
  (`_obj:"make"` の結果) から layer ID を拾う実装に変える。
- パネルが真っ黒: `resize()` が走る前にサイズ0の可能性。パネルを一度リサイズするか、
  `loadDoc` 後に自動 `fitView()` が呼ばれる。
- 権限不足エラー: `manifest.json` の `requiredPermissions` を確認（本プラグインは
  ネットワーク不要・`localFileSystem: "plugin"` のみ）。

## 配布（任意）
- UDT の **Package** で `.ccx` を作成し配布（社内インストール）。
- 署名/ストア配布は Adobe のフローに従う。

## Web版との関係
- UI ロジック（消失点/アイレベル/傾け/人物線/太さ/密度）は Web版
  `perspective_editor.py` の JS と同等。自動推定が必要なら、Web版の
  `/api/detect`（ローカル Flask）を `fetch` する拡張も可能（manifest にドメイン許可が必要）。
