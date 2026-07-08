# 天使ちゃんシーンライブラリ 設計書

> 2026-07-07 起草。ユーザー要望:「過去動画からセマンティック検索——『天使ちゃんが家に
> いるシーン』『寝てる顔』『いただだきますしているシーン』等——ができ、その画像を
> 生成の参照に使え、さらにその場面からYouTube再生までできるライブラリ」。
> 本日の手作業（ルック参照・シーン別参照の抽出）は本ライブラリのPhase 0（実証）にあたる。

> **2026-07-08 更新（v8）**: 検索は辞書ベース（FTS/同義語）を廃し、埋め込みベクトルの
> セマンティック検索へ移行済み。構成＝Gemini `gemini-embedding-001`（768次元・L2正規化、
> doc側 RETRIEVAL_DOCUMENT／query側 RETRIEVAL_QUERY）＋ D1 `scenes.embedding` BLOB
> （f32 LE、migration 0009）＋ Worker内ブルートフォースコサイン（335件<1ms）。
> docテキストは `${caption}（場所:${place}／行動:${action}／表情:${expression}／構図:${shot}／時間帯:${time_of_day}）`。
> **egress制約**: Workerの外向きfetchはログインセッション文脈のみ許可されるため、
> ブラウザ検索はWorkerが直接埋め込み、エージェント/生成フローは
> `python3 -m src.shorts.scene_search`（ローカル埋め込み→`qvec`渡し）を使う。
> ベクトル投入も同様にローカル計算→`POST /api/agent/scenes/vectors`。
> 辞書検索（v7.3）はキー無し/APIエラー時のフォールバックとして残置。

## 1. 全体像

```
[取り込み（バッチ・AIワーカー）]
  Personal Clipper（全動画フルカバレッジ）→ フレーム抽出・間引き
  → Claudeが画像を見て構造化タグ＋キャプション付け → 字幕除去クロップ
  → Higgsfield media（参照用media_id）＋ D1（メタデータ）

[検索（スタジオアプリ新タブ「シーン検索」）]
  自然文検索（FTS＋同義語展開）＋ ファセット絞り込み（場所/行動/表情/画角/時間帯）

[利用]
  ① 「参照に使う」→ media_id をコピー / 既存カードの refs に追加
  ② 「▶ この場面から再生」→ youtu.be/<video_id>?t=<秒>（新規タブ or 埋め込み）
```

## 2. データモデル（D1・migration 0007想定）

```sql
CREATE TABLE scenes (
  id TEXT PRIMARY KEY,             -- uuid
  video_id TEXT NOT NULL,          -- YouTube ID
  video_title TEXT NOT NULL,
  episode TEXT NOT NULL DEFAULT '',-- 「15話・牛丼」「ショート・部屋紹介」等
  t_start REAL NOT NULL,           -- 元動画の秒（Clipperのstart_seconds+クリップ内オフセットで復元）
  t_end REAL NOT NULL,
  frame_media_id TEXT NOT NULL,    -- Higgsfield media（字幕除去済み・参照に直接使える）
  frame_url TEXT NOT NULL,         -- CloudFrontサムネURL
  place TEXT NOT NULL,             -- 部屋/キッチン/玄関/ベランダ/夜の街/住宅街/店内/会社/その他
  action TEXT NOT NULL,            -- 食べる/いただきます/寝る/歩く/走る/スマホ/料理/ぬい/叫ぶ/…
  expression TEXT NOT NULL,        -- 笑顔/恍惚/泣き/怒り/ジト目/真顔/驚き/照れ/…
  shot TEXT NOT NULL,              -- 顔アップ/バスト/全身/後ろ姿/物・背景のみ
  time_of_day TEXT NOT NULL,       -- 昼/夕方/夜/深夜
  caption TEXT NOT NULL,           -- 自由文1〜2文（検索の主対象）
  quality INTEGER NOT NULL DEFAULT 2, -- 参照適性 1-3（3=そのまま参照に使える）
  created_at INTEGER NOT NULL
);
-- 日本語検索用にFTS5（bigramトークナイズ）: caption + 各タグを索引
CREATE VIRTUAL TABLE scenes_fts USING fts5(caption, place, action, expression,
  content='scenes', tokenize='trigram');
```

