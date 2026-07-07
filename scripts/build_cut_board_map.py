"""香盤表(xlsx) → cut_board_map CSV を自動生成（新話数の量産入口）。

やること:
  1. 香盤表をパース（koban.py）: カット・場所・シーン色(→時間)・BANK を取り出す
  2. 原図フォルダを走査: PSDのカット番号(束/枝番対応=naming.parse_cut_codes)と突合
     → filename と 担当(assignee=PSDの親フォルダ名) を埋める
     → PSDが無いカットは「原図待ち」= 予測ファイル名で行だけ作る（後日 rescan で実物に繋がる）
  3. --boards-dir 指定時: naming.match_board（場所+時間）で美術ボードを提案
     → 確度が高いものだけ board 列に記入（誤マッチは害なので閾値未満は空欄＝コンソールで選ぶ）
  4. BANK レンジは出力しない（原図作業なし・件数は報告）

使い方（ep8）:
  python scripts/build_cut_board_map.py --project runs/project_尚善_08.json --last-cut 300
  # または個別指定:
  python scripts/build_cut_board_map.py --koban "…香盤表#08.xlsx" --genzu-dir "…\\00.原図" \
      --boards-dir "…\\01.美術ボード" --work 尚善 --ep 08 --last-cut 300

PYTHONPATH 不要。openpyxl 不要（xlsxは標準ライブラリで読む）。
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from genzu_fix import koban, naming
from genzu_fix.assets import WORK_ALIASES

_IMG_BOARD_EXT = (".png", ".jpg", ".jpeg")


def _index_genzu(genzu_dir: str):
    """PSD走査 → {カット表記(非ゼロ詰め+枝番): (filename, assignee)}。"""
    idx = {}
    if not (genzu_dir and os.path.isdir(genzu_dir)):
        return idx
    root = os.path.abspath(genzu_dir)
    for cur, _, files in os.walk(root):
        for fn in files:
            if not fn.lower().endswith(".psd"):
                continue
            info = naming.parse_cut_codes(fn)
            rel = os.path.relpath(cur, root)
            parts = [p for p in rel.split(os.sep) if p and p != "."]
            # 担当=シーン名らしくない親フォルダ（server._units_from_folder と同じ発想）
            import re as _re
            assignee = next((p for p in reversed(parts) if not _re.search(r"c\d", p)), "(直下)")
            for c in info.get("cuts") or []:
                m = _re.match(r"(\d+)([A-Za-z]?)", c)
                if not m:
                    continue
                key = f"{int(m.group(1))}{m.group(2).upper()}"
                idx.setdefault(key, (fn, assignee))
    return idx


def _work_prefix(work: str, genzu_idx: dict) -> str:
    """filename 予測用の作品プレフィックス。実PSDがあればそこから、無ければ別名表から。"""
    for fn, _ in genzu_idx.values():
        info = naming.parse_cut_codes(fn)
        if info.get("work"):
            return info["work"]
    for alias in WORK_ALIASES.get(work, []):
        if alias.isascii():
            return alias
    return "shz"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="build_cut_board_map",
                                description="香盤表xlsx → cut_board_map CSV")
    p.add_argument("--project", default=None, help="discover_assets の project json（koban等を補完）")
    p.add_argument("--koban", default=None, help="香盤表xlsx")
    p.add_argument("--genzu-dir", default=None)
    p.add_argument("--boards-dir", default=None)
    p.add_argument("--work", default="尚善")
    p.add_argument("--ep", default=None)
    p.add_argument("--last-cut", type=int, default=None, help="『293～』等の終端開きを閉じる最終カット番号")
    p.add_argument("--board-score", type=int, default=3,
                   help="ボード自動記入の最低スコア（既定3=場所+時間。誤マッチ防止）")
    p.add_argument("--out", default=None, help="出力CSV（既定 runs/cut_board_map_ep<EP>.csv）")
    a = p.parse_args(argv)

    if a.project:
        pj = json.load(open(a.project, encoding="utf-8"))
        a.koban = a.koban or pj.get("koban")
        a.genzu_dir = a.genzu_dir or pj.get("genzu_dir")
        a.boards_dir = a.boards_dir or pj.get("boards_dir")
        a.work = pj.get("work", a.work)
        a.ep = a.ep or pj.get("ep")
    if not a.koban or not os.path.exists(a.koban):
        p.error(f"香盤表が見つかりません: {a.koban}（--koban か --project で指定）")
    ep = str(a.ep or "").strip() or "00"
    ep2 = f"{int(ep):02d}" if ep.isdigit() else ep
    out = a.out or os.path.join("runs", f"cut_board_map_ep{int(ep) if ep.isdigit() else ep}.csv")

    cuts, warns = koban.parse_koban_xlsx(a.koban, last_cut=a.last_cut)
    genzu_idx = _index_genzu(a.genzu_dir)
    prefix = _work_prefix(a.work, genzu_idx)

    board_index = []
    if a.boards_dir and os.path.isdir(a.boards_dir):
        names = sorted({f for _, _, fs in os.walk(a.boards_dir) for f in fs
                        if f.lower().endswith(_IMG_BOARD_EXT)})
        board_index = naming.build_board_index(names)

    rows, banks, missing, boarded = [], 0, 0, 0
    for c in cuts:
        if c["bank"]:
            banks += 1
            continue
        hit = genzu_idx.get(c["cut"])
        if hit:
            filename, assignee = hit
        else:
            missing += 1
            filename = f"{prefix}_{ep2}_{c['num']:03d}{c['sfx']}_genzu.psd"
            assignee = "(原図待ち)"
        board = ""
        if board_index and c["place"]:
            cand = naming.match_board({"place": c["place"], "time": c["time"]}, board_index, top=1)
            if cand and cand[0]["score"] >= a.board_score:
                board = cand[0]["raw"]
                boarded += 1
        scene = f"{c['place']}c{c['range_label']}" if c["place"] else f"c{c['range_label']}"
        rows.append({"cut": c["cut"], "assignee": assignee, "scene": scene,
                     "filename": filename, "board": board})

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["cut", "assignee", "scene", "filename", "board"])
        w.writeheader()
        w.writerows(rows)

    print(f"== cut_board_map 生成: {a.work} #{ep} ==")
    print(f"  カット {len(rows)}行（BANKスキップ {banks}） / PSD一致 {len(rows)-missing} / 原図待ち {missing}")
    print(f"  ボード自動記入 {boarded}（score>={a.board_score}。残りはコンソールのプルダウンで選択）")
    for w_ in warns:
        print(f"  [注意] {w_}")
    print(f"  出力: {os.path.abspath(out)}")
    print(f"次: python run_console.py --project <project.json> --csv {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
