# セッション間 受け渡し（改訂版）— 分担: 分析=great-edison / 生データ=stoic-hopper

## 確定した分担
- **原図理解（構図/EL/配置/remove/破綻の読み取り、`situation`/`remove` 記入）= great-edison（当方）がやる。**
  当環境の Read ツールは PNG を画像として閲覧できるため、原図PNGさえあれば当方で分析可能。
- **stoic-hopper は生データを渡すだけ。** 解釈・記入は不要。

## ① 既に git にある＝再依頼不要（合意）
- `runs/ledger.jsonl`（30行）, `runs/cut_scene_info_ep7.csv`（place/time/structures/era 済み・空きは situation/remove のみ）,
  `runs/cut_board_map_ep7.csv`, `runs/boards_ep7.json`, `runs/board_manifest_ep7.*`。
- → 旧・依頼B(ledger/場面メタ) と 依頼C(ボード索引) は解決済み。

## ② 唯一の必要物 = 原図PNGの受け渡し（PSDではない）
理由: 当コンテナは `work/` 不在＋`psd_tools` 未導入。PSD(30–500MB)の base64 取得は不可。
対象10カット: **15, 23, 47, 53, 207, 240, 257, 274, 293, 294**。各カットについて:

- **body.png**（ヘッダー除去済み・原図の中身全体）… 当方の「原図理解」用。**必須。**
- **padded.png**（出力寸ぴったりの生成入力）と **manifest.json**（psd/region/aspect/scale/canvas寸）
  … 当方で生成まで回す場合に必要。回さないなら省略可。

### 渡し方（どれか一つ。git が確実）
- 推奨: `runs/genzu_png/<cut>/body.png`（＋ padded.png, manifest.json）として **`git add -f`**
  （`work/` 配下を避ければ .gitignore に当たらない）→ 当方ブランチへ pull できる形でコミット。
- 代替: Drive の専用フォルダに10枚アップロード（当方が MCP で取得）。
- ※ ボード画像（IMAGE2）も2枚入力に進めるなら、対応ボードPNGも同梱してくれると一括で進む。

## ③ 当方の現状
- GLOBAL(A層)=「修正パス」三分割に改訂済み・push 済み（`src/genzu_fix/prompt.py`）。
- `runs/prompt_test_10scenes_ep7.md` は新GLOBALで再生成済み（CUT層は汎用のまま）。
- ②のPNGが来たら: 各カットを閲覧→`situation`/`remove`＋構図/EL/破綻を記入→CUT層を具体化→
  プロンプト作り直し→（padded.png があれば）Higgsfield 生成まで当環境で実行可能。

## ④ 確認したい小さな分岐
- 生成の実行はどちら持ち? 当方で回すなら padded.png＋manifest を、そちらで回すなら body.png だけでよい。
- cut240 のボード不整合（scene=森_よどんだ朝 / board=寺院内寝室 → 道観_寝室に解決）の正はどっちか。
- 束カット(016_026 等)は1ファイル=1生成でよいか。
