---
name: shorts-from-video
description: 横型(16:9)のAI動画ファイルから見どころを抽出して縦型(9:16)ショート動画を作る。動画ファイル(ローカル/Drive/Box)またはYouTube URLを受け取ったら使用。
---

# 横型動画 → 縦型ショート 作成手順

設計背景は `docs/shorts-pipeline.md` を参照。コストが発生する手順は事前に金額を伝える。

## 0. 入力の確認

- **YouTube URL の場合** → 手順Yへ（Personal Clipper 全自動）。
- **動画ファイルの場合** → 手順1へ。チャット添付は読めないため、Google Drive か Box に
  置いてもらい MCP でダウンロードする。
- ユーザーに確認すること（未指定なら既定値）: 本数（既定3）、1本の尺（既定20〜45秒）、
  縦型化モード（既定 blurpad。crop / reframe(有料) も可）。

## Y. YouTube URL ルート（全自動）

1. `mcp__Higgsfield__personal_clipper_create`
   - urls, clips_num, clip_aspect="9:16", subtitle_font（ユーザーの好み。既定 "Noto Sans"）
2. 30分以上かかることがある。`send_later` で30分後の自己チェックを仕込み、
   `personal_clipper_status` で完了確認 → 結果URLを共有して終了。

## 1. 準備（初回のみ）

```bash
apt-get update -qq && apt-get install -y ffmpeg   # サンドボックスに未導入の場合
```

## 2. 動画の取得と確認

Drive/Box からダウンロードして `work/shorts/<プロジェクト名>/source.mp4` に保存し、

```bash
python3 -m src.shorts.probe work/shorts/<name>/source.mp4
```

で尺・解像度・音声有無を確認。

## 3. シーン解析（Higgsfield）

1. `mcp__Higgsfield__media_upload` (filename, content_type="video/mp4") → 返ってきた curl で PUT
   → `mcp__Higgsfield__media_confirm` (type="video")
2. `mcp__Higgsfield__video_analysis_create` (video_input_id=<media_id>)
3. `mcp__Higgsfield__video_analysis_status` をポーリング（3〜5分目安。短い動画なら数十秒）
4. 完了したら結果 JSON をそのまま `work/shorts/<name>/analysis.json` に保存
   ※10分を超える長尺は解析精度が落ちる。ffmpeg で分割してから解析する。

## 4. 見どころ選定

```bash
python3 -m src.shorts.select_highlights work/shorts/<name>/analysis.json \
  -o work/shorts/<name>/segments.json --min-len 20 --max-len 45 --count <本数>
```

出力はあくまで一次候補。**必ず自分（Claude）で analysis.json のシーン記述を読み**、
以下の基準で `segments.json` を編集して確定する:

- 冒頭1〜2秒でフックになる画から始まっているか
- 1クリップ=1見せ場、見せ場の直後で切れているか
- crop にする場合は被写体位置に合わせてクリップ毎に `focus_x` (0.0-1.0) を設定

確定した segments.json の内容（区間と選定理由）をユーザーに報告する。

## 5. 切り出し＋縦型化

```bash
python3 -m src.shorts.make_shorts work/shorts/<name>/source.mp4 \
  work/shorts/<name>/segments.json -o work/shorts/<name>/out --mode blurpad
```

- `--mode crop` : 中央/focus_x クロップ（左右が切れてよい場合）
- `--mode blurpad` : ぼかし背景パディング（既定）
- `--mode cut` : 横のまま切り出し → 次の reframe 用素材

### reframe（有料・任意）を使う場合

- 事前に `mcp__Higgsfield__reframe` (get_cost=true, duration_seconds, resolution) で見積り、
  ユーザーに金額を伝えて了承を得る（目安: 30秒720p=145cr）。対象は60秒以下。
- cut モードで切り出したクリップを media_upload→PUT→confirm し、
  `reframe` (aspect_ratio="9:16", 15秒超は duration_seconds と resolution 必須) を実行。

## 6. 検品と納品

1. 各 short_XX.mp4 を probe で確認（1080×1920、想定尺）。
2. （任意）本命クリップは `mcp__Higgsfield__virality_predictor` (action=create) でフック強度を確認。
3. 成果物を Drive/Box にアップロードして共有。`work/` は git 管理外なので、
   残したい設定（segments.json 等）があれば報告して指示を仰ぐ。
