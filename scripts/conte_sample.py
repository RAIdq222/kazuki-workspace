"""絵コンテPDFのサンプルページを「gitで共有できる縮小JPG」にする（用紙フォーマット調査用）。

新作品のコンテOCRを組む前に、用紙の列構成（絵/アクション/セリフ/尺の境界比率）と
記法を確認する必要がある。このスクリプトは指定ページをPNG化→縮小JPG化して
handoff 配下に置く。push すれば PSD/PDF が無いセッションでも紙面を確認できる。

使い方（SP2 #10 の先頭5ページ）:
  pip install pymupdf                       ← 初回だけ
  python scripts/conte_sample.py --pdf "C:\\...\\03.設定資料\\SP2#10_決定稿コンテ.pdf" ^
      --first 1 --last 5 --out handoff/SP2_10/conte_sample
  git add handoff/SP2_10 && git commit -m "data: SP2#10 コンテ用紙サンプル" && git push

PYTHONPATH 不要。
"""
from __future__ import annotations
import argparse
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from genzu_fix import conte


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="conte_sample", description="コンテPDFのサンプルページを縮小JPG化")
    p.add_argument("--pdf", required=True)
    p.add_argument("--first", type=int, default=1)
    p.add_argument("--last", type=int, default=5)
    p.add_argument("--dpi", type=int, default=150, help="150で文字が読める程度・1枚300KB前後")
    p.add_argument("--maxside", type=int, default=1600)
    p.add_argument("--out", default="handoff/conte_sample")
    a = p.parse_args(argv)

    if not os.path.exists(a.pdf):
        print(f"[!] PDFが見つかりません: {a.pdf}")
        return 1
    paths = conte.render(a.pdf, a.out, dpi=a.dpi, first=a.first, last=a.last)
    from PIL import Image
    total = 0
    for pth in paths:
        im = Image.open(pth)
        if max(im.size) > a.maxside:
            s = a.maxside / max(im.size)
            im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
        jp = pth[:-4] + ".jpg"
        im.convert("RGB").save(jp, quality=85)
        os.remove(pth)
        total += os.path.getsize(jp)
    print(f"縮小JPG {len(paths)}枚 / 合計 {total // 1024}KB -> {os.path.abspath(a.out)}")
    print("次: git add で push（PSD/PDFが無いセッションでも紙面を確認できる）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
