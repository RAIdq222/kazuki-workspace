"""美術ボードフォルダの一覧＋縮小サムネイルを「gitで共有できる形」にする（紐づけ設計用）。

カット→ボードの自動紐づけを設計するには、ボードの命名規則（場所名か・カット範囲か・時間帯か）と
絵の内容を見る必要がある。このスクリプトはボードフォルダを走査して:
  1. ファイル一覧（相対パス・サイズ）を runs/*.txt に書き出し
  2. 各ボードの縮小JPGサムネイルを handoff 配下に書き出し（PSD/TIFFもPNG化して縮小）
push すれば、ボードPSDが無いセッションでも名前と絵を見て紐づけ規則を決められる。

使い方（SP2 #10）:
  python scripts/dump_boards.py --boards-dir "C:\\...\\01.美術ボード" ^
      --out runs/sp2_10_boards.txt --samples-out handoff/SP2_10/boards_sample
  git add runs handoff && git commit -m "data: SP2#10 美術ボード調査" && git push origin main

PYTHONPATH 不要。
"""
from __future__ import annotations
import argparse
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

EXTS = (".png", ".jpg", ".jpeg", ".webp", ".psd", ".psb", ".tif", ".tiff")


def _thumb(src: str, dst_jpg: str, maxside: int) -> bool:
    from PIL import Image
    if src.lower().endswith((".psd", ".psb")):
        from psd_tools import PSDImage
        im = PSDImage.open(src).composite()
    else:
        im = Image.open(src)
    if im.mode != "RGB":
        canvas = Image.new("RGB", im.size, (255, 255, 255))
        rgba = im.convert("RGBA")
        canvas.paste(rgba, mask=rgba.split()[-1])
        im = canvas
    if max(im.size) > maxside:
        s = maxside / max(im.size)
        im = im.resize((round(im.width * s), round(im.height * s)))
    im.save(dst_jpg, quality=80)
    return True


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="dump_boards", description="美術ボードの一覧＋サムネイル書き出し")
    p.add_argument("--boards-dir", required=True)
    p.add_argument("--out", default="runs/boards_dump.txt")
    p.add_argument("--samples-out", default="handoff/boards_sample")
    p.add_argument("--maxside", type=int, default=700)
    p.add_argument("--subdir", default="",
                   help="この名前のフォルダ配下だけ拾う（例: 01_ボード ＝サンプルBG素材を除外）")
    p.add_argument("--no-thumbs", action="store_true", help="一覧だけ書き出す（サムネイル無し）")
    a = p.parse_args(argv)

    bd = os.path.abspath(a.boards_dir)
    files = []
    for root, _, fns in os.walk(bd):
        if a.subdir and a.subdir not in root.replace("\\", "/").split("/"):
            continue
        for fn in sorted(fns):
            if fn.lower().endswith(EXTS):
                path = os.path.join(root, fn)
                files.append((os.path.relpath(path, bd), os.path.getsize(path)))
    if not files:
        print(f"[!] ボード画像が見つかりません: {bd}")
        return 1

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(f"# 美術ボード一覧: {bd}  {len(files)}枚\n\n")
        for rel, size in files:
            f.write(f"{size // 1024:>7}KB  {rel}\n")
    print(f"一覧書き出し: {os.path.abspath(a.out)}  ({len(files)}枚)")

    if a.no_thumbs:
        return 0
    os.makedirs(a.samples_out, exist_ok=True)
    total = 0
    for rel, _ in files:
        stem = os.path.splitext(os.path.basename(rel))[0]
        safe = "".join(c if (c.isalnum() or c in "._-～〜") else "_" for c in stem)
        dst = os.path.join(a.samples_out, safe + ".jpg")
        try:
            _thumb(os.path.join(bd, rel), dst, a.maxside)
            total += os.path.getsize(dst)
        except Exception as e:  # noqa
            print(f"  [warn] {rel}: {str(e)[:100]}")
    print(f"サムネイル書き出し: {os.path.abspath(a.samples_out)}（合計 {total // 1024}KB・git push 可）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
