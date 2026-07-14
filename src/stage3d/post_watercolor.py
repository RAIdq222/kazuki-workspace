# -*- coding: utf-8 -*-
"""レンダリング画像に水彩画っぽい淡さを足すポスト処理。

- ソフトブルーム (ハイライトのにじみ)
- シャドウを紙色へリフト (真っ黒を作らない)
- 彩度をわずかに抑えて紙目ノイズを重ねる
- 周辺をほんのり明るく (紙の余白感)

使い方: python3 src/stage3d/post_watercolor.py in.png [out.png]
"""

import sys

from PIL import Image, ImageChops, ImageEnhance, ImageFilter

PAPER = (232, 230, 220)


def watercolor(im, bloom=0.20, lift=0.14, desat=0.94, grain=0.045):
    im = im.convert("RGB")
    w, h = im.size

    # 1) ソフトブルーム: ぼかしをスクリーン合成
    blur = im.filter(ImageFilter.GaussianBlur(max(2, w // 180)))
    im = ImageChops.blend(im, ImageChops.screen(im, blur), bloom)

    # 2) シャドウリフト: 暗部ほど紙色へ寄せる
    paper = Image.new("RGB", im.size, PAPER)
    inv = im.convert("L").point(lambda v: int((255 - v) * lift))  # 暗いほど大きい
    im = Image.composite(paper, im, inv)

    # 3) 彩度控えめ
    im = ImageEnhance.Color(im).enhance(desat)

    # 4) 紙目: 255付近を中心にしたノイズを乗算 (わずかに凹むだけ)
    noise = Image.effect_noise((w // 2, h // 2), 26).resize((w, h))
    noise = noise.point(lambda v: int(255 - abs(v - 128) * grain * 5))
    im = ImageChops.multiply(im, Image.merge("RGB", (noise, noise, noise)))

    return im


def main():
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src.replace(".png", "_wc.png")
    watercolor(Image.open(src)).save(dst, quality=92)
    print("wrote", dst)


if __name__ == "__main__":
    main()
