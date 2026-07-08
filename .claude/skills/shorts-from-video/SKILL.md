---
name: shorts-from-video
description: 横型(16:9)のAI動画ファイルから見どころを抽出して縦型(9:16)ショート動画を作る。動画ファイル(ローカル/Drive/Box)またはYouTube URLを受け取ったら使用。
---

# 横型動画 → 縦型ショート 作成手順

設計背景は `docs/shorts-pipeline.md` を参照。コストが発生する手順は事前に金額を伝える。
**編集の型（必読）**: `docs/shorts-editing-style.md` — 参照ショート6本の実測分析。
連続区間の切り出しではなく「フック→飯テロ接写⇔リアクション交互→オチ」の
マイクロカット・モンタージュ（1カット1〜3秒、全体16〜34秒、crop フルフレーム）が基本形。

## 0. 入力の確認（**マスター素材ファースト** — 詳細: docs/master-pipeline.md）

- **最優先: マスター素材（無劣化）**。YouTube URLを受け取った場合も、まず
  Driveのマスター素材フォルダに該当動画（ファイル名にYouTube ID）が無いか探す。
  あれば手順1（ローカル解析）へ——Clipper(720p再エンコ・字幕焼き込み)より
  高解像度・字幕なしで、後段のクロップ劣化も不要になる。
  無ければユーザーにマスター提供を依頼し、待てない場合のみ手順Y（フォールバック）へ
- **動画ファイルの場合** → 手順1へ。チャット添付は読めないため、Google Drive か Box に
  置いてもらい MCP でダウンロードする。
- ユーザーに確認すること（未指定なら既定値）: 本数（既定3）、1本の尺（既定20〜45秒）、
  縦型化モード（既定 blurpad。crop / reframe(有料) も可）。

## E. 納品物（マスター経由の場合は必ず両方）

1. **完パケmp4**＋upload.txt（package_short）
2. **EDL XML**: `python -m src.shorts.export_xmeml_edl <master> <segments.json> -o <name>_EDL.xml
   --name <題名> --source-name "<ユーザーのローカルのマスターファイル名>"`
   — 元動画1本への in/out タイムスタンプでシーケンスを組んだ xmeml。ユーザーが
   Premiereで開いてローカルのマスターにリリンクすれば、切り貼り構造ごと微調整できる。
   音声ベッドはA1/A2交互にクロスフェード分重ねて配置済み（クロスフェード適用で完パケと同尺）

## Y. YouTube URL ルート（フォールバック限定。字幕焼き込み・720p劣化あり）

前提知識: この実行環境は egress IP がリクエスト毎に変わるため **yt-dlp での
YouTube 直接ダウンロードは不可**（メディアURLがIP紐付きで403）。素材の取得は
Personal Clipper をサーバー側ダウンローダーとして使う。

1. **素材取得**: `mcp__Higgsfield__personal_clipper_create`
   - urls=[URL], clips_num=3〜6（多いほど素材カバレッジ増）, **clip_aspect="16:9"**
   - 字幕は無効化できない（下部に焼き込み）→ 後段の `--trim-bottom 0.15` で切り落とす
   - `personal_clipper_status` で完了待ち（5〜30分）。長引くなら send_later で自己チェック
2. **クリップDL**: 各 cdn_url を curl でローカル保存（CloudFront は egress 許可済み）
3. **内容確認**: `analyze_local.py` で文字起こし＋シーン境界 → 見どころ候補の時刻から
   `ffmpeg -ss <t> -i clip.mp4 -frames:v 1 f.jpg` でフレーム抽出して**自分の目で確認**
