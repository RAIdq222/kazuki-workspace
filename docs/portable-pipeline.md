# Higgsfield 非依存版パイプライン 設計案

> 2026-07-06 ドラフト。目的: 本人以外（チーム/他クリエイター）にも配れる形にする。
> 現行の Higgsfield/MCP 依存版は `docs/shorts-pipeline.md`。編集の型は `docs/shorts-editing-style.md`。

## 0. 方針

現行パイプラインのうち **Higgsfield が担っているのは「頭脳」部分だけ**で、
編集の実体（切り出し・縦型化・結合）は既に ffmpeg ローカル処理＝依存ゼロ。
したがって差し替えるのは次の3点:

| 工程 | 現行 (Higgsfield) | 置き換え候補 |
|---|---|---|
| ① 動画理解（シーン解析） | video_analysis | Gemini API（動画ネイティブ対応）/ ローカル(PySceneDetect+Whisper) |
| ② 見どころ選定 | Claude セッション内の判断 | 任意のLLM API＋プロンプトテンプレート（型を明文化済みなので移植可能） |
| ③ ゼロから生成（ルートB） | Seedance 2.0 via MCP | Seedance直API(BytePlus)/ fal.ai・Replicate / Veo(Gemini API)/ Kling 等 |

縦型化は編集スタイル分析の結論により **crop（ローカル・無料）が正解**なので、
reframe(AI外挿) の代替は原則不要。必要になった場合のみ外部API（Runway等）を検討。

## 1. 推奨構成（配布版）

```
[入力] 動画ファイル or YouTube URL
   │
   ├─ ① 解析: Gemini API (gemini-3-flash 等)
   │     ・動画をネイティブ理解。YouTube URL を直接渡せる（DL不要）のが最大の利点
   │     ・structured output で scenes JSON を直接取得（現行スキーマ互換にする）
   │     ・コスト目安: 数分の動画で数円〜十数円のオーダー（モデル/解像度設定で変動、要実測）
   │     ・代替(APIキー不要): PySceneDetect(カット検出) + faster-whisper(文字起こし)
   │       → 精度は落ちるが完全無料・オフライン
   │
   ├─ ② 選定: LLM に scenes JSON + 編集スタイルガイドを渡し、モンタージュEDLを生成
   │     ・プロンプトテンプレート化（どのLLMでも可: Gemini/Claude/GPT）
   │     ・出力 = segments.json (cuts配列) → 人がレビュー・微調整
   │
   ├─ ③ 編集: ffmpeg（既存 src/shorts/ をそのまま利用。依存なし）
   │     ・yt-dlp で元動画取得（ユーザーのPC/サーバーなら制限なし）
   │     ・make_shorts.py: マイクロカット切り出し → crop 9:16 → 無劣化結合
   │
   └─ ④ (任意) ルートB生成: プロバイダアダプタ経由
         ・Seedance: BytePlus ModelArk の直API、または fal.ai / Replicate 経由
         ・Veo: Gemini API 経由（参照画像対応）
         ・アダプタIF: generate(prompt, aspect, duration, ref_images) -> mp4_url
```

### 配布形態

- **Python CLI** (`pip install` 一発 or uv)。コマンド例:
  ```
  shorts analyze <url|file> -o scenes.json          # ①
  shorts select scenes.json -o segments.json        # ②（LLM呼び出し）
  shorts cut <file> segments.json -o out/           # ③（完全ローカル）
  ```
- 必要な資格情報は環境変数1つ（例 `GEMINI_API_KEY`）から始められるのが理想。
- Claude Code / MCP はあくまで「このリポジトリでの開発・運用の道具」とし、
  配布物はそれらに依存しない。

## 2. 各工程の比較詳細

### ① 動画理解

| 方式 | 精度 | コスト | 備考 |
|---|---|---|---|
| Gemini API | 高（映像+音声を統合理解、タイムスタンプ付き記述可） | 低（従量、動画は秒あたりトークン換算） | YouTube URL直接入力可。**推奨** |
| Higgsfield video_analysis | 高 | プラン内 | 現行。MCP必須・個人アカウント紐付き |
| PySceneDetect + Whisper | 中（映像意味理解なし。カット境界+セリフのみ） | 無料 | オフライン要件がある場合の保険 |
| GPT-4o / Claude (フレーム抽出) | 中〜高 | 中 | 動画→フレーム画像サンプリングの前処理が必要 |

