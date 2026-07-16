"""コンテOCR結果CSV → cut_scene_info CSV（プロンプトCUT層の材料）変換。

conte consolidate の出力（cut,page,action,dialogue,se,time,characters,confidence,notes）を、
prompt.load_cut_info が読む cut_scene_info スキーマ
（cut,scene_key,place,time,weather,situation,situation_en,remove,remove_en,structures,era,source）
へ落とす。場所・時刻はカット範囲表（scene_ranges CSV: start,end,scene_key,place,time,weather）から引く。

- situation = コンテの action 列（改行は「／」に潰す）。OCR信頼度が --min-conf 未満の行は
  誤読テキストをプロンプトに流し込まないよう situation を空にする（place/time だけ効かせる）。
- era は必ず --era を書き込む（空だと尚善の既定「中国 南北朝」が誤適用されるため）。
- 出力はそのまま project json の "cut_info" に指せばコンソール/batch のプロンプトに効く。

使い方（SP2 #10）:
  python scripts/build_cut_info_from_conte.py --conte runs/conte_v2_sp2_10.csv ^
      --ranges runs/scene_ranges_sp2_10.csv --out runs/cut_scene_info_sp2_10.csv ^
      --era "現代日本（modern-day Japan）"

PYTHONPATH 不要。
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

from genzu_fix.prompt import CUT_INFO_FIELDS  # スキーマは prompt 側を正とする

_CONF_ORDER = {"low": 0, "medium": 1, "high": 2}

# situation に採用しないト書き＝キャラの芝居（人名・集団語を含む行）。
# 背景線画のタスクには「誰が何をしているか」はノイズで、しかも
# 「シーン設定に合わせて補完してよい」という誤読の燃料になる。
_CHARACTER_WORDS = (
    "佐々木", "二人静", "阿久津", "星崎", "お隣さん", "アバドン", "エリエル",
    "ピーちゃん", "加藤", "加瀬", "マスター", "彼氏", "母", "女将", "野次馬",
    "一同", "2人", "3人", "二人", "みんな", "こちらを見",
)


def _load_ranges(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["start"], r["end"] = int(r["start"]), int(r["end"])
    return rows


def _find_range(ranges: list[dict], n: int) -> dict | None:
    return next((r for r in ranges if r["start"] <= n <= r["end"]), None)


def _clean(text: str) -> str:
    return "／".join(s.strip() for s in (text or "").splitlines() if s.strip())


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="build_cut_info_from_conte",
                                description="コンテOCR CSV→cut_scene_info CSV")
    p.add_argument("--conte", required=True, help="conte consolidate の出力CSV")
    p.add_argument("--ranges", required=True, help="カット範囲→場所/時刻の表CSV")
    p.add_argument("--out", required=True)
    p.add_argument("--era", default="現代日本（modern-day Japan）",
                   help="時代設定。空にしない（既定eraの誤適用防止）")
    p.add_argument("--min-conf", default="medium", choices=["low", "medium", "high"],
                   help="この信頼度未満の action は situation に採用しない（誤読の混入防止）")
    p.add_argument("--board-map-out", default="",
                   help="範囲表に board 列があれば、cut,board のCSVも書き出す"
                        "（project json の board_map に指す＝コンソールのボード自動紐づけ）")
    a = p.parse_args(argv)

    ranges = _load_ranges(a.ranges)
    seen: dict[str, dict] = {}
    dropped_conf = 0
    with open(a.conte, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            cut = (row.get("cut") or "").strip()
            m = re.match(r"0*(\d+)", cut)
            if not m:
                continue
            if cut in seen:  # 同カットの継続コマは先勝ち
                continue
            rng = _find_range(ranges, int(m.group(1)))
            conf_ok = _CONF_ORDER.get((row.get("confidence") or "").strip(), 0) >= _CONF_ORDER[a.min_conf]
            situation = _clean(row.get("action") or "") if conf_ok else ""
            if not conf_ok:
                dropped_conf += 1
            if situation and any(wd in situation for wd in _CHARACTER_WORDS):
                situation = ""  # キャラ芝居のト書きはプロンプトに流さない（環境描写のみ通す）
            seen[cut] = {
                "cut": cut,
                "scene_key": (rng or {}).get("scene_key", ""),
                "place": (rng or {}).get("place", ""),
                "time": (rng or {}).get("time", ""),
                "weather": (rng or {}).get("weather", ""),
                "situation": situation,
                "situation_en": "",
                "remove": "",
                "remove_en": "",
                "structures": "",
                "era": a.era,
                "source": f"conte:{row.get('page','')};conf:{row.get('confidence','')}",
            }

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CUT_INFO_FIELDS)
        w.writeheader()
        for cut in sorted(seen, key=lambda c: (int(re.match(r"0*(\d+)", c).group(1)), c)):
            w.writerow(seen[cut])
    n_place = sum(1 for v in seen.values() if v["place"])
    n_sit = sum(1 for v in seen.values() if v["situation"])
    print(f"書き出し: {a.out}  {len(seen)}カット（place={n_place} / situation={n_sit} / "
          f"低信頼でsituation落とし={dropped_conf}）")

    if a.board_map_out:
        n_board = 0
        with open(a.board_map_out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["cut", "board"])
            for cut in sorted(seen, key=lambda c: (int(re.match(r"0*(\d+)", c).group(1)), c)):
                n = int(re.match(r"0*(\d+)", cut).group(1))
                board = (_find_range(ranges, n) or {}).get("board", "")
                if board:
                    w.writerow([cut, board])
                    n_board += 1
        print(f"書き出し: {a.board_map_out}  board紐づけ {n_board}カット")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
