---
name: scene-library
description: 天使ちゃんシーンライブラリの取り込み（過去動画→タグ付きフレーム→検索DB）と、生成時の「同一シーン参照」ルール。「ライブラリ取り込みして」「シーン追加して」で使用。設計は docs/scene-library-design.md。
---

# シーンライブラリ運用

ダッシュボード: https://summer-bell-707.higgsfield.app（APIトークン: `work/agent_token.txt`）

## A. 取り込み（1動画ずつ。夜間cronのBの後に1〜3本）

**主経路はマスター素材（無劣化。docs/master-pipeline.md）**:

1. **マスター取得**: Driveのマスター素材フォルダから該当動画をダウンロード
   （ファイル名のYouTube IDで突き合わせ）
2. **フレーム抽出**:
   `python -m src.shorts.scene_ingest <master.mp4> --video-id <id> --start-seconds 0 -o work/scenes/<id>`
   （タイムスタンプはそのまま元動画秒。字幕なしマスターならクロップ不要＝
   `--crop-bottom 0` のデフォルトのまま）

**フォールバック（マスターが無い動画のみ）— Clipper経由**:

1. `personal_clipper_create`（16:9・clips_num=20。ショートは9:16だが
   **クリップ0本で返る不具合あり**→同じ舞台が映る本編回で代替）。
   各クリップの `start_seconds` を控える
2. クリップごとに `--start-seconds <s>` と **`--crop-bottom 0.14〜0.26`**（字幕焼き込みの
   除去。Clipperに字幕OFF設定は無い）を付けて scene_ingest を実行。
   マスター入手後は同タイムスタンプの無劣化フレームで差し替え可
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

カット生成の前に、そのカットの舞台・行動でライブラリを**セマンティック検索**する
（v8: Gemini埋め込み gemini-embedding-001@768 のコサイン類似。自然文でよい）:

```bash
python3 -m src.shorts.scene_search "<自然文。例: いただきますしているシーン>" \
  --limit 5 [--place 部屋] [--min-quality 3]
```

- 仕組み: クエリをローカルで埋め込み → agent API に `qvec` として渡す。
  **エージェント文脈のWorkerは外部APIへのegressが遮断されている**ため、
  `q=` だけの検索は辞書フォールバックになる。生成フローでは必ずこのCLIを使う
  （ダッシュボードのブラウザ検索はセッション文脈なのでegressが通り、そのままセマンティック）
- 前提ファイル: `work/agent_token.txt`, `work/gemini_api_key.txt`（git管理外）
- シーン追加・キャプション・**expression_detail**（表情・視線ディテール1文。
  上目遣い/伏し目/半眼/むくれ等の語彙で画に忠実に。顔が写らないカットは空）を
  修正したら再埋め込みが必要: `python3 -m src.shorts.embed_backfill`
  （export→RETRIEVAL_DOCUMENTで埋め込み→`POST /api/agent/scenes/vectors`）。
  docテキストはアプリ側 sceneDocText と一字一句一致:
  `${caption}（場所:${place}／行動:${action}／表情:${expression}／構図:${shot}／時間帯:${time_of_day}）`
  ＋ expression_detail 非空なら末尾に `表情ディテール: ${expression_detail}`。
  Gemini無料枠は約100件/分（429は70s待ちで再試行）

- **ヒットした場合のみ**（quality>=2、舞台が本当に一致するものに限る）:
  frame_media_id をスタートフレーム生成／Seedanceの参照に追加する
- **ヒットしない場合は使わない**。「近いだけの別シーン」を無理に参照すると
  かえって嘘の内装・嘘の照明が固定されるため、参照なし＋プロンプトのみで生成し、
  結果が良ければその生成物を将来のライブラリ候補としてメモする
- 固定の基本セット（ルック参照・部屋/屋外セット・小物）は docs/character-tenshichan.md 参照

## C. 権利ルール

登録対象は自チャンネル動画のみ。remake元（他作品）のフレームは分析専用でライブラリに入れない。
