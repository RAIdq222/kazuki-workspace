# UI-REVIEW-HANDOFF — 原図修正コンソール（生成・QC管理画面）レビュー引き継ぎ

外部レビュアー（ChatGPT/Codex等）向けの引き継ぎ文書。**今回はレビューが目的であり、
大規模なUI変更は行わない**。修正を入れる場合も「触ってほしくない箇所」「維持すべき業務要件」を守ること。

## 1. 管理画面の目的
商用アニメの背景**原図（genzu）修正**を自動化するコンソール。ラフな原図PSDから背景レイヤーを
抽出し、GPT Image 2（Higgsfield CLI）で清書した原図を生成、原図画角へ復元して品質管理する。
複数作品対応（現在: 佐々木とピーちゃん第2期#10=進行中 / 尚善#07=一時中断）。
美術監督がカット単位で「確認→生成/リテイク→OK/要修正判定」を回すための画面。

## 2. ブランチ / ディレクトリ
- **トランクは `main`**（常に全部入り・最新）。開発はセッション別ブランチ
  （現アクティブ: `claude/stoic-hopper-bezfdl`）→ 逐次 main へマージ。**レビューは main を見ればよい**。
- 未コミット/未pushの変更は無い（本文書コミット時点）。
- 管理画面コード: **`src/genzu_fix/server.py` 1ファイル**（Flask＋HTML/JS/CSS埋め込み。ビルド工程なし）。
- 関連バックエンド: `src/genzu_fix/`（`batch.py`=生成パイプライン, `prompt.py`=3層プロンプト,
  `psd_export.py`=PSD抽出, `image_aspect.py`=入出力グリッド, `qc.py`=自動QC, `naming.py`, `conte.py`=コンテOCR）。

## 3. 起動方法
```
# Windows（実運用）
run_console.bat            # 内部で PYTHONPATH=src を通して genzu_fix.server を起動
# 汎用
python run_console.py      # または PYTHONPATH=src python -m genzu_fix.server
```
- **ポート: 8765**（`--port` で変更可）。http://127.0.0.1:8765
- 必要な環境変数: **UI表示だけなら不要**。生成には Higgsfield CLI のログイン
  （`higgsfield auth login`）、QCのvision判定（任意 `--qc-vision`）とstaging生成スクリプトには
  `ANTHROPIC_API_KEY` が必要。
- 作品レジストリ: 起動時に `runs/project_*.json` を全て読み、作品×話数タブを構成する。
  パスがローカルに無い作品はスキップされる（＝レビュー環境ではPSDが無くてもUIは起動する。
  カット0件になるので、UI確認は `tests/console_e2e.py` のフィクスチャ方式を参照）。

## 4. 主要な画面・機能と担当箇所（すべて server.py 内）
| 機能 | 担当 |
|---|---|
| カット一覧画面 | JS `render()`＋`PAGE` テンプレ。フィルタ（担当/状態/未生成/QC） |
| カットカード | JS `card(u)`。状態は左帯＋チップ、OK/要修正は右上ミニボタン、サムネクリック→詳細 |
| 詳細モーダル | `#dmodal`＋JS `openDetail/dShow/dGenerate/dSaveStage` 等。画角記述(staging)・プロンプト・リテイク・生成の操作ハブ |
| 原図/生成結果の比較 | `#cmp`＋JS `openCmp/setCmpMode`。横並び/スライダー/重ね合わせ(透過)の3モード |
| OK/要修正（QC判定） | JS `accept(id,v)` → `POST /api/unit/<uid>/accept`（console_state.json に保存） |
| 自動QC | 生成後に `qc.evaluate`（プログラム判定）＋任意で `qc.vision_check`。カードにQCバッジ |
| 一括生成 | JS `genBatch(scope)` → `POST /api/generate_batch`。`GEN_QUEUE`＋ワーカースレッド（`--max-parallel` 既定3）。冪等（生成済み/PSD無しはスキップ） |
| 原図の取り直し | `#gmodal`＋`POST /api/unit/<uid>/recapture`（ソース: base/visible/レイヤー選択） |
| 話数概要・主要ボード | `GET /api/overview`。ボード出現数の集計表示 |

## 5. 技術構成
- **フロント**: フレームワーク無しの素のHTML/CSS/JS（server.py 内の `PAGE` 文字列）。npm/ビルド無し。
- **バックエンド**: Flask（開発サーバ・単一プロセス）。生成はスレッドワーカー＋キュー。
- **データ保存**: 全てファイルベース。
  - 判定・カット別設定: `<出力先>/console_state.json`（uid→ {status, board, staging, retake_note,
    prompt, takes, adopted, genzu_source, genzu_rev, ...}。**STATE_LOCK下で原子的に保存**）
  - 生成物: `<出力先>/<uid>/`（input.png / restored_full.png / prompt.en|jp.txt / qc.json / takes/take_NN/）
  - 静的レジストリ: `runs/project_*.json`（作品）, `runs/works.json`, `runs/cut_scene_info_*.csv`（C層）,
    `runs/board_map_*.csv`（カット→ボード）, `runs/staging_sp2_10.csv`（画角記述の自動下書き）