### ② 見どころ選定（＝このプロジェクトの独自価値）

`docs/shorts-editing-style.md` の型を **プロンプトテンプレート**に落とし込む:

```
入力: scenes.json（①の出力）
指示: フック→飯テロ接写⇔リアクション交互→オチ の順で 8〜15 マイクロカット、
      各1〜3秒・合計16〜34秒のEDLを組め。セリフはフレーズ完結、等（ガイド全文を同梱）
出力: segments.json (cuts配列、note付き)
```

テンプレートはLLM非依存に書く。キーワードスコアの `select_highlights.py` は
LLM不使用時のフォールバックとして残す。

### ③ 元動画の取得

- 配布版の前提は「ユーザー自身のマシンで実行」なので **yt-dlp が素直に動く**
  （今回のサンドボックスの403はこの実行環境固有のegress制限）。
- 自作動画なら書き出し元ファイルをそのまま使うのが最良（再圧縮なし）。

### ④ ルートB（ゼロから生成）のプロバイダ候補

| プロバイダ | モデル | 特徴 |
|---|---|---|
| BytePlus ModelArk | Seedance 直API | 現行と同モデルを直接。参照画像/一貫性が強み |
| fal.ai / Replicate | Seedance, Kling, Wan, Hunyuan 等 | 1つのAPIキーで複数モデル比較可。**検証に便利** |
| Google Gemini API | Veo 系 | 音声付き生成・参照画像。Google課金に集約可能 |
| ローカル (Wan 2.x 等) | OSS | GPU必須。コストゼロだが品質/速度は要検証 |

アダプタ層を1枚挟み、`--provider seedance-byteplus / veo / fal:kling` のように
切替可能にする。価格は各社改定が頻繁なため、実装時に get-cost 相当を必ず挟む。

## 2.5 実装状況（2026-07-06 実装・検証済み）

**「見どころ検出」「縦型化」は外部サービスゼロ（ローカルOSSのみ）で成立することを実証済み。**

| モジュール | 実装 | 依存 |
|---|---|---|
| `analyze_local.py` | シーン境界(ffmpeg scdet) + 音量プロファイル(astats) + 文字起こし(faster-whisper small/int8/CPU) → Higgsfield互換 scenes JSON | ffmpeg, faster-whisper (全てOSS・無料) |
| `focus.py` | crop注視点の自動推定: アニメ顔検出(lbpcascade_animeface, MIT) → 動き重心フォールバック | opencv-python-headless <5 |
| `make_shorts.py --auto-focus` | focus_x 未指定カットを自動推定してモンタージュ結合 | 同上 |

実測（29秒・実映像クリップ, CPUのみ）: シーン境界15箇所・発話12区間・全処理数十秒。
whisper の注意: BGM混在素材では `vad_filter=False` + `language='ja'` 必須（VADが発話を落とす）。
文字起こしは small モデルだと誤字が出るが、見どころ選定用途には十分。精度が要る場合は
`--whisper-model medium/large-v3` に上げる（CPUだと処理時間増）。

**残る非ローカル要素は「映像の意味理解」のみ**（例:「黄身が割れる瞬間」の識別）。
- Claude Code セッション運用では、フレーム画像を抽出して Claude 自身が見る（追加API不要）
- 配布版では (a) 文字起こし+構造情報だけで選定（人がレビュー） (b) Gemini 等のAPIをオプション追加
  の2段構え。**APIなしでも成立し、APIを足すと選定が賢くなる**という位置づけにする。

## 3. 移行ステップ（案）

1. **P1**: `providers/` 抽象化 + Gemini 解析プロバイダ実装（scenes JSON を現行スキーマ互換に）
2. **P2**: 選定プロンプトのテンプレート化（`prompts/select_montage.md`）+ `shorts select` コマンド
3. **P3**: CLI 化（analyze/select/cut の3コマンド、README、APIキー設定手順）
4. **P4**: ルートB アダプタ（fal.ai から着手が検証効率よい）
5. 現行 Higgsfield 版は「Claude セッション運用の高速路」として並存させる

## 4. 運用メモ

- Drive のドラフト運用（初稿→2稿→3稿…）: パイプラインは**フォルダ全読みせず、
  指定された1ファイル（または最新稿）だけ**を対象にする。
  ファイル名末尾のバージョン（`_v3` 等）か更新日時で最新を判定する規約にする。
