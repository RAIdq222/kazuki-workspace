"""既存の生成出力の位置ずれを計測する（生成不要・ローカルで完結・API不要）。

「重ねたら位置がだいぶずれる」を数値にする: 原図(visible.png)と結果(restored_full.png)の
相似変換（拡大率＋平行移動）を推定し、ずれていれば逆変換で原図グリッドへ戻した
restored_aligned.png と重ね図 align_overlay_{before,after}.jpg を出す。
重ね図の見方: 原図の線=シアン / 生成の線=赤 / 一致した線=黒。

使い方（PYTHONPATH 不要）:
  python scripts\check_align.py work\gkv\SP2_10_283            ← 生成出力フォルダを渡す
  python scripts\check_align.py --genzu 原図.png --result 結果.png --out work\_align
"""
from __future__ import annotations

import argparse
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from genzu_fix import align  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="check_align", description="生成結果の位置ずれ計測")
    p.add_argument("out_dir", nargs="?", help="visible.png / restored_full.png がある生成出力フォルダ")
    p.add_argument("--genzu", help="原図PNG（out_dir を使わない場合）")
    p.add_argument("--result", help="結果PNG（out_dir を使わない場合）")
    p.add_argument("--out", help="計測結果の書き出し先（既定: 画像と同じ場所）")
    a = p.parse_args(argv)

    if a.out_dir:
        genzu = os.path.join(a.out_dir, "visible.png")
        result = os.path.join(a.out_dir, "restored_full.png")
        out = a.out or a.out_dir
    elif a.genzu and a.result:
        genzu, result, out = a.genzu, a.result, (a.out or os.path.dirname(a.result) or ".")
    else:
        p.error("out_dir か --genzu/--result を指定")
    for f in (genzu, result):
        if not os.path.exists(f):
            raise SystemExit(f"見つからない: {f}")

    r = align.measure(genzu, result, out)
    print(f"scale ×{r['scale']:.3f}   shift ({r['dx_pct']:+.1f}%, {r['dy_pct']:+.1f}%)   "
          f"score {r['score']:.3f}   → {r['verdict']}")
    if r["verdict"] == "mismatch":
        print(f"ずれあり。逆変換版と重ね図を書き出した:\n"
              f"  {os.path.join(out, 'restored_aligned.png')}\n"
              f"  {os.path.join(out, 'align_overlay_before.jpg')}（補正前: 赤とシアンが離れているはず）\n"
              f"  {os.path.join(out, 'align_overlay_after.jpg')}（補正後: 黒く重なれば相似ズレが主因）")
    elif r["verdict"] == "low_confidence":
        print("線の噛み合いが弱く推定を信用できない（構図自体が別物の可能性）。目視確認を推奨。")
    else:
        print("位置整合OK（±2%/1.5%以内）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
