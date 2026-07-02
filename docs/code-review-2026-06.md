# 全体構造レビュー（2026-06 / main@08a36a1）

3方向（コア機構・コンソール/運用・機能ギャップ）の並行レビュー結果の統合。
優先度と対処は `docs/TODO.md` に反映済み。ここは根拠（ファイル:行つき）の詳細版。

## 総括 — 最大のテーマは「部品は揃ったが、配線されていない」
個々のモジュール（レジスト・3層プロンプト・コンテOCR v2・場面理解・QC・パース）は完成度が
高いのに、**互いを繋ぐブリッジが未実装**のため価値が流れていない：

1. **conte v2 → cut_scene_info が断線**（conte.py:206 merge は v1 形式前提。v2 の出力に
   situation/characters フィールドが無く流し込めない）→ プロンプトCUT層が 245カット中ほぼ空のまま。
2. **qc.py がどこからも呼ばれていない**（batch/server とも import ゼロ）。ledger.qc は枠だけ。
   コンソールの OK/要修正（console_state.json）と ledger.qc が完全分断。
3. **scene_understanding は cut274 の1本で止まっている**。出力(runs/scene_understanding/)を
   cut_scene_info へ書き戻す merge が無く、バッチ実行ドライバも無い。
4. **cli.py が確定前提と真逆の既定**（cli.py:41,44 = 自動ヘッダ切除＋visible取り出し。
   §20.6 確定は「切らない＋Base」）。cli 経路で生成すると結果が食い違う。
5. **perspective 系（perspective.py / perspective_editor.py / UXPプラグイン）はパイプラインと
   完全に独立**。使い道（生成前QC/ガイドレイヤー返し/リテイク指示素材）の方針が未決。

## A. 事故リスク（高）
- **server.py STATE のロック不整合**（:390,396,402,412,443,260）: 変更がロック外、
  `_save_state` の json.dump 中に並行変更→ console_state.json 破損→ **次回起動不能**
  （_load_json:57 に例外処理なし）。→ 変更+保存をロック内ヘルパに集約、tmp→os.replace の
  アトミック書き、読み込みにフォールバック。
- **生成の同時実行数制御なし**（server.py api_generate:434）: uid単位ガードのみで
  連打すると Higgsfield 多重起動（レート制限・クレジット浪費）。→ セマフォ(~8)+キュー。
- **失敗カットが「生成中」のまま固まる**（server.py:282-285）: 例外時に STATE.status を
  戻さない。urlretrieve(batch:214)・subprocess(batch:84) に timeout なし → 永久 running 化し
  そのカットが再生成不能。→ except で status 復帰、DL/CLI に timeout、running のリセット導線。
- **バッチが冪等でない**（batch.py main）: 既生成スキップ・失敗リトライ・途中再開なし。
  再実行＝全件再課金。→ ledger/出力有無でスキップ、失敗のみ再試行。

## B. バグ（中）
- `_genzu_preview`（server.py:210）キャッシュが PSD mtime / genzu_source を見ない。
  base/visible が同一ファイル名で、process_cut も同名を上書き → 「Photoshopで直して確認」で
  古い絵が出る。→ mtime 比較＋`visible_{source}.png` に分離。
- ledger の書き先が **git管理下の runs/ledger.jsonl**（相対パス）: 生成のたび dirty、
  複数マシンで conflict。cut ID 形式も混在（shz_02_143 / shz_07_272_genzu）。
  → 実行時は `<out>/ledger.jsonl`、共有分は明示的に集約。ledger.load は壊れ行1つで全滅（:46）。
- perspective.py:499 `_anthropic_vision` が画像未縮小で base64 送信（4000px級で API 400）。
  scene_understanding.py:474 には縮小あり＝非対称。
- scene_understanding.py:517 が HTTPError で SystemExit（リトライ無し、429一発で観点1-3の
  結果ごと捨てる）。conte.py:430 には retry4 がある＝ポリシー分裂。
- batch.py:259 boards_dir 索引に拡張子フィルタ無し（server 側の _BOARD_EXTS+PNG変換と非対称）
  → PSDボードが _prep_board/PIL に渡り失敗し得る。
- scene_understanding.py:247 コンテ行の int キー化で枝番(16A)が16に潰れる。
- server.py:104 _board_png キャッシュキーが正規化名のみ→同名別拡張子で衝突可。

