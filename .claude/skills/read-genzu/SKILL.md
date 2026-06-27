---
name: read-genzu
description: 原図(genzu)PSDの中身を実際に「見る／読む」方法。PSDはバイナリなのでReadツールでは中身が見えない、work/ はgitignoreでリモートのコンテナに来ない——という「原図が読めない」状況を解決する。原図を確認したい・situation/removeを埋めたい・レイヤー選択を確認したいときに使う。
---

# 原図(genzu)を読む

「原図が読めない」原因は2つ。両方ここで解決する。

1. **PSDはバイナリ**。Read ツールはPNG/JPGは視覚的に読めるが、`.psd` の中身は見えない。
   → **PSDをPNGに書き出してから Read する**。
2. **`work/` は .gitignore 除外**。リモートの使い捨てコンテナには原図PSDも書き出しPNGも無い。
   → **git に乗った `handoff/ep7/` のPNGを使う**（無ければ作って push してもらう）。

---

## ケースA: 原図PSDがローカルにある（work/ がある／Driveから落とした）

`scripts/render_genzu.py` でPNG化して、そのPNGを Read で開く。PYTHONPATH 不要。

```bash
# カット番号で（cut_board_map から本体PSDを引き、--genzu-dir 配下を探索）
python scripts/render_genzu.py 47 --genzu-dir "<原図フォルダ>"

# PSDを直接指定
python scripts/render_genzu.py path/to/shz_07_047_genzu.psd

# レイヤー選択を疑うとき（どのレイヤーが原図か一覧で確認）
python scripts/render_genzu.py 47 --genzu-dir "<原図フォルダ>" --layers
```

出力（既定 `work/_genzu_view/<cut>/`）:
- `genzu_base.png` … 背景作画レイヤーのみ合成（= 自動検出Base。指示/補助線/タップ穴を除外）
- `genzu_visible.png` … 見たまま全レイヤー合成（指示・補助線・タップ穴も**見える**）

→ この2枚を **Read ツールで開けば原図が見える**。
状況/除去対象(situation/remove)を判断するなら、まず `genzu_visible.png` で全体を把握し、
`genzu_base.png` で「背景作画として残る線」を確認するとよい。

> レイヤー誤検出（指示レイヤーが原図扱い等）を疑ったら `--layers` で一覧を見る。
> 内部は `genzu_fix.psd_export.export_background_layer`（BG→LO→背景の順で選択）/
> `export_visible_to_png` / `list_layers`。直接呼んでもよい:
> `python -c "from genzu_fix import psd_export; psd_export.export_background_layer('x.psd','o.png')"`

## ケースB: リモートのコンテナで、手元にPSDが無い

原図は `work/`（gitignore）にしか無いので、**git 経由で受け取る**。

1. `git pull` して `handoff/ep7/cut<NN>/` を見る。
   - `genzu.png`（背景のみ）/ `genzu_visible.png`（見たまま）/ `manifest.json` / `conte.*` が入っている。
   - あれば **その genzu.png / conte を Read で開く**。これで原図もコンテも読める。
2. `handoff/ep7/` が空（まだ作られていない）なら、データ保有者（作業マシン側）に次を依頼:
   ```bash
   python scripts/gather_handoff_ep7.py --genzu-dir "<原図フォルダ>" --conte-dir "<コンテ>"
   git add handoff/ep7 && git commit -m "data: 原図/コンテ受け渡し" && git push
   ```
   詳細は `runs/handoff_DATA_README.md`。pull すれば読めるようになる。

---

## まとめ（最短手順）
- ローカルにPSDあり → `python scripts/render_genzu.py <cut> --genzu-dir <dir>` → 出たPNGを Read。
- リモートでPSD無し → `git pull` → `handoff/ep7/cut<NN>/genzu*.png` を Read（無ければ gather を依頼）。
- 「PSDをそのまま Read」だけは無駄打ち（中身が見えない）。必ずPNG化を挟む。
