# 横型AI動画 → 縦型ショート 自動化パイプライン 設計

> ステータス: 設計＋基盤実装済み（2026-07-06）。実写検証（本物のAI動画）待ち。
> 実行手順は `.claude/skills/shorts-from-video/SKILL.md`（既存動画から）と
> `.claude/skills/shorts-from-idea/SKILL.md`（ゼロから生成）を参照。

## 1. 目的

YouTube投稿用の横型(16:9)AI動画から「見どころ」を自動抽出し、
YouTube Shorts / TikTok 向けの縦型(9:16)ショート動画を量産する。
あわせて、既存動画に依らずゼロから企画→生成する経路も持つ
（参照画像 + Higgsfield MCP 経由の Seedance 2.0）。

## 2. 全体像 — 3経路

```
[A-1] YouTube URL ──► Personal Clipper (Higgsfield) ─────────► 縦型クリップ一式（全自動）

[A-2] 動画ファイル ─► ① Higgsfieldへアップロード
                     ② video_analysis でシーン毎解析
                     ③ 見どころ選定 (select_highlights.py + Claude/人がレビュー)
                     ④ ffmpeg で切り出し (make_shorts.py)
                     ⑤ 縦型化: crop / blurpad (ローカル・無料)
                              または reframe (AI外挿・有料)
                     ⑥ (任意) virality_predictor でスコア確認 → 保存/納品

[B]   企画から生成 ─► ① Claudeで案出し（フック/展開/オチ、カット割り 4〜15秒×N）
                     ② 参照画像アップロード
                     ③ generate_video (seedance_2_0, 9:16) をカット毎に実行
                     ④ explainer_video でカット結合（＋字幕焼き込み可）
                     ⑤ virality_predictor で事前チェック
```

## 3. 経路の使い分け

| 経路 | 入力 | 向いているケース | コスト感 |
|---|---|---|---|
| A-1 Personal Clipper | YouTube URL | 既に公開済みの長尺。手間最小（見どころ抽出・9:16化・字幕まで全自動） | ジョブ課金（30分+かかることあり） |
| A-2 自前パイプライン | ローカル/Drive/Boxの動画ファイル | 未公開素材。切り所やクロップ位置を制御したい。無料で済ませたい | 解析＋(任意)reframe のみ |
| B ゼロから生成 | テーマ＋参照画像 | 元動画が無い、または元動画と独立した企画 | Seedance 45cr/10秒(720p,std) 目安 |

## 4. 確認済みの事実（2026-07-06 実測）

- **egress**: サンドボックス→ `upload.higgsfield.ai` への PUT は **200 OK**（以前の403は解消。
  環境の Network access 設定済み）。web セッション内で完結可能。
- **video_analysis**: 4秒動画で16秒で完了。scenes スキーマ:
  `{scene_number, label, visual, audio, shot_type, timestamp_start:"0:01", timestamp_end}`
  （タイムスタンプは "M:SS" 文字列。`select_highlights.py` が正規化対応済み）。
  長尺ほど精度が落ちるため、10分超は分割解析を検討。
- **reframe**: 対象 ≤60秒。9:16対応。30秒/720p = **145 credits**。15秒超は
  `duration_seconds` と `resolution` の指定必須。
- **seedance_2_0**: 4〜15秒/本。aspect 9:16 可。720p/std 10秒 = **45 credits**。
  参照入力: `start_image / end_image / image_references / video_references / audio_references`。
  `generate_audio` でネイティブ音声生成可。4k は mode=std のみ。
- **explainer_video**: 複数クリップの結合は無料（字幕は 0.05cr/ブロック）。
  ルートBのカット結合に使える（9:16 なら width=720/height=1280 等）。
- **ffmpeg**: サンドボックスに `apt-get update && apt-get install -y ffmpeg` で導入可。
- 残高: 2,233 credits / plan creator（2026-07-06時点）。

## 5. ローカル実装（src/shorts/）

| ファイル | 役割 |
|---|---|
| `probe.py` | ffprobe ラッパ（尺・解像度・音声有無） |
| `select_highlights.py` | 解析シーンJSON → ハイライト候補 `segments.json`（キーワードスコア＋隣接結合）。**叩き台**であり、Claude/人がレビュー・編集して確定する |
| `make_shorts.py` | `segments.json` に従って切り出し＋縦型化。`--mode crop`（中央/指定位置クロップ）/ `blurpad`（ぼかし背景で上下パディング）/ `cut`（横のまま切るだけ→reframe 素材用）。出力 1080×1920 + `manifest.json` |

テスト済み: 合成テスト動画で 3経路（crop/blurpad/選定ロジック）とも 1080×1920 出力を確認。

## 6. 縦型化の方式選択

1. **crop**（無料・即時）: 被写体が中央付近にある映像。左右が切れる。`focus_x` で注視点調整可。
2. **blurpad**（無料・即時）: 構図全体を見せたい映像。上下がぼかし背景になる定番スタイル。
3. **reframe**（有料・AI外挿）: 上下をAIが自然に描き足す。1本あたり尺×解像度で課金
   （30秒720p=145cr）。"ここぞ" の本命クリップ用。

既定は blurpad で量産し、反応の良いものを reframe で作り直す運用を推奨。

## 7. 見どころ選定の方針

- 一次スクリーニングは `select_highlights.py`（visual/label/audio のキーワードスコア）。
- 最終判断はセッション内で Claude がシーン解析全文を読み、以下の基準で決める:
  - 冒頭1秒でフックになる画があるか（Shorts は最初の1〜2秒が命）
  - 1クリップ = 1つの見せ場（詰め込まない）、20〜45秒
  - オチ/変化で終わる（見せ場の直後で切る）
- 判断結果は `segments.json` を直接編集して反映（`focus_x` もクリップ毎に指定可）。

## 8. ファイル受け渡し

- チャットへの動画添付は MCP から読めない → **Google Drive / Box 経由**で受け渡す
  （Drive: `download_file_content`、Box: `get_file_content`）。
- 生成物の返却も Drive/Box アップロード、または Higgsfield の CloudFront URL を共有。

## 9. 未決事項 / 次アクション

- [ ] 実際の横型AI動画1本でA-2をエンドツーエンド実測（解析精度・選定品質・blurpad画質）
- [ ] reframe の画質検証（1クリップだけ課金して比較）
- [ ] ルートBの実制作1本（参照画像→Seedance 3カット→結合→virality チェック）
- [ ] 字幕/タイトル焼き込みの要否（AI動画は台詞なしが多い想定。必要なら drawtext 追加）
- [ ] 量産時の命名規約・Drive 保存先フォルダの確定
