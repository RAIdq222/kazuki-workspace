# -*- coding: utf-8 -*-
"""寝室ボード原画 (尚善美術ボード008) からテクスチャを切り出す。

- floor: 床板 (家具・光だまりのない領域)
- lattice: 朱塗り飾り格子パネル1枚分
- wardrobe: 黒漆の飾り箪笥の扉
- screen: 屏風パネル
- rug: 白い敷物

`python3 src/stage3d/room_textures.py <board008.png> [出力ディレクトリ]`
"""
import os
import sys

from PIL import Image, ImageFilter

# 3600x2448 の原画に対する切り出し座標
CROPS = {
    "floor":    (2740, 1450, 3280, 2350),
    "lattice":  (1440, 86, 1826, 466),
    "wardrobe": (2900, 60, 3420, 660),
    "screen":   (2, 630, 238, 1530),
    "rug":      (1180, 1040, 1530, 1860),
}


def cut(im, name, box, out_dir, blur=0.6):
    c = im.crop(box)
    c = c.filter(ImageFilter.GaussianBlur(blur))
    p = os.path.join(out_dir, f"room_{name}.png")
    c.save(p)
    print(name, c.size, "->", p)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "work/boards/board008.png"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "work/sprites"
    os.makedirs(out_dir, exist_ok=True)
    im = Image.open(src).convert("RGB")
    assert im.size == (3600, 2448), f"想定外のサイズ: {im.size}"
    for name, box in CROPS.items():
        cut(im, name, box, out_dir)


if __name__ == "__main__":
    main()
