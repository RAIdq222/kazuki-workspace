# セッション台帳（誰が何を / ブランチ / 決定・未決）

> 可変情報の置き場。並行セッションはここを見て「相手が何をしているか」を把握する。
> 自分の担当・決定・未決を**追記**し、commit/push する。古い行は消さず取り消し線か日付で更新。

## 作品の状態（2026-07）
- **尚善 ep7 = 一時中断（優先度変更のため）**。到達点: レビュー由来の改修完了
  （事故防止/S1一括生成/S2冪等/S3自動QC/S5テイク履歴/Aレイヤー手動+指示付きリテイク/C衛生/
  B自動探索+香盤表パーサ）。**再開手順**: `git pull` → `run_console.bat` で即続行可能。
  残タスクは `docs/TODO.md`（B残: 共通化/pytest/scene_understanding量産統合、per-cut situation充足）。
  未決: ボード2枚入力の本採用 / cut240ボード正誤 / 香盤表パーサの実xlsx確認（1コマンド、TODO参照）。
- **佐々木とピーちゃん第2期(SP2) #10 = 着手（テスト）**。素材は会社Drive
  （担当別原図フォルダ「#10_佐々木とピーちゃん」＋「HOSHI様_20260714_…#10_テスト」パッケージ、
  ID群は `runs/works.json`）。命名は `SP2_10_006.psd` 形式（_genzu無し）→ naming.parse_cut_codes 対応済み。
  **用語の確定（2026-07-14）**: 原図修正＝**原図→原図**（ラフ原図を修正・清書した原図として返す）。
  「白黒線画ドラフトに変換」という旧表現は誤解を招くため CLAUDE.md から削除。
  画調の正解は作品ごとの参考資料（SP2は 密度参考BG／隔離空間の輪郭線について.jpg 等）に従う。
  **#10 進捗（2026-07-15）**: 原図83本＝納品済み分で確定（総カット314、続きは後着）。
  レイヤー抽出はSP2規則対応済み（`psd_export` v2: _BG/グループBG/_PAN、BOOK除外）→
  **未了: ローカルで `dump_layers` 再実行し strategy≒BG/PAN 全数＋005型BGグループ中身の目視確定**。
  コンテOCRは準備完了: 用紙=SILVER LINK（Cut|Picture|Action|Dialog|Sec）、列比率 **0.53,0.71,0.91**
  （--debug-crops で罫線一致確認済）、用語集 `runs/conte_glossary_sp2_10.md`、
  `conte.py --cut-map` パラメータ化（別作品でep7枝番表を誤用しない。SP2では `--cut-map ""`）。
  本文はp3〜（p1表紙・p2白紙）。赤バツ＝欠番。**未了: ローカル（APIキーあり）でOCR本走**。

## 並行ブランチの地図
| ブランチ | 役割 | 主な成果物 |
|---|---|---|
| **`main`（トランク）** | 全部入りの基準。新セッションはここから | 下記すべてを統合 |
| `claude/stoic-hopper-bezfdl` | ツール/コンソール/受け渡し基盤 | `src/genzu_fix/server.py`, `run_*.bat`, `scripts/render_genzu.py`, `scripts/gather_handoff_ep7.py`, `.claude/skills/read-genzu`, `CLAUDE.md` |
| `claude/great-edison-bk5g8c` | プロンプト設計/品質/シーン分析/コンテOCR | `src/genzu_fix/prompt.py` `conte.py` `scene_understanding.py`, `runs/scene_profiles/`, `runs/conte_v2_ep7.csv`, `scripts/fetch_asset.py` |

- 新セッションは **`main` から開始**（Web UIのブランチ欄を main に）。作業は feature ブランチ→ main へマージ。
- 相手の成果を使うときは `git fetch origin <branch>` → 必要ファイルを参照（または merge）。
- 2026-06 時点: main は great-edison の最新(d74b542系)＝stoic-hopperのマージを内包する superset から作成。

## 確定した決定
- レジストずれ＝入力=出力グリッドで解決。原図はフレームで切らない（ヘッダはプロンプト除去）。
- 原図の取り出しはコンソールも別セッションも `psd_export` の同じ関数（`/read-genzu`）。
  PSDが手元にあるセッションは `gather` 不要。**ただし `handoff/ep7/` は PSD が無いセッションの
  原図/資料アクセス経路として意図的に git 管理**（`scene_understanding.py`・`fetch_asset.py` が読む）。
  肥大するので全カット分は入れない／`run_gather.bat` は投入前にサイズ確認する（2026-07 訂正）。
- 生成の台帳(ledger)は実行時 `<out>/ledger.jsonl`（work側・非git）へ。`runs/ledger.jsonl` に直接追記しない。
- リポジトリ衛生: `work/`（含 conte_crops）は git 対象外。中間物は work/、共有物は work/ の外。
- 比較ビュー（コンソール）: 横並び / スライダー / 重ね合わせ(透過) の3モード。
- 話数概要＋主要ボードはコンソール上部に表示（`runs/ep_overview.json` / `cut_board_map` 集計）。
- カット個別の場面記述（synopsis の per-cut）は**保留**。

## 未決（ユーザー判断待ち）
- 美術ボード2枚入力（IMAGE2）に進めるか。
- cut240 のボード対応（森 or 寝室、どちらが正）。
- 出力 aspect の固定ルール（ledger に 16:9/3:2 混在）。
- 束カットは1ファイル=1生成でよいか／生成の分担（どのセッション/環境で回すか）。

## per-cut situation/remove（プロンプトCUT層の穴）
- `runs/cut_scene_info_ep7.csv` の `situation`/`remove` は未充足（絵コンテ→Vision で埋める設計）。
- 充足には原図＋コンテが要る。原図は `/read-genzu`、コンテは Drive `shz_07_conte_決定稿1025.pdf`（92MB・1本）。
- great-edison 側の担当。進めるなら scene_profiles と同じ対訳(JP/EN)形式で埋める。

## 更新ログ
- 2026-06: cross-session 共有レイヤー整備（CLAUDE.md / docs/sessions.md / read-genzu skill）。