## C. 共通化（同じロジックの多重実装）
- **cut番号→PSD解決が3実装**（render_genzu:31 / scene_understanding:410 / gather_handoff:46）
  → `genzu_fix/resolve.py` に一本化。PSD再帰walk索引も5箇所→同モジュールへ。
- **Anthropic REST が4実装**でtimeout/retry/縮小ポリシーばらばら
  （conte:105, conte:430, scene_understanding:495, perspective:499）
  → `genzu_fix/anthropic_client.py`（retry+timeout+縮小+JSON抽出）に集約。
  JSON抽出パーサ3コピー・カット番号正規化3コピー・モデル名等の定数3箇所も同時に。
- 死にコード: batch.build_prompt（呼び出し元ゼロ）、perspective_editor /api/render、
  dashboard.py（旧世代・参照ゼロ）→ 削除 or「旧」明記。

## D. 設計負債
- **パッケージ化なし**（pyproject.toml 不在）→ PYTHONPATH ハックとランチャが増殖。
  `pip install -e .` + console_scripts で恒久解消。
- server.py PAGE=315行インラインHTML/JS（perspective_editor も同様）→ static/ 分離。
  esc() が引用符未エスケープで board名の `'` が JS を壊し得る。
- 相対パス散在（ledger:14, conte:554,838,952 等が CWD 依存。scene_understanding だけ
  ROOT アンカー方式）→ ROOT 方式に統一。
- image_aspect.probe_output_size が永続化されない（「観測で更新」が実現していない）。
- **テスト**: Playwright e2e 3本のみ・pytest 収集不可・CI なし。ユニットテスト最優先対象＝
  image_aspect ラウンドトリップ / psd_export レイヤー選択 / prompt 3層 / conte の
  _cut_key・ページ跨ぎ統合 / naming.parse_cut_codes。
- 束カットは**離散が確定仕様**（154_169 は cut154 と cut169 の2カット。実データ・実装とも一致）。
  naming.py:74 の古いコメントだけ更新して明文化する。

## E. データ・リポジトリ衛生
- **handoff/ep7 のPNGが51MB**（pack 55MBの大半）: 役目（受け渡し）は完了済み。
  → git rm（今後は LFS or 都度削除）。run_gather.bat にサイズ警告。
- 旧CSV残置: ep7_cut_board_map.csv（旧11行・紛らわしい）/ cut_index.example.csv /
  genzu_index_ep7.csv（cut_board_map の実質重複）→ 削除 or archive、`runs/README.md` を置く。
- conte_v2 変種: baseline と reocr が**バイト同一**（片方冗長）、overrides は空、
  正は conte_v2_ep7.csv → README で明示。
- work/conte_crops/ 48ファイルが gitignore を無視してトラック済み（規約矛盾）→ git rm --cached。
- run_console.bat が自前規約（.batはASCII）違反 ／ BOARDS/OUT の存在チェック無し ／
  run_gather.bat が他人のマシンでも kuroe 名義を自動 set（→未設定なら中断に変更）。
- docs 乖離: NEXT-SESSION.md は旧世代（削除/archive）、runbook のコンソール節が旧UI記述、
  TODO.md がmain統合前のまま、sessions.md に wonderful-allen（パース系）ブランチ未記載、
  CLAUDE.md 索引に perspective/conte 系ツール未掲載。UXPプラグインは「実機未検証」を明記。
- 統合済みブランチ（stoic-hopper/great-edison）の削除 or アーカイブ明記。

## F. 実装すべき機能（優先度）→ docs/TODO.md 参照
S1 一括/並列生成＋キュー ／ S2 冪等バッチ（スキップ・リトライ・再開）／
S3 QC自動フラグ配線（qc.evaluate→ledger→コンソール⚠）／
S4 situation/remove 充足の実行（gen-info 全担当化＋conte merge2）／ S5 テイク履歴。
A: レイヤー手動オーバーライドUI（バックエンド済・配線のみ）／指示付きリテイク／コスト記録／
PSD無し7カットの方針／aspect固定ルール。
B: キーボード操作・一覧強化／scene_understanding 量産統合／ep8展開の脱ハードコード
（プロジェクト設定JSON＋香盤表→cut_board_map 生成ツール）／ledger⇔console 突合。
C: perspective 系の位置づけ決定／ダーク背景・サムネ拡大／handoff 完全版。
