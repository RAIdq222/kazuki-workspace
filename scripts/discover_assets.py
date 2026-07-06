"""作業ルートを走査して話数の参照先を自動特定し、project マニフェストを書き出す。

使い方（新話数の入口。ep8 なら）:
  python scripts/discover_assets.py --root "C:\\...\\尚善_原図修正自動化検証" --work 尚善 --ep 08
  → runs/project_尚善_08.json を書き、原図/ボード/出力/脚本/香盤/コンテ/設定資料の場所を表示。
  以後 `python run_console.py --project runs/project_尚善_08.json` で起動できる（脱ハードコード）。

PYTHONPATH 不要（src を自前で通す）。
"""
from __future__ import annotations
import argparse
import json
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from genzu_fix import assets


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="discover_assets",
                                description="話数の参照先(原図/ボード/脚本/香盤/コンテ/設定)を自動特定")
    p.add_argument("--root", required=True, help="作業ルート（例: 尚善_原図修正自動化検証）")
    p.add_argument("--work", default="尚善")
    p.add_argument("--ep", required=True, help="話数（例: 08）")
    p.add_argument("--out", default=None, help="出力json（既定 runs/project_<work>_<ep>.json）")
    p.add_argument("--max-depth", type=int, default=4)
    a = p.parse_args(argv)

    if not os.path.isdir(a.root):
        print(f"[!] ルートが見つかりません: {a.root}")
        return 1
    m = assets.discover(a.root, a.work, a.ep, max_depth=a.max_depth)
    out = a.out or os.path.join("runs", f"project_{a.work}_{a.ep}.json")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

    print(f"== 参照先の自動特定: {a.work} #{a.ep} ==")
    for k in ("genzu_dir", "boards_dir", "out_dir", "script", "koban", "conte"):
        v = m[k]
        print(f"  {'OK ' if v else 'NG '}{k:11}: {v or '(未検出)'}")
    print(f"  設定資料 {len(m['settings'])}件:")
    for s in m["settings"]:
        print(f"      - {s}")
    if m["missing"]:
        print(f"\n未検出: {m['missing']}（フォルダ名/ファイル名が規則と違う可能性。手で json を補える）")
    print(f"\n書き出し: {os.path.abspath(out)}")
    print(f"次: python run_console.py --project {out}")
    return 0 if not m["missing"] else 0  # 未検出でも0（部分成功を許容）


if __name__ == "__main__":
    raise SystemExit(main())
