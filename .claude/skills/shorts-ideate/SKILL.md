---
name: shorts-ideate
description: トレンド収集＋自由発想で企画カードを量産し、ダッシュボード「天使ちゃんスタジオ」のボードへ直接投入する。remake（天使ちゃん変換）や切り抜き依頼などのワーカータスク処理も行う。「ネタ出しして」「スタジオのタスク処理して」で使用。
---

# ネタ出し＆スタジオワーカー

型とルールの本体は `docs/shorts-ideation.md`（必読）。
ダッシュボード: https://summer-bell-707.higgsfield.app （APIトークン: `work/agent_token.txt`）

## A. ネタ出し（カードをボードへ直接投入）

ユーザーは**生のトレンドではなく完成した企画カード**を見て採否を判断したい。
トレンド→カードの1:1変換に縛られず、自由に発想すること。

1. トレンド収集: `python3 -m src.shorts.trends -o work/trends/trends_$(date +%m%d).json`
2. **発想（プロセスv2必須）** — `docs/shorts-ideation.md §8` の手順で行う:
   25本プレミス→ルーブリック採点→上位のみ過剰化パス→タイトルテスト。
   「あるある」で止まっている案（過剰さ・自虐の突き放し・狂気の画が無い案）は捨てる。
   素材は以下をミックスする:
   - トレンド由来 2〜3案（トレンド2つの掛け算も可。例: サッカー×寝溜め）
   - **発想シード由来 2〜3案**（トレンド不使用）:
     季節・曜日・時事の生活イベント（月曜、給料日前、猛暑、健康診断…）／
     天使ちゃんの生活の未公開領域（休日の過ごし方、実家、会社の給湯室、コンビニ…）／
     定番型の続編（部屋紹介第2弾、苦手なことシリーズ…）／if妄想（もし天使ちゃんが◯◯だったら）
   - 実績ある型①②③（生活公開/ミーム参加/不器用チャレンジ）を優先、⑤チルは多くて1
   - NG: 政治・事故・訃報・下品。飯テロに逃げない
3. 各案に: タイトル（メタデータルール準拠）/ memo（**docs/shorts-script-style.md §6 の
   カット別脚本フォーマット必須**: フック絵の静止画テスト＋■カット別設計
   （各≤15s・1動作ビート列+1カメラムーブ・[SE]・[VO-Ｍ/声]と口パク要否・
   生成プロンプト日本語）＋オチのパターン明記。
   セリフは§1の**プロファイル8箇条**で書き（皮肉ゼロ・NGワード確認）、
   実ヒットのセリフに混ぜて違和感チェック）/
   prompt（キャラ定型記述込みSeedance英語プロンプト。カット1=フック絵）/ source（元ネタ表記）
4. **ボードへ投入**（summary=「何が面白いか」1文は必須。ボードの一覧に表示される）:
   ```bash
   TOKEN=$(cat work/agent_token.txt)
   curl -sS -X POST https://summer-bell-707.higgsfield.app/api/agent/cards \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"cards":[{"type":"idea","title":"...","summary":"...","memo":"...","source":"...","prompt":"..."}]}'
   ```
5. ユーザーには投入した件数と各案の1行サマリだけ報告（詳細はボードで見る）

## B. ワーカータスク処理（flash / remake / 切り抜き依頼）

1. タスク取得:
   ```bash
   curl -sS https://summer-bell-707.higgsfield.app/api/agent/tasks \
     -H "Authorization: Bearer $TOKEN"
   ```
   **進捗ラベル（全タスク種別で厳守）**: 各工程の開始時に
   `PATCH /api/agent/cards/:id` で `worker_stage` を更新する。ダッシュボードが
   この文言＋プログレスバーを表示する。使う文言（この5つから・完了時は空文字""に戻す）:
   「元ネタを解析中」→「企画を執筆中（フック/展開/オチ）」→
   「カット別プロンプトを設計中」→「検証カットを生成中」→（完了=""＋status更新）。
   途中でエラー停止する場合も worker_stage を "" に戻してから終了する
2. **flash（フラッシュアイデア展開）** — flash=1 で memo が空のカード。
   ユーザーが1文で投げたネタ（title に入っている）を、docs/shorts-ideation.md の
   ヒットDNA＋docs/shorts-script-style.md §6 フォーマット（プロファイル8箇条準拠）で
   **フルショート案に展開**:
   - title をチャンネル文法のタイトルに磨き直し（元の1文の意図は保持）
   - summary（何が面白いか1文）/ memo（フック絵＋30秒脚本＋オチパターン）/
     prompt（Seedance英語）を PATCH で書き込み
   - **auto_generate=1 の場合**: そのまま検証1カットを生成（Seedance 9:16 720p ≤10s、
     上限50cr）→ jobs登録 → status「レビュー」。auto_generate=0 は status「アイデア」のまま
   - 元の1文がヒットDNA的に弱い場合も否定せず、過剰化パスで一段持ち上げて展開する
3. **remake（天使ちゃん変換）** — 「この動画/画像を天使ちゃんでやったらどうなる？」の自動検証:
   - youtube_url があれば `video_analysis_create(youtube_url)` でシーン解析、
     image_url があれば画像をダウンロードして自分の目で見る
   - **権利ルール（厳守）**: 元動画・元画像は分析にのみ使う。生成の参照素材
     （image_references/start_image等）には絶対に使わない。元作品の固有名詞・
     キャラ名・ロゴ・タイトルは企画からもプロンプトからも外す。生成は
     天使ちゃんの公式設定資料＋プロンプトのみで再設計する
   - 元ネタの「面白さの構造」を1行で特定し、天使ちゃんの文脈（OL/深夜/ぼっち/回復）に翻訳
   - 変換後の脚本は docs/shorts-script-style.md §6 フォーマットで書く（プロファイル8箇条準拠）
   - `PATCH /api/agent/cards/:id` で title/memo（変換企画）/prompt を書き込み
   - **検証生成（1カットのみ、上限50cr）**: `generate_video` model=seedance_2_0,
     aspect_ratio=9:16, duration≤10, resolution=720p, image_references=三面図
     （media_id: docs/character-tenshichan.md 参照）。job_id を
     `POST /api/agent/cards/:id/jobs` で登録し、status を「レビュー」に PATCH
   - 課金は実行アカウント（既定=オーナーのHiggsfield）。1タスク1検証カットまで。
     本制作はユーザーがカードを承認してから
4. **clip（YouTube切り抜き依頼）**: `/shorts-from-video` の手順で制作。
   - カードに **feedback** が入っている場合は再制作依頼: フィードバックを読んで
     EDL/クロップ/尺を修正して作り直す（過去の結果は残す）
   - 完成したら完パケをチャットで納品し、カードの status を「レビュー」に PATCH
5. **アーカイブ（完成処理）**: ユーザーがカードを「完成」にしたら（またはチャットで
   完成指示が来たら）、完成mp4を media_upload→PUT→confirm で恒久化し、
   `PATCH /api/agent/cards/:id` で final_video_url にCloudFront URLを設定

## C. 定期実行

- 毎朝のcron: A→B の順で1周（Aは6〜8案、Bは残タスク全部）
- 毎時の軽量ワーカーcron: **Bのみ**実行。タスクが空なら何もせず即終了（報告も最小限）
