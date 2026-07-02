"""対象カットの生データを handoff/ep7/ に集める（セッション間の受け渡し用）。

なぜ: リモートの使い捨てコンテナ側セッションには .gitignore 除外の work/ が無く、
原図PNG・コンテ・manifest.json が届かない。分析（原図理解）は受け手セッションが
画像を見てやる仕事なので、こちらは「生データを git に乗せる」ところだけを淡々と行う。

これが集めるもの（カットごと handoff/ep7/cut<NN>/ 配下）:
  - genzu.png          … 背景作画レイヤーだけを合成した原図（自動検出 Base 相当）
  - genzu_visible.png  … 見たまま全レイヤー合成（指示/補助線も含む・任意）
  - manifest.json      … 画素/region/aspect 等（work/ 配下にあればコピー・任意）
  - conte.*            … 絵コンテ（--conte-dir にカット番号を含む画像があればコピー・任意）
集め終えたら handoff/ep7/ を commit / push すれば受け手が git pull で読める。

使い方（作業マシン側＝原図PSDがある環境）:
  set PYTHONPATH=src
  python scripts/gather_handoff_ep7.py ^
    --genzu-dir "C:\\...\\00.原図" ^
    --work "work" ^
    --conte-dir "C:\\...\\コンテ書き出し" ^
    --cuts 15,23,47,53,207,240,257,274,293,294
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import re
import shutil
import sys

# src レイアウトのため、PYTHONPATH 未設定でも import できるよう自前で通す。
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from genzu_fix import psd_export

DEFAULT_CUTS = "15,23,47,53,207,240,257,274,293,294"


def _cut_num(s: str) -> int | None:
    m = re.match(r"\s*(\d+)", s or "")
    return int(m.group(1)) if m else None


def _load_cut_to_psd(csv_path: str) -> dict[int, str]:
    """cut番号 → 代表PSDファイル名。束カットや派生は本体を優先して1つに絞る。"""
    cand: dict[int, list[str]] = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            n = _cut_num(r["cut"])
            fn = (r.get("filename") or "").strip()
            if n is None or not fn:
                continue
            cand.setdefault(n, [])
            if fn not in cand[n]:
                cand[n].append(fn)

    def score(fn: str) -> tuple:
        # 単独カット（_が少ない＝束でない）・BGonlyでない を優先
        bundle = fn.count("_")
        return (bundle, "bgonly" in fn.lower(), len(fn))

    return {n: sorted(v, key=score)[0] for n, v in cand.items()}


def _index_psd(genzu_dir: str) -> dict[str, str]:
    idx: dict[str, str] = {}
    for root, _, files in os.walk(genzu_dir):
        for fn in files:
            if fn.lower().endswith(".psd"):
                idx.setdefault(fn, os.path.join(root, fn))
    return idx


def _find_manifest(work_dir: str, cut_num: int, psd_stem: str) -> str | None:
    if not work_dir or not os.path.isdir(work_dir):
        return None
    pad = f"{cut_num:03d}"
    for root, _, files in os.walk(work_dir):
        if "manifest.json" not in files:
            continue
        key = (root + os.sep).lower()
        if psd_stem.lower() in key or f"_{pad}_" in key or key.rstrip(os.sep).endswith(pad):
            return os.path.join(root, "manifest.json")
    return None


def _find_conte(conte_dir: str, cut_num: int) -> str | None:
    if not conte_dir or not os.path.isdir(conte_dir):
        return None
    pad = f"{cut_num:03d}"
    hits = []
    for root, _, files in os.walk(conte_dir):
        for fn in files:
            if not fn.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                continue
            nums = re.findall(r"\d+", fn)
            if pad in nums or str(cut_num) in nums:
                hits.append(os.path.join(root, fn))
    return sorted(hits, key=len)[0] if hits else None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="gather_handoff_ep7",
                                description="対象カットの生データを handoff/ep7 に集める")
    p.add_argument("--genzu-dir", required=True, help="原図PSDのあるフォルダ（再帰探索）")
    p.add_argument("--csv", default="runs/cut_board_map_ep7.csv", help="cut→filename 対応CSV")
    p.add_argument("--work", default="work", help="manifest.json を探す work/ ルート（任意）")
    p.add_argument("--conte-dir", default=None, help="コンテ画像フォルダ（カット番号を含む画像・任意）")
    p.add_argument("--out", default="handoff/ep7", help="出力先")
    p.add_argument("--cuts", default=DEFAULT_CUTS, help="対象カット番号（カンマ区切り）")
    p.add_argument("--include-book", action="store_true", help="genzu.png にBOOKレイヤーも含める")
    p.add_argument("--no-visible", action="store_true", help="見たまま合成(genzu_visible.png)を作らない")
    a = p.parse_args(argv)

    cuts = [int(x) for x in a.cuts.split(",") if x.strip()]
    cut2psd = _load_cut_to_psd(a.csv)
    psd_idx = _index_psd(a.genzu_dir)
    os.makedirs(a.out, exist_ok=True)

    summary = []
    for n in cuts:
        d = os.path.join(a.out, f"cut{n:03d}")
        os.makedirs(d, exist_ok=True)
        rec = {"cut": n, "psd": None, "genzu": False, "visible": False,
               "manifest": False, "conte": False, "note": ""}
        fn = cut2psd.get(n)
        if not fn:
            rec["note"] = "CSVにカット無し"
            summary.append(rec)
            continue
        rec["psd"] = fn
        psd_path = psd_idx.get(fn)
        if not psd_path:
            rec["note"] = f"PSD未検出: {fn}"
            summary.append(rec)
            continue
        # 1) 背景作画だけの原図PNG（受け手の一次資料の核）
        try:
            w, h, info = psd_export.export_background_layer(
                psd_path, os.path.join(d, "genzu.png"),
                bg=(255, 255, 255), include_book=a.include_book)
            rec["genzu"] = True
            rec["note"] = f"layer[{info['strategy']}]={info['layers']} {w}x{h}"
        except Exception as e:  # noqa
            rec["note"] = f"genzu書き出し失敗: {e}"
        # 2) 見たまま合成（指示/補助線も見たい時用・任意）
        if not a.no_visible:
            try:
                psd_export.export_visible_to_png(
                    psd_path, os.path.join(d, "genzu_visible.png"),
                    bg=(255, 255, 255), drop_text=False)
                rec["visible"] = True
            except Exception:
                pass
        # 3) manifest.json（あれば）
        man = _find_manifest(a.work, n, os.path.splitext(fn)[0])
        if man:
            shutil.copy2(man, os.path.join(d, "manifest.json"))
            rec["manifest"] = True
        # 4) コンテ（あれば）
        con = _find_conte(a.conte_dir, n)
        if con:
            shutil.copy2(con, os.path.join(d, "conte" + os.path.splitext(con)[1].lower()))
            rec["conte"] = True
        summary.append(rec)

    with open(os.path.join(a.out, "index.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"== handoff/ep7 収集結果（{len(cuts)}カット）==")
    for r in summary:
        flags = "".join([
            "G" if r["genzu"] else "-", "V" if r["visible"] else "-",
            "M" if r["manifest"] else "-", "C" if r["conte"] else "-"])
        print(f"  cut{r['cut']:>3} [{flags}] {r['psd'] or ''}  {r['note']}")
    miss = [r["cut"] for r in summary if not r["genzu"]]
    print(f"\n原図PNG欠落: {miss if miss else 'なし'}")
    print(f"出力先: {os.path.abspath(a.out)}")
    print("次: `git add handoff/ep7 && git commit && git push` で受け手に渡る（GVMC = genzu/visible/manifest/conte）")
    return 1 if miss else 0


if __name__ == "__main__":
    raise SystemExit(main())
