# マスター素材ファースト・パイプライン（無劣化）

> 2026-07-07 再設計。ユーザー指摘:「Clipper経由は字幕焼き込み＋再エンコードで素材が
> 劣化する。元動画は手元にあるのだから、劣化させずに見どころ抽出→縦型化できるはず」。
> 以後、**切り抜き制作とシーンライブラリ取り込みの主経路はマスター素材**とし、
> Personal Clipper は「マスターが入手できない動画の暫定フォールバック」に降格する。

## 1. 素材の受け渡し（ユーザー → ワーカー）

- **置き場**: Google Drive のマスター素材フォルダ（リンク共有）。
  1動画=1ファイル、ファイル名は `<YouTubeID>_<タイトル簡略>.mp4` 推奨
  （YouTube IDが入っていると、ライブラリの「▶ この場面から再生」に直結できる）
- **推奨フォーマット**: 完パケと同一解像度以上のH.264/H.265。
  **字幕なし書き出しがあればベスト**（テロップ前の素材）。完パケしか無くても
  Clipper経由と違い追加劣化ゼロなのでそのまま置いてよい
- 取得方法: Drive MCP（`download_file_content`）または
  `drive.usercontent.google.com/download?id=<fileId>&confirm=t`（リンク共有時）。
  数百MBでも問題なし（実測済みの経路）

## 2. 切り抜きショート制作（shorts-from-video の主経路）

1. **取り込み**: Driveからマスターをダウンロード → `work/masters/<id>.mp4`
2. **見どころ抽出**（従来のローカル解析。Clipperの自動選定は不要）:
   - `python -m src.shorts.analyze_local`（whisperで台本起こし＋シーン検出）
   - Claudeがトランスクリプト＋フレームを見てEDL（切り出し秒リスト）を決める
3. **縦型化**: `python -m src.shorts.make_shorts`（crop/blurpad・focus・モンタージュ）
   - 入力がマスター解像度（1080p+）なので出力品質はClipper(720p再エンコード)より上
   - 音声つなぎは audio bed（複数区間クロスフェード）で処理
4. セルフチェック（review_sheet）→ メタデータ（package_short）→ 納品
   ※字幕チェック工程は**マスターに字幕が無い場合は省略できる**

## 3. シーンライブラリ取り込み（scene-library の主経路）

- `python -m src.shorts.scene_ingest <master.mp4> --video-id <id> --start-seconds 0`
  - マスターは動画全体＝タイムスタンプが**そのまま元動画秒**（復元計算不要）
  - **`--crop-bottom 0`（デフォルト）**: 字幕なしマスターならクロップ不要＝無劣化フレーム
  - 完パケ（字幕入り）しか無い場合のみ `--crop-bottom 0.14〜0.26`
- 以降（タグ付け→media_upload→POST /api/agent/scenes）は同じ

## 4. Personal Clipper の位置づけ（フォールバック限定）

使ってよいのは以下のみ:
- マスターが存在しない/提供されない動画（例: 他者の動画のremake分析）
- 至急でマスター受け渡しを待てないとき

制約を必ず認識すること: **字幕OFF設定が存在しない**（必ず焼き込み）・720p再エンコードで
劣化・ショートURLはクリップ0本で失敗することがある。Clipper由来のフレームは
`--crop-bottom` で字幕帯を落とす（＝さらに画角も失う）。

## 5. 移行メモ

- 既存ライブラリのClipper由来シーン（初期シード11件）は、マスター入手後に
  同タイムスタンプの無劣化フレームで**置き換え可能**（scenesのframe_media_id/frame_urlを
  PATCHで差し替え。テーブル設計は変更不要）
- ダッシュボードの切り抜きカード（type=clip）はYouTube URL入力のまま。ワーカーが
  URL→YouTube ID→Driveマスターの突き合わせを行い、無ければユーザーにマスター提供を依頼する
