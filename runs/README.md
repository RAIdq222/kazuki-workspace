# runs/ のファイル索引（何が正典で、何が派生/旧か）

セッション間で「どれを読めばいいか」を迷わないための一覧。迷ったらまずここ。

## カット表・索引
| ファイル | 役割 | 状態 |
|---|---|---|
| `cut_board_map_ep7.csv` | **正典**。カット→原図PSD→美術ボード→担当（245行/217原図/8班） | ◎使用中 |
| `genzu_index_ep7.csv` | cut_board_map から board 列を除いた索引版（カット→原図） | doc参照のみ |
| `ep7_cut_board_map.csv` | 旧・初期調査版（11行, 日本語ヘッダ）。コード参照なし | 旧（歴史的） |
| `cut_index.example.csv` | design-notes 用のスキーマ例 | doc例 |

## 話数メタ・ボード
| ファイル | 役割 |
|---|---|
| `ep_overview.json` | 話数のあらすじ/シーン展開/主要ボード（コンソール上部に表示） |
| `boards_ep7.json` | 美術ボード画像ファイル名の一覧（コンソールの選択肢フォールバック） |
| `board_manifest_ep7.csv` / `.md` | ボード→シーン群→時間帯→使用カット（Drive ID付き） |
| `scene_profiles/*.json` | シーン固有の背景語彙（place/era/structures/avoid）＝プロンプトB層 |
| `scene_coverage_ep7.md` | scene_profile の整備状況（カバー率） |

## プロンプトCUT層・コンテOCR（great-edison 主管）
| ファイル | 役割 | 状態 |
|---|---|---|
| `cut_scene_info_ep7.csv` | カット別 situation/remove（プロンプトCUT層）。conte→Vision で充足 | 充足途中 |
| `conte_v2_ep7.csv` | **コンテOCRの正典**（per-cut 構造化） | ◎使用中 |
| `conte_v2_ep7.baseline.csv` | 再OCR前のスナップショット（訂正差分の基準） | 派生 |
| `conte_v2_ep7.reocr.csv` | 再OCR時点のスナップショット（現状 baseline と同一） | 派生 |
| `conte_overrides_ep7.csv` | OCR手動訂正の上書き（現状ヘッダのみ＝空） | 枠 |
| `conte_glossary_ep7.md` | OCR精度向上の用語集（登場人物/絵コンテ用語/尺記法/場所） | ◎使用中 |
| `conte_frames_v2_ep7.json` ほか | コンテ抽出の中間JSON | 中間 |

> `conte_v2_ep7.csv` が正。`baseline`/`reocr` は snapshot（`conte.py` が差分表示に使うので消さない）。

## 生成・受け渡し
| ファイル | 役割 |
|---|---|
| `ledger.jsonl` | 過去の生成記録（手動試行の遺物含む）。**実行時の台帳は `<out>/ledger.jsonl`（work側・非git）** に出す |
| `handoff_DATA_README.md` / `handoff_request_for_data_session.md` | セッション間データ受け渡しの説明/依頼 |

## 注意
- `runs/` は git 管理（＝共有される）。生成の中間物・大きな画像は **`work/`（.gitignore）** へ。
- `handoff/ep7/` は「PSDが無いセッションが原図/資料を読むための入力」として**意図的に git 管理**
  （`scene_understanding.py` / `fetch_asset.py` が読む）。ただし全カット分を入れると肥大するので、
  `run_gather.bat` は投入前にサイズ警告を出す。
