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
  本文はp3〜（p1表紙・p2白紙）。赤バツ＝欠番。
  **OCR本走 完了（2026-07-15）**: 109ページ→312カット（総カット314とほぼ一致・通し番号1〜313）。
  成果物 `runs/conte_v2_sp2_10.csv`。verify異常4件のみ（cut45/68/222/246のtime混入）。
  用語集に実測を反映済み（主要5人確定、シバドン/佐元神/比売神等は**アバドン**の誤読ゆれ疑い）。
  **レイヤー規則 v3（2026-07-15）**: 実地で fallback 7本（全て `_BG_Book*` 統合レイヤー構成）と
  005型のBGグループ空（実背景はLOグループ内_BG）が判明 →
  ①Book除外は「Bookで始まる名前」のみ（_BG_BookはBG本体として採用）
  ②合成が空（全面透明/完全単色）なら次候補へ落ちる ③候補に「グループ内ネスト_BG」を追加。
  合成PSDテスト `tests/psd_export_test.py` で3構造＋尚善回帰を固定。
  → **v3で確定（2026-07-15）**: 実データ86本＝BG 85 / BG(nested) 1 / fallback 0。
  base画像の目視OK（005=LO内_BGのブラインド窓が復活、007=_BG_Book採用、006=BG+PAN合成）。
  レイヤー抽出はこれで確定。
  **コンテ→プロンプト配線 完了（2026-07-15）**: `scripts/build_cut_info_from_conte.py` で
  `runs/conte_v2_sp2_10.csv`＋シーン範囲表(`runs/scene_ranges_sp2_10.csv`)→
  `runs/cut_scene_info_sp2_10.csv`（312カット・era=現代日本明示・低信頼OCRのsituationは不採用）。
  project json の cut_info に配線済み＝コンソール/batchのプロンプトに[シーン][カット]が入る。
  **ボード紐づけ 完了（2026-07-15）**: SP2ボードは`SP/SP2_世界_場所_時間帯`命名（104枚・1期流用込み）。
  scene_ranges に board 列を追加→`runs/board_map_sp2_10.csv`(cut,board)を生成、
  server の scan 構成が board_map で自動紐づけ（確信のある3レンジのみ: 会議室/お隣さんの部屋/
  爆発後アパート＋発生前夜景。料亭・バー・夜の街対峙はボード未存在=空→プルダウン手動）。
  **テスト生成の知見（2026-07-17, c005）**: パイプライン一気通貫は成功（新CLI対応:
  改行でWindowsのコマンドラインが分断→引数全損に注意・batch側で畳み済み）。
  ボード全景参照は原図の構図を乗っ取る（役割宣言だけでは2回とも敗北）。
  断片化案は**却下**（「どの角度から見た場所か」の情報が死ぬ・黒江さん指摘）。
  **確定方針: ボードは全景で渡し、プロンプトで権限を「意匠辞書」に狭める**
  （許可=原図に在る要素の意匠・材質・線密度の解釈のみ／禁止=構図・家具配置・
  開口部・部屋の続きの補完。batch [IMAGES]）。合わせてGLOBALに「存在の定義=原図」を
  追加、[SCENE]の什器列挙を削除（補完の燃料）、[CUT]のキャラ芝居ト書きを不採用に
  （環境描写のみ通す）。**密度参考BG・隔離空間の輪郭線について.jpg は線画の参考ではない**
  （黒江さん確認済み。線画タッチの根拠として扱わない）。
  **次: 上記プロンプトv2でc005再テスト → 構図維持と意匠反映の両立を確認**。

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