- **API**: JSONの素朴なRESTふう。主要: `/api/projects` `/api/units` `/api/unit/<uid>`（詳細+プロンプト）
  `/api/unit/<uid>/{generate,accept,board,board_ref?,retake_note,staging,prompt,recapture,adopt,open}`
  `/api/generate_batch` `/api/jobs` `/api/overview` `/img/<uid>/{genzu,result,board}` `/board-img`
- **テスト**: `tests/console_e2e.py`（Playwright。フィクスチャで実PSD不要）＋
  `tests/{psd_export,naming,assets,koban,batch_queue}_test.py`。実行例:
  `PYTHONPATH=src python tests/console_e2e.py`（chromium必須・無ければSKIP）

## 6. 状態管理の設計
- **サーバ側が唯一の真実**: `STATE`（console_state.json）と `JOBS`（メモリ上の生成ジョブ）。
  UIは `/api/units` を再取得して `render()` で全カード再描画（差分レンダ無し）。
- 再描画時に開いていた `<details>`・入力途中のテキスト・フォーカスを退避→復元する
  （`render()` 冒頭。**このガードを壊さないこと**）。
- 生成中はジョブポーラ（`pollJobs` 2.5s間隔）が RUN 集合を更新。busy=0で自動停止。
- 画像キャッシュ: 原図プレビューは `genzu_<source>_<rev>.png`＋URLに `?v=<source><genzu_rev>`。
  抽出規則を変えたら server.py の `_PREVIEW_REV` を上げる規約。

## 7. データ構造の要点
- **unit**（カット）: `{id, cuts[], filename, assignee, scene, board, status, has_psd, has_result,
  qc_verdict, takes[], adopted, retake_note, staging, genzu_source, genzu_rev, gen_error, ...}`
- status 遷移: `todo → generating → done →（人が）accepted | reject`。doneは「生成済み未判定」。
- staging（画角・場面の言語記述）は **手動(state) > 自動下書き(staging_map CSV)** の優先。
- プロンプトは3層（A=GLOBAL/B=SCENE/C=CUT）＋[SHOT]=staging＋[IMAGES]＋[EYE LEVEL]。
  作品ごとに `genzu_trust`（"high"=原図の幾何を正とする忠実清書 / "rough"=修正パス）を宣言。

## 8. 既知の問題・暫定実装
- **構図の制御が最重要課題**: 参照画像では構図が伝わらない（実測）。言語記述(staging)が主チャンネル。
  比率まで書けば通ることを確認中（歩留まり未計測）。
- 料亭・バー等のシーンは該当美術ボードが未着（board_map 空欄）。
- 重複PSD（GKV/old と 優先順位高 等）はスキャンで先勝ち・警告のみ。staging CSVにも重複行あり（後勝ちで実害なし）。
- PANカット・束ねカット(022_025)・_Rリテイク版の生成は未検証。
- Flask開発サーバのまま（認証なし・ローカル前提）。
- 尚善#07 は一時中断中（データ・プロファイルは残置。壊さないこと）。

## 9. 今後実装予定
- staging自動下書きの品質確認→83カット展開→歩留まり計測（同条件複数回）
- 画調（線密度・タッチ）の合否基準づくりとB層プロファイルのSP2展開
- 白紙級カットの運用確立 / PSD書き戻し（insert_result_layer）のSP2検証

## 10. Codexに触ってほしくない箇所（変更禁止・要相談）
- `src/genzu_fix/prompt.py` の GLOBAL/GLOBAL_TRUST 本文と3層構造（実測で練った文言。1語の変更が生成品質を変える）
- `src/genzu_fix/psd_export.py` の抽出規則（実PSD86本で検証済み。`tests/psd_export_test.py` が仕様）
- `src/genzu_fix/image_aspect.py` の入出力グリッド（レジストずれ解決の根幹。docs/design-notes §20）
- `console_state.json` のキー名・意味（後方互換必須。既存の判定データを失わない）
- `/api/*` ルート名と `/img/*`（JSと外部スクリプトが参照）
- `runs/` 配下のデータCSV/JSON（生成データ。手で整形・再フォーマットしない）
- 日本語コメント・UTF-8エンコーディングを維持。ファイル全体の再フォーマット禁止

## 11. UI改善時にも維持すべき業務要件
1. **原図が正**（SP2）: UIは常に「原図＝基準、生成結果＝候補」の主従で提示する
2. OK/要修正は**人間の最終判定**であり、自動QCはあくまで参考バッジ
3. 生成は**テイク履歴**を残す（上書きしない）。採用テイクの切替が常に可能
4. 手動staging・手動プロンプトは自動値より常に優先。自動更新で人の編集を消さない
5. 再描画で編集中の入力を失わない
6. 一括生成は冪等（生成済み・PSD無しをスキップ）で、失敗はカット単位で隔離
7. ボード画像は「表示・比較・意匠辞書」であり、構図の根拠として使わない
8. 変更後は `PYTHONPATH=src python tests/console_e2e.py` がALL PASSであること
