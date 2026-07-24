# ボード照合コンタクトシート生成 (Issue #6 P0-1)
# 原画 / 3Dレンダー / 50%重ね の3枚を縦に並べた比較画像を作る
# 実行: python3 src/stage3d/palace/compare_boards.py 17 work/renders/view17xxx.png
import os
import sys

from PIL import Image, ImageDraw

BOARDS = {
    "17": "work/boards_b08/shz_b08_17皇宮_主殿_昼.png",
    "19": "work/boards_b08/shz_b08_19皇宮_別殿_座敷_昼.png",
}


def make_sheet(board_key, render_path, out_path, width=1600):
    board = Image.open(BOARDS[board_key]).convert("RGB")
    render = Image.open(render_path).convert("RGB")
    h = round(width * board.size[1] / board.size[0])
    board = board.resize((width, h), Image.LANCZOS)
    render = render.resize((width, h), Image.LANCZOS)
    blend = Image.blend(board, render, 0.5)
    sheet = Image.new("RGB", (width, h * 3 + 8 * 4 + 26 * 3), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    y = 8
    for label, img in (("board " + board_key, board), ("3D", render),
                       ("50% blend", blend)):
        d.text((10, y + 4), label, fill=(255, 255, 128))
        sheet.paste(img, (0, y + 26))
        y += h + 26 + 8
    sheet.save(out_path)
    print("wrote", out_path)


if __name__ == "__main__":
    key, render_path = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else f"work/renders/compare_{key}.png"
    make_sheet(key, render_path, out)
