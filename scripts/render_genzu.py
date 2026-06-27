"""原図PSDを「読める」PNGに変換する（Read ツールはPNGを視覚的に読めるがPSDは読めない）。

使い方:
  # PSDを直接指定（背景レイヤーのみ＝Base と 見たまま＝visible の両方を書き出し）
  python scripts/render_genzu.py path/to/shz_07_047_genzu.psd

  # カット番号で指定（cut_board_map から本体PSDを引き、--genzu-dir 配下を再帰探索）
  python scripts/render_genzu.py 47 --genzu-dir "C:\\...\\00.原図"

  # レイヤー構成も確認したい（どのレイヤーが原図か当てる手がかり）
  python scripts/render_genzu.py 47 --genzu-dir "..." --layers

出力先（既定 work/_genzu_view/<cut>/）に genzu_base.png / genzu_visible.png を書き、
そのパスを表示する。あとはそのPNGを Read ツールで開けば原図が見える。
PYTHONPATH 不要（src/ を自動で通す）。
"""
from __future__ import annotations
import argparse
import csv
import os
import re
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from genzu_fix import psd_export


def _resolve_psd(target: str, genzu_dir: str | None, csv_path: str) -> str | None:
    """target が既存パスならそのまま。数字ならCSVでファイル名を引き genzu-dir から探す。"""
    if os.path.isfile(target):
        return target
    m = re.match(r"\s*(\d+)\s*$", target)
    if not m or not genzu_dir:
        return None
    n = int(m.group(1))
    cand = []
    if os.path.exists(csv_path):
        for r in csv.DictReader(open(csv_path, encoding="utf-8-sig")):
            cm = re.match(r"\s*(\d+)", r.get("cut", ""))
            fn = (r.get("filename") or "").strip()
            if cm and int(cm.group(1)) == n and fn and fn not in cand:
                cand.append(fn)
    # 本体PSD優先（束/BGonlyを避ける）。CSVに無ければ番号で総当たり。
    cand.sort(key=lambda f: (f.count("_"), "bgonly" in f.lower(), len(f)))
    names = cand or [f"shz_07_{n:03d}_genzu.psd"]
    idx = {}
    for root, _, files in os.walk(genzu_dir):
        for f in files:
            if f.lower().endswith(".psd"):
                idx.setdefault(f, os.path.join(root, f))
    for nm in names:
        if nm in idx:
            return idx[nm]
    # ファイル名一致が無ければ、番号を含むPSDを拾う
    for f, p in idx.items():
        if f"_{n:03d}_" in f or re.search(rf"_{n:03d}\b", f):
            return p
    return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="render_genzu", description="原図PSD→読めるPNG")
    p.add_argument("target", help="PSDのパス、またはカット番号（例 47）")
    p.add_argument("--genzu-dir", default=None, help="カット番号指定時のPSD探索ルート")
    p.add_argument("--csv", default="runs/cut_board_map_ep7.csv")
    p.add_argument("--out", default=None, help="出力先（既定 work/_genzu_view/<cut>）")
    p.add_argument("--source", choices=["base", "visible", "both"], default="both")
    p.add_argument("--include-book", action="store_true")
    p.add_argument("--layers", action="store_true", help="レイヤー一覧も表示")
    a = p.parse_args(argv)

    psd = _resolve_psd(a.target, a.genzu_dir, a.csv)
    if not psd:
        print(f"PSDが見つかりません: {a.target}"
              + ("" if a.genzu_dir else "（カット番号指定なら --genzu-dir が必要）"))
        return 1
    cut = os.path.splitext(os.path.basename(psd))[0]
    out = a.out or os.path.join("work", "_genzu_view", cut)
    os.makedirs(out, exist_ok=True)
    print(f"PSD: {psd}")

    made = []
    if a.source in ("base", "both"):
        bp = os.path.join(out, "genzu_base.png")
        w, h, info = psd_export.export_background_layer(psd, bp, include_book=a.include_book)
        print(f"  Base(背景のみ): {bp}  {w}x{h}  layer[{info['strategy']}]={info['layers']}")
        made.append(bp)
    if a.source in ("visible", "both"):
        vp = os.path.join(out, "genzu_visible.png")
        vw, vh = psd_export.export_visible_to_png(psd, vp, drop_text=False)
        print(f"  visible(見たまま): {vp}  {vw}x{vh}")
        made.append(vp)

    if a.layers:
        print("  --- レイヤー一覧（上から）---")
        for li in psd_export.list_layers(psd):
            print(f"    {'  '*li.depth}{'👁' if li.visible else '・'} {li.name} [{li.kind}] {li.bbox}")

    print("\n次: 上記PNGを Read ツールで開けば原図が見える。")
    print("Base=背景作画のみ / visible=指示・補助線・タップ穴も含む見たまま。")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
