---
name: shorts-from-idea
description: 元動画なしでゼロから縦型ショート動画を企画・生成する。参照画像＋Higgsfield MCPのSeedance 2.0で9:16動画を生成し、必要なら複数カットを結合する。
---

# ゼロから縦型ショートを作る手順（Seedance 2.0）

設計背景は `docs/shorts-pipeline.md` を参照。**動画生成は全て有料**なので、
生成前に必ず get_cost で見積り、合計金額をユーザーに伝えて了承を得る。

> **天使ちゃん案件は必ず docs/character-tenshichan.md の「ルック制御の勝ちパターン」
> に従う**: Seedance 2.0 に参照を**直渡し**（`image_references`＝ルック参照2〜3枚＋舞台参照）。
> スタートフレーム静止画は原則作らない。三面図＋テキストの直行生成は禁止。
> **nano_banana系は使用NG（マスピ調化・ユーザー裁定）**。画像生成を使うのは
> 「背景のみのロケーション設定画」が必要な場合のみで、モデルは GPT Image 2。
> 生成前に**シーンライブラリで同一シーンを検索**（`python3 -m src.shorts.scene_search`）し、
> **ヒットした場合のみ** frame_media_id を舞台参照に追加する（無い場合は無理に使わない）。
> 手順: .claude/skills/scene-library/SKILL.md §B

## 0. 音声ルール（全生成共通・厳守）

- **生成動画の音声はSE/環境音のみ。セリフ・ナレーション・歌は入れない**（VO=声優後録り）
- プロンプトに発話誘発ワードを書かない: talks / says / speaking / chatting /
  narrates / vlogger voice 等はNG（口パクが要る場合は
  `mouth moves silently as if talking — do NOT generate any voice` と書く）
- プロンプト末尾に必ず入れる:
  `AUDIO: strictly no human voice, no speech, no narration, no singing —
  only ambient sounds / SE. She does not speak at any point.`
- **生成後チェック（必須）**: faster-whisper(language='ja', vad_filter=False)で
  セリフ混入を検出。混入していたら同じ start_image で音声指示を強めて再生成する

## 1. 企画（案出し）

ユーザーのテーマから複数案（3案程度）を出して選んでもらう。各案は:

- **フック**（最初の1〜2秒で目を引く画）→ **展開** → **オチ/余韻** の3構造
- 合計尺 15〜60秒、カット割り: 1カット4〜15秒（Seedance の制約）× N本
- 各カットに: プロンプト（英語推奨）、尺、参照画像の使い方（identity維持か画風参照か）

## 2. 参照画像の用意

- ユーザー提供: Drive/Box 経由で受け取り → `media_upload`(image) → PUT → `media_confirm`
- Web上の画像: `media_import_url`
- 無ければ生成: `generate_image`（**GPT Image 2** のみ・**背景のみのロケーション設定画**に限る。
  nano_banana系は使用NG=マスピ調化。キャラ入り静止画は作らず Seedance に参照直渡し）

## 3. カット生成（Seedance 2.0）

カット毎に `mcp__Higgsfield__generate_video`:

```
model: "seedance_2_0"
aspect_ratio: "9:16"
duration: 4〜15（秒）
resolution: "720p"（本命は "1080p"、mode="std" のとき 4k まで）
mode: "std"（急ぎ・ラフは "fast"、ただし 720p まで）
generate_audio: true/false
medias: [
  { value: <media_id>, role: "image_references" },   // キャラ/物のidentity維持
  { value: <media_id>, role: "start_image" },        // 最初のフレーム固定（任意）
]
prompt: <カットのプロンプト>
```

- 目安コスト: 10秒 720p std = 45cr。先に get_cost=true で全カット分見積る。
- カット間の一貫性: 同じ image_references を全カットに渡す。**連続シーンは前カットの
  終端フレームを ffmpeg で抽出→media_upload→次カットの image_references に渡す**
  （床と一体化v3で確立。部屋・照明・服装・小物が繋がる）。
- **1生成マルチカット方式（調理・ルーティン系の密度高いモンタージュ向け・推奨）**:
  15秒1回の生成に `cut1:/cut2:/…` 形式で10〜16カットを書き込むと、カット割り済みの
  モンタージュが1発で出る（カルボナーラ実証: 12カット67.5cr。個別生成の1/5コスト）。
  プロンプト構成は「全体ルール(BGMなし等)→#制約(画角を変える・画風維持・文字禁止)→
  #登場人物→#情景→#シーン(感情トーン)→cutN列(各カットに環境音明記)→AUDIO定型文」。
  弱点: カット単位のリテイクができない(全取り直し)ので、ストーリー物より
  工程見せ・仕草のモンタージュに向く。衣装は参照画像でなくテキストで指定する
  （顔参照の服に引っ張られるため）。
- 生成結果はジョブIDで返る。完了待ち→プレビューURLをユーザーに共有し、
  カット単位でOK/リテイクを確認（リテイクは最大2回を目安に、都度コスト提示）。

## 4. カット結合（複数カット構成のとき）

`mcp__Higgsfield__explainer_video`:

- items: 完成カットの job_id を再生順に並べる（結合自体は無料）
- width/height: 720×1280（720p生成時）または 1080×1920
- 字幕が要る場合のみ subtitles を付ける（0.05cr/ブロック）

## 5. 事前チェックと納品

1. `mcp__Higgsfield__virality_predictor` (action="create") でフック強度・リテンションを確認
   し、弱ければフックカットだけ作り直しを提案。
2. 完成動画のURLを共有。ローカル保存が必要なら CloudFront URL から curl でダウンロードして
   Drive/Box にアップロード。
3. 使ったプロンプト・job_id・参照画像の対応を `work/shorts/<name>/production.json` に記録
   （リテイク・続編制作の再現用）。