4. **EDL作成**: `docs/shorts-editing-style.md` の型でモンタージュ EDL（cuts配列）を書く
   - カット境界がシーン変わり目を跨いでいないかフレームで検証する（重要）
   - **音声は「音声ベッド方式」が既定**: segments に `"audio_bed": {"start": <秒>}` を
     付けると、カット毎の切り貼りではなく元音声の連続区間が敷かれる
     （BGM/セリフの繋ぎ目破綻を防ぐ。参照ショートと同じ構造）。
     ベッド区間に良いナレーションが乗るよう、映像カットは時系列順を基本にし、
     口元が大写しのカットはセリフ位置とだいたい合わせる
   - **音声パートを途中で削る場合**（尺調整・不要フレーズ除去）は複数パート形式:
     `"audio_bed": {"parts": [{"start": s1, "end": e1}, {"start": s2, "end": e2}],
     "crossfade": 0.3}` — フレーズ境界で切り、クロスフェードで接続。
     **接続点は映像のカット替わりと同じ位置**に置くと編集点として自然になる。
     ベッドは必ず文末まで含める（言い切り前で切らない。末尾0.4sフェードは語尾の後に）
   - 映像カットの合計秒数 = ベッドの合計秒数（クロスフェード分 -0.3s/接続）に合わせる
5. **生成**:
   ```bash
   python3 -m src.shorts.make_shorts <clip.mp4> <edl.json> -o out/ \
     --mode crop --auto-focus --trim-bottom 0.15
   ```
6. **セルフチェック（改善ループ・必須）**:
   ```bash
   python3 -m src.shorts.review_sheet out/short_01.mp4 <edl.json> -o review/
   ```
   機械チェック（解像度/尺16-34s/音声/字幕残り2種のエッジ密度）を確認したうえで、
   review/ の各カット mid/join フレームを**自分の目で見て**以下を検品する:
   - 字幕・黒帯の残り（ナレーションが長い区間は字幕2行 → その cut だけ
     `"trim_bottom": 0.24` に上げる）
   - カット途中でシーンが変わっていないか（mid と join の絵が別物なら境界ズレ）
   - **音と映像の意味ズレ**: review.json の audio_text_overlap と cut の note を突き合わせ、
     動作カット（合掌・投入・すすり等）が対応するセリフ位置に載っているか
   - framing（被写体の見切れ。ダメなら focus_x を手動指定）
   問題があれば EDL を直して再ビルド → 再チェック（1〜2周で収束するのが普通）
7. **完パケ**: タイトル・説明文・タグは **`docs/shorts-metadata-style.md` のルールに従う**
   （タイトルにすべての情報を載せる・末尾に #深夜のドカ食い天使ちゃん・絵文字なし。
   説明文は `src/shorts/data/tenshichan_description.txt` の定型文そのまま。tags固定4種）。
   meta.json を書き `python3 -m src.shorts.package_short` でパッケージ →
   `SendUserFile` で mp4 + upload.txt を納品
8. 制約を毎回伝える: 素材は Clipper が選んだ窓に限られる。フル素材で作りたい場合は
   Drive リンク共有（高画質・全範囲）か配布版CLI（ユーザーPCで yt-dlp）を案内

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

## 3-L. シーン解析（ローカル・推奨。外部サービス不要）

```bash
pip install faster-whisper "opencv-python-headless<5" numpy   # 初回のみ
python3 -m src.shorts.analyze_local work/shorts/<name>/source.mp4 \
  -o work/shorts/<name>/analysis.json
```

- シーン境界・音量・文字起こしが入った Higgsfield 互換 scenes JSON が出る。
- 映像の意味（何が映っているか）は含まれないため、見どころ候補の各区間から
  `ffmpeg -ss <t> -i source.mp4 -frames:v 1 frame.png` でフレームを抽出して
  **自分(Claude)で画像を見て**内容を確認しながら EDL を組む。
- crop の注視点は `--auto-focus`（手順5）で自動推定できる（アニメ顔検出→動き重心）。

## 3. シーン解析（Higgsfield 版・代替）

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
`docs/shorts-editing-style.md` の型に従って `segments.json` を**モンタージュ形式**
（`cuts` 配列 = 並べ替え済みEDL）で書き直して確定する:

- フック: 本編クライマックスの「食べている最中/料理ドン」の1〜2秒から始める
- 飯テロ接写(1カット=1セールスポイント) と 顔リアクション を1〜3秒で交互に
- セリフはパンチライン1フレーズまで。フレーズ途中で切らない
- 最後はオチ（空の皿/ギャグ/カメラ目線）で即終了。全体16〜34秒
- crop の注視点はカット毎に `focus_x` (0.0-1.0) で調整

確定した segments.json の内容（カット表と選定理由）をユーザーに報告する。

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