## 3. 取り込みパイプライン（AIワーカーがバッチ実行）

対象: 本編14本＋ショート24本（順次、cronで1晩1〜3本）

1. **Clipper でサーバー側取り込み**（この環境はYouTube直DL不可のため）:
   16:9・clips_num=20 でほぼ全編をカバー。各クリップの `start_seconds` が返るので
   **クリップ内オフセット＋start_seconds＝元動画タイムスタンプ** が復元できる（実証済み）。
   ※ショートはclips_num=1〜2。今回「部屋紹介」はクリップ0本で返る不具合があったため、
   ショートで失敗した場合は同じ舞台が映る本編回で代替する
2. **フレーム抽出・間引き**: fps=0.5 → シーン検出(select=gt(scene,0.3))＋pHash近傍dedupで
   1動画あたり代表30〜60枚に
3. **タグ付け**: Claudeが画像を見て §2 の閉集合タグ＋自由文キャプションをJSONで出力
   （語彙を閉集合にするのが検索安定のキモ。新語彙は設計書を更新してから追加）
4. **字幕除去**: 下部の焼き込み字幕帯をクロップ（1行≈14%、2行≈26%。quality=3のみ）
5. **登録**: media_upload→confirm、`POST /api/agent/scenes`（バルク）でD1へ

コスト: Clipperは実測無料枠内。タグ付けはClaudeトークンのみ（≈40枚×38本≒1,500枚）。
生成クレジットは消費しない。

## 4. 検索の実現方式（段階導入）

| Phase | 方式 | 体験 |
|---|---|---|
| 1（アプリv7） | FTS5全文検索＋同義語辞書（「いただきます」→合掌・食前 等）＋ファセットチップ | 「家にいるシーン」→ place=部屋系 で即ヒット。実用上これで大半カバー |
| 2 | チャット/ワーカー連携: 「〜なシーン探して」とAIに投げると検索→候補提示→カードrefsに直挿入 | 完全な自然文・曖昧クエリ対応 |
| 3（任意） | キャプションの埋め込みベクトル検索（プラットフォームでベクトルDBが使えるようになったら） | 类似画像・ニュアンス検索 |

## 5. アプリUI（v7: ライブラリタブ内に「シーン検索」セクション）

- 検索バー＋ファセットチップ（場所/行動/表情/画角/時間帯）→ サムネグリッド
- 結果カード: フレームサムネ / エピソード名＋タイムコード / タグチップ
  - **[参照にコピー]** media_idをクリップボードへ
  - **[カードに追加]** ピッカーで企画カードを選び refs へPATCH
  - **[▶ この場面から再生]** `https://youtu.be/<video_id>?t=<floor(t_start)>` を新規タブ
    （埋め込みは iframe `?start=` でモーダル表示も可）
- カード詳細の参照ピッカーに「ライブラリから選ぶ」導線を追加

## 6. 権利・運用ルール

- 登録対象は**自チャンネルの動画のみ**（remake元の他作品フレームは登録しない）
- 参照利用は生成の image_references / 静止画参照に限る（素材としての切り貼りはしない）
- 追加された動画は公開翌日にワーカーが自動取り込み（cron: 新着チェック→パイプライン）

## 7. 実装順（提案）

1. **v7アプリ改修**: scenes テーブル＋agent API（POST /api/agent/scenes, GET検索）＋
   シーン検索UI（1回のサブエージェント改修で完了する規模）
2. **初回バッチ**: 本編の直近3本（13〜15話）＋部屋・チル系ショート3本から開始
   （=今日手動で作った屋外/部屋セットがそのまま初期データになる）
3. 夜間cronに取り込みジョブを追加 → 全38本を1週間程度で完了
