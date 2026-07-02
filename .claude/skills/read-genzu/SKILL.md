---
name: read-genzu
description: 原図修正コンソールがPSDから原図を出すのと「全く同じやり方」で、別セッションでも原図を取り出す方法。PSDはバイナリでReadできないので、コンソールと同じ psd_export 関数でPNG化してから読む。原図を確認したい・situation/removeを埋めたい・レイヤー選択を確認したいときに使う。
---

# 原図(genzu)を読む — コンソールと同じやり方で

原図修正コンソールが「PSDを読み込んで原図を表示」しているとき、内部でやっているのは
**`genzu_fix.psd_export` の関数でPSDを合成→PNG化**するだけ。別セッションでも**同じ関数を呼べば
コンソールと1:1で同じ原図が出る**。PNGをgitに上げて配る必要はない。

- コンソール: `server._genzu_preview` →
  `psd_export.export_background_layer(...)`（既定=Base）/ `export_visible_to_png(..., drop_text=False)`（visible）
- 別セッション: `scripts/render_genzu.py` が**同じ2関数を同じ引数で**呼ぶ。出力は同一。

PSDをそのまま Read しても中身は見えない（バイナリ）。必ずこのPNG化を挟む。

## 唯一の前提
そのセッションが**PSDにアクセスできること**（コンソールに渡すのと同じ `--genzu-dir`、例: `00.原図`）。
PSDが手元に無いリモートは、そもそもコンソールでも原図を出せない＝同じ条件。ローカル等PSDがある場所で動かす。

## やり方（コンソールと同手順）
```bash
# カット番号で（cut_board_map から本体PSDを引き、--genzu-dir 配下を再帰探索）
python scripts/render_genzu.py 47 --genzu-dir "<原図フォルダ 例: ..\\00.原図>"

# PSDを直接指定でもよい
python scripts/render_genzu.py path/to/shz_07_047_genzu.psd
```
出力（既定 `work/_genzu_view/<cut>/`）:
- `genzu_base.png` … `export_background_layer`（背景作画のみ）＝**コンソール既定の「原図」と同一**
- `genzu_visible.png` … `export_visible_to_png`（見たまま全レイヤー＝指示/補助線/タップ穴も見える）

→ この**PNGを Read ツールで開けば、コンソールに出るのと同じ原図が見える**。
situation/remove を判断するなら、`genzu_visible.png` で全体把握 → `genzu_base.png` で背景作画として残る線を確認。

## レイヤー選択を疑うとき
`export_background_layer` は BG→LO→背景 の順でレイヤーを選ぶ。誤検出（指示レイヤーが拾われた等）を疑ったら一覧を見る:
```bash
python scripts/render_genzu.py 47 --genzu-dir "<原図フォルダ>" --layers
```
コンソールの「原図取り直し（visible/Base切替）」と同じ判断材料。直接 `psd_export.list_layers(psd)` でもよい。

## コードで直接呼ぶ場合（コンソールと同じ）
```python
from genzu_fix import psd_export
psd_export.export_background_layer("shz_07_047_genzu.psd", "genzu_base.png")   # = コンソールの原図
psd_export.export_visible_to_png("shz_07_047_genzu.psd", "genzu_visible.png", drop_text=False)
```

---
補足: `handoff/ep7/` へPNGを書き出して git で配る方式（`scripts/gather_handoff_ep7.py`）も別に在るが、
PSDにアクセスできるなら不要。本スキルの「その場でPSD→PNG」がコンソールと完全に同じ取り回し。
