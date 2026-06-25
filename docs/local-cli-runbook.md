# ローカルCLI 実行ランブック（GKV担当カットを生成→保存）

目的: GKV担当の原図を、ローカルのターミナルで「生成→PSDへAIレイヤー差し込み→保存」まで回す。
生成バックエンドは公式 **Higgsfield CLI**（auth・アップロード・ポーリングを肩代わり）。

---

## 0. 前提（最初の1回だけ）

- **Node.js**（Higgsfield CLI 用）と **Python 3.11+**。
- このリポジトリを clone 済み。Python 依存:
  ```bash
  pip install psd-tools pillow numpy
  ```
- リポジトリ直下で実行する想定（`runs/cut_board_map_ep7.csv` を使う）。

## 1. Higgsfield CLI を入れてログイン
```bash
npm install -g @higgsfield/cli
higgsfield auth login        # ブラウザが開く。数秒で完了
```

## 2. 入力画像フラグ名を確認（重要・1回）
gpt_image_2 に入力画像を渡すフラグ名はバージョン差があるため確認する:
```bash
higgsfield generate create gpt_image_2 --help
```
`--image` / `--images` / `--reference-image` 等のどれかをメモ。既定は `--image`。
違う場合はバッチ実行時に `--image-flag <名前>` で指定する。

## 3. GKVの原図PSDをローカルに用意
GKVカット(15〜52)は Drive の
`原図フォルダ → 花家_復活の儀の部屋c014～052 → GKV`
（フォルダID `1XuKmSa8Rm7L5BvUfZE7YShdDZcxEQwDD`）にある。
このフォルダを丸ごとローカルに落とす。例: `~/shz07_genzu/GKV/`。
（バッチは `--genzu-dir` を再帰探索してファイル名で原図を探す）

## 4. まず DRY-RUN（生成せず確認）
prepだけ実行し、叩く higgsfield コマンドを表示する:
```bash
PYTHONPATH=src python -m genzu_fix.batch \
    --genzu-dir ~/shz07_genzu \
    --assignee GKV \
    --out work/batch \
    --dry-run
```
- 各カットの入力寸（例 2688x1520 / 2048x1360）と組み立てたコマンドが出る。
- `! 原図PSDが見つかりません` が出たら `--genzu-dir` の場所を確認。

## 5. 1本だけ本番（試運転）
```bash
PYTHONPATH=src python -m genzu_fix.batch \
    --genzu-dir ~/shz07_genzu --assignee GKV \
    --out work/batch --limit 1 \
    --image-flag --image          # 2で確認した名前
```
`work/batch/<cut>/` に成果物ができる:
- `input.png` … 生成入力（出力寸ぴったり）
- `gen_raw.png` … Higgsfield 生成結果（無加工）
- `restored_full.png` … 原図画角へ戻したもの
- `<cut>_AI.psd` … 元PSDに「AI原図修正」レイヤーを足したもの
- `runs/ledger.jsonl` に1行追記

仕上がりを確認してOKなら次へ。

## 6. GKV 全部を流す
```bash
PYTHONPATH=src python -m genzu_fix.batch \
    --genzu-dir ~/shz07_genzu --assignee GKV \
    --out work/batch --image-flag --image
```
- 束カット（016_026 等）は同一PSD=1回だけ生成。
- 失敗は最後にまとめて表示。続行される。

## 7. ダッシュボードで状態確認（任意）
```bash
PYTHONPATH=src python - <<'PY'
import csv, json, re
from genzu_fix import dashboard, ledger as L
rows=[]; defaults={}
for r in csv.DictReader(open("runs/cut_board_map_ep7.csv", encoding="utf-8-sig")):
    m=re.match(r"(\d+)", r["cut"])
    rows.append({"cut_num":int(m.group(1)) if m else 0,"cut_label":r["cut"],
                 "filename":r["filename"],"assignee":r["assignee"],"scene":r["scene"]})
    if r["board"].strip(): defaults[r["cut"]]=r["board"]
rows.sort(key=lambda r:(r["cut_num"],r["cut_label"]))
def labs(cf):
    m=re.match(r"shz_07_(.+?)_genzu",cf) or re.match(r"shz_07_(.+)",cf)
    return [str(int(x.group(1)))+x.group(2) for t in (m.group(1).split("_") if m else [])
            for x in [re.match(r"(\d+)([A-Za-z]*)",t)] if x]
gen=set()
for r in L.load():
    if r.get("cut","").startswith("shz_07_"): gen.update(labs(r["cut"]))
boards=json.load(open("runs/boards_ep7.json"))
html=dashboard.render_genzu_list(rows,board_options=boards,generated_cuts=gen,defaults=defaults)
out=dashboard.timestamped_path("work/genzu_list.html"); open(out,"w",encoding="utf-8").write(html)
print("wrote",out)
PY
```
生成済みカットが「生成済(緑)」になる。

---

## オプション / 調整
- `--assignee 野田` などで担当を変えれば他班も同じ手順で回せる。
- `--limit N` … 先頭N本だけ（試運転）。
- `--prompts-dir prompts/` … `prompts/<cut>.txt` があればプロンプトを上書き（カット個別調整用）。
- `--resolution` / `--quality` … 既定 2k / high。
- 美術ボードは v1 では「場所/時間/構成物」のヒントとしてプロンプト文に入る（色は不参照）。
  ボード画像そのものを2枚目入力に渡す方式は、基本ループが安定してから追加する。

## つまずきやすい点- **入力画像フラグ名**（手順2）。`--help` と食い違うと生成が失敗する → `--image-flag` で合わせる。
- 原図が見つからない → `--genzu-dir` を再帰探索するので、GKVフォルダの親を指定すればOK。
- レジストずれは原理上ほぼ出ない（入力=出力グリッド）。ずれて見えるのは生成の描き直し由来。

---

## 作業コンソール（ブラウザで全カットを回す・MVP）
バッチ(`genzu_fix.batch`)は一括実行だが、カット単位で「原図/結果を見ながらプロンプト編集→
生成/リテイク→OK判定」をしたいときは **コンソール(`genzu_fix.server`)** を使う。

### 起動（原図とHiggsfield CLIがあるマシンで）
```
python -m pip install flask
set PYTHONPATH=src
python -m genzu_fix.server --genzu-dir "C:\Users\kuror\OneDrive\デスクトップ\尚善\尚善_原図修正自動化検証\00.原図" --out "C:\Users\kuror\OneDrive\デスクトップ\尚善\尚善_原図修正自動化検証\10.生成結果" --boards-dir "<美術ボード展開先>" --port 8765
```
→ ブラウザで `http://127.0.0.1:8765` を開く。

### 使い方
- 左: カット一覧（担当/状態でフィルタ。GKVは赤）。クリックで右に詳細。
- 右: 原図プレビュー / 生成結果、プロンプト編集（保存・自動に戻す）、美術ボード選択。
- **生成実行 / リテイク実行**: その場で生成（数分・進捗表示）。リテイクはPSDに `_02` で積む。
- **OK / 要修正**: 状態を記録（`<out>/console_state.json` に永続）。
- **原図を手修正したら**: Photoshopで直して保存 → 「リテイク実行」でPSDを読み直して再生成。
- `--boards-dir` を渡すと美術ボードを2枚目参照画像として生成に使う（無ければプロンプト文ヒントのみ）。

### 補足
- 状態・編集プロンプトは `<out>/console_state.json` に保存。バッチと同じ `cut_board_map_ep7.csv` を読む。
- MVP。今後: レイヤー手動オーバーライド、複数選択の一括/並列実行、検品(qc)フラグ、コスト記録。
