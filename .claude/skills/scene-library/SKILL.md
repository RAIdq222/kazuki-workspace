---
name: scene-library
description: 天使ちゃんシーンライブラリの取り込み（過去動画→タグ付きフレーム→検索DB）と、生成時の「同一シーン参照」ルール。「ライブラリ取り込みして」「シーン追加して」で使用。設計は docs/scene-library-design.md。
---

# シーンライブラリ運用

ダッシュボード: https://summer-bell-707.higgsfield.app（APIトークン: `work/agent_token.txt`）

## A. 取り込み（1動画ずつ。夜間cronのBの後に1〜3本）

1. **Clipperで取り込み**: `personal_clipper_create`（16:9・clips_num=20でほぼ全編カバー。
   ショートは9:16・1〜2本だが**クリップ0本で返る不具合あり**→失敗したら同じ舞台が映る
   本編回で代替）。レスポンスの各クリップ `start_seconds` を控える
2. **フレーム抽出**: クリップごとに
   `python -m src.shorts.scene_ingest <clip.mp4> --video-id <id> --start-seconds <s> -o work/scenes/<id>_cN`
   （字幕クロップ: 1行≈`--crop-bottom 0.14`、2行≈`0.26`。Clipperは字幕OFF設定が
   存在しないため必ずクロップする）
3. **タグ付け**: フレームを目視し、**閉集合語彙**でタグ＋自由文キャプション1〜2文:
   - place: 部屋/キッチン/玄関/ベランダ/夜の街/住宅街/店内/コンビニ/会社/その他
   - action: 食べる/いただきます/調理/寝る/歩く/走る/スマホ/ぬい/叫ぶ/泣く/笑う/座る/その他
   - expression: 笑顔/恍惚/泣き/怒り/ジト目/真顔/驚き/照れ/寝顔
   - shot: 顔アップ/バスト/全身/後ろ姿/物・背景のみ
   - time_of_day: 昼/夕方/夜/深夜
   - quality: 3=参照にそのまま使える / 2=検索用 / 1=登録しない
   - 新語彙が必要になったら docs/scene-library-design.md を先に更新してから使う
4. **参照用アップロード**: quality=3 のみ media_upload→PUT→media_confirm で
   frame_media_id を取得（2は frame_url のみでよい→どこかに恒久URLが必要なので
   実運用は全て media_upload でよい。CloudFront URLが frame_url になる）
5. **登録**: `POST /api/agent/scenes`（Bearer、最大100件バルク）

## B. 生成時の「同一シーン参照」ルール（全生成フロー共通・厳守）

カット生成の前に、そのカットの舞台・行動でライブラリを検索する:

```bash
curl -sS "https://summer-bell-707.higgsfield.app/api/agent/scenes?q=<キーワード>&place=<場所>&limit=5" \
  -H "Authorization: Bearer $(cat work/agent_token.txt)"
```

- **ヒットした場合のみ**（quality>=2、舞台が本当に一致するものに限る）:
  frame_media_id をスタートフレーム生成／Seedanceの参照に追加する
- **ヒットしない場合は使わない**。「近いだけの別シーン」を無理に参照すると
  かえって嘘の内装・嘘の照明が固定されるため、参照なし＋プロンプトのみで生成し、
  結果が良ければその生成物を将来のライブラリ候補としてメモする
- 固定の基本セット（ルック参照・部屋/屋外セット・小物）は docs/character-tenshichan.md 参照

## C. 権利ルール

登録対象は自チャンネル動画のみ。remake元（他作品）のフレームは分析専用でライブラリに入れない。
