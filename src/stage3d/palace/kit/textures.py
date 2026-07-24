# 皇宮キット用 PIL手続きテクスチャ (work/sprites/ に生成)
# 様式: 南朝風 = 灰黒瓦 / 朱柱・赤壁 / 金彫刻帯 / 白石基壇 (docs/palace-sources.md §4/§7)
import os
import random

from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.join(os.getcwd(), "work", "sprites")
os.makedirs(OUT, exist_ok=True)


def _save(img, name):
    p = os.path.join(OUT, name)
    img.save(p)
    return p


def _noise(draw, w, h, base, amp, n, seed):
    rng = random.Random(seed)
    for _ in range(n):
        x, y = rng.randrange(w), rng.randrange(h)
        v = rng.randint(-amp, amp)
        c = tuple(max(0, min(255, b + v)) for b in base)
        draw.rectangle([x, y, x + rng.randint(1, 3), y + rng.randint(1, 3)], fill=c)


def tiles(name="kw_tile_grey.png", base=(72, 78, 82), rib=(46, 50, 54),
          hi=(96, 102, 106)):
    """筒瓦: 1タイル=筒瓦1列(縦リブ)+平瓦。u=0.35m 相当でタイル."""
    w = h = 256
    img = Image.new("RGB", (w, h), base)
    d = ImageDraw.Draw(img)
    # 平瓦のうねり (横方向の淡い段)
    for y in range(0, h, 32):
        d.rectangle([0, y, w, y + 2], fill=tuple(int(b * 0.92) for b in base))
    # 筒瓦 (右端に縦リブ)
    d.rectangle([w - 46, 0, w - 1, h], fill=rib)
    d.rectangle([w - 46, 0, w - 40, h], fill=tuple(min(255, r + 24) for r in rib))
    d.rectangle([w - 8, 0, w - 1, h], fill=tuple(max(0, r - 14) for r in rib))
    d.line([(w - 23, 0), (w - 23, h)], fill=hi, width=3)
    _noise(d, w, h, base, 7, 900, 11)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    return _save(img, name)


def tiles_amber():
    return tiles("kw_tile_amber.png", base=(196, 130, 52), rib=(150, 92, 30),
                 hi=(224, 162, 84))


def red_wall():
    """赤壁 (経年の朱漆喰)."""
    w = h = 512
    base = (118, 42, 30)
    img = Image.new("RGB", (w, h), base)
    d = ImageDraw.Draw(img)
    _noise(d, w, h, base, 12, 4000, 21)
    for i in range(14):  # 雨だれ・退色の縦ムラ
        rng = random.Random(100 + i)
        x = rng.randrange(w)
        col = (int(base[0] * 0.9), int(base[1] * 0.9), int(base[2] * 0.9))
        d.rectangle([x, rng.randrange(h // 2), x + rng.randint(4, 14), h], fill=col)
    img = img.filter(ImageFilter.GaussianBlur(2.2))
    return _save(img, "kw_redwall.png")


def frieze():
    """額枋の金彫刻帯 (赤地+金の雲文、横リピート32モチーフ)."""
    w, h = 2048, 128
    img = Image.new("RGB", (w, h), (96, 32, 24))
    d = ImageDraw.Draw(img)
    gold = (198, 158, 74)
    dark = (140, 100, 42)
    d.rectangle([0, 0, w, 8], fill=gold)
    d.rectangle([0, h - 8, w, h], fill=gold)
    step = 64
    for i in range(w // step):
        x = i * step
        # 雲文風の渦: 円弧2つ+点
        d.arc([x + 8, 28, x + 46, 66], 200, 500, fill=gold, width=5)
        d.arc([x + 22, 44, x + 52, 92], 20, 300, fill=dark, width=4)
        d.ellipse([x + 40, 30, x + 50, 40], outline=gold, width=3)
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    return _save(img, "kw_frieze.png")


def dougong_band():
    """斗栱帯の略記 (檐下の影+斗栱シルエットの繰り返し)."""
    w, h = 1024, 128
    img = Image.new("RGB", (w, h), (52, 26, 22))
    d = ImageDraw.Draw(img)
    arm = (120, 66, 36)
    for i in range(w // 64):
        x = i * 64 + 8
        d.rectangle([x, 70, x + 48, 84], fill=arm)
        d.rectangle([x + 8, 46, x + 40, 60], fill=arm)
        d.rectangle([x + 18, 22, x + 30, 40], fill=(150, 88, 46))
    img = img.filter(ImageFilter.GaussianBlur(1.0))
    return _save(img, "kw_dougong.png")


def lattice_door():
    """格子扉 (回紋窓系の方形グリッド+金枠、youkai_10参照)."""
    w, h = 256, 512
    img = Image.new("RGB", (w, h), (60, 30, 22))
    d = ImageDraw.Draw(img)
    gold = (172, 132, 62)
    # 上2/3 = 格子、下1/3 = 板パネル
    gy = int(h * 0.62)
    d.rectangle([6, 6, w - 6, gy], outline=gold, width=5)
    for x in range(6, w - 6, 24):
        d.line([(x, 6), (x, gy)], fill=gold, width=3)
    for y in range(6, gy, 24):
        d.line([(6, y), (w - 6, y)], fill=gold, width=3)
    d.rectangle([6, gy + 8, w - 6, h - 6], outline=gold, width=4)
    d.rectangle([26, gy + 26, w - 26, h - 26], outline=(120, 84, 40), width=3)
    return _save(img, "kw_lattice.png")


def lattice_door_dark():
    """格子扉の暗色版 (軒下の陰の中の建具。b08_17の1層)."""
    w, h = 256, 512
    img = Image.new("RGB", (w, h), (28, 16, 12))
    d = ImageDraw.Draw(img)
    gold = (96, 74, 38)
    gy = int(h * 0.62)
    d.rectangle([6, 6, w - 6, gy], outline=gold, width=5)
    for x in range(6, w - 6, 24):
        d.line([(x, 6), (x, gy)], fill=gold, width=2)
    for y in range(6, gy, 24):
        d.line([(6, y), (w - 6, y)], fill=gold, width=2)
    d.rectangle([6, gy + 8, w - 6, h - 6], outline=gold, width=4)
    d.rectangle([26, gy + 26, w - 26, h - 26], outline=(70, 52, 28), width=3)
    return _save(img, "kw_lattice_dk.png")


def stone_paving():
    """広場の大判石畳."""
    w = h = 512
    base = (168, 165, 156)
    img = Image.new("RGB", (w, h), base)
    d = ImageDraw.Draw(img)
    _noise(d, w, h, base, 9, 2500, 31)
    for y in range(0, h, 128):
        d.line([(0, y), (w, y)], fill=(120, 118, 110), width=4)
    for i, x in enumerate(range(0, w, 128)):
        off = 64 if (i % 2) else 0
        for y in range(off, h + 1, 128):
            d.line([(x, y - 64), (x, y + 64)], fill=(126, 124, 116), width=3)
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    return _save(img, "kw_paving.png")


def cloud_ramp():
    """御路 (階段中央の雲龍紋の斜路)。二重縁+中央の蛇行帯+絡み雲."""
    w, h = 512, 2048
    base = (154, 152, 144)
    img = Image.new("RGB", (w, h), base)
    d = ImageDraw.Draw(img)
    dk = (112, 110, 102)
    md = (128, 126, 118)
    lt = (168, 166, 158)
    d.rectangle([6, 6, w - 6, h - 6], outline=dk, width=10)
    d.rectangle([26, 26, w - 26, h - 26], outline=md, width=5)
    # 中央の蛇行帯 (龍体の略記)
    import math as _m
    pts = [(w / 2 + _m.sin(t / 90) * w * 0.16, 60 + t) for t in range(0, h - 120, 8)]
    for i in range(len(pts) - 1):
        d.line([pts[i], pts[i + 1]], fill=md, width=26)
    for i in range(len(pts) - 1):
        d.line([pts[i], pts[i + 1]], fill=lt, width=10)
    # 絡み雲 (二重渦を規則的に)
    rng = random.Random(7)
    for iy in range(10):
        for ix in range(3):
            cx = 60 + ix * 140 + rng.randint(-18, 18)
            cy = 100 + iy * 190 + rng.randint(-24, 24)
            r = rng.randint(30, 44)
            d.arc([cx - r, cy - r * 0.7, cx + r, cy + r * 0.7], 160, 520, fill=dk, width=7)
            d.arc([cx - r * 0.55, cy - r * 0.4, cx + r * 0.55, cy + r * 0.4],
                  0, 320, fill=lt, width=5)
            d.ellipse([cx + r * 0.3, cy - 6, cx + r * 0.3 + 12, cy + 6], fill=md)
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    return _save(img, "kw_ongro.png")


def frieze_olive():
    """別殿系のオリーブ金彫刻帯 (b08_19)."""
    return _frieze_base("kw_frieze_o.png", bg=(74, 66, 34), fg=(178, 148, 66),
                        fg2=(120, 104, 48))


def _frieze_base(name, bg, fg, fg2):
    w, h = 2048, 128
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 8], fill=fg)
    d.rectangle([0, h - 8, w, h], fill=fg)
    step = 64
    for i in range(w // step):
        x = i * step
        d.arc([x + 8, 28, x + 46, 66], 200, 500, fill=fg, width=5)
        d.arc([x + 22, 44, x + 52, 92], 20, 300, fill=fg2, width=4)
        d.ellipse([x + 40, 30, x + 50, 40], outline=fg, width=3)
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    return _save(img, name)


def sudare():
    """簾 (巻き下ろし状態)。横編みの竹ひご+吊り紐2本."""
    w, h = 256, 512
    img = Image.new("RGB", (w, h), (188, 162, 108))
    d = ImageDraw.Draw(img)
    rng = random.Random(5)
    for y in range(0, h, 7):
        tone = rng.randint(-14, 10)
        c = (188 + tone, 162 + tone, 108 + tone)
        d.rectangle([0, y, w, y + 4], fill=c)
        d.line([(0, y + 5), (w, y + 5)], fill=(130, 106, 62), width=2)
    for x in (w // 4, w * 3 // 4):
        d.rectangle([x - 3, 0, x + 3, h], fill=(96, 70, 40))
    d.rectangle([0, 0, w, 10], fill=(96, 70, 40))
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    return _save(img, "kw_sudare.png")


def rough_stone():
    """野面積み (不整形の石積み、b08_19の基壇)."""
    w, h = 512, 256
    img = Image.new("RGB", (w, h), (104, 100, 92))
    d = ImageDraw.Draw(img)
    rng = random.Random(9)
    for _ in range(90):
        cx, cy = rng.randrange(w), rng.randrange(h)
        rx, ry = rng.randint(28, 64), rng.randint(18, 40)
        tone = rng.randint(-16, 22)
        c = (150 + tone, 146 + tone, 138 + tone)
        d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=c,
                  outline=(96, 92, 84), width=4)
    img = img.filter(ImageFilter.GaussianBlur(1.4))
    return _save(img, "kw_rough.png")


def door_red():
    """朱漆板門: 縦板+門釘(金鋲)+鋪首(sasage_16の指定)."""
    w, h = 256, 512
    img = Image.new("RGB", (w, h), (108, 30, 22))
    d = ImageDraw.Draw(img)
    for x in range(0, w, 32):  # 縦板の目地
        d.line([(x, 0), (x, h)], fill=(84, 22, 16), width=3)
    gold = (196, 156, 72)
    for iy in range(7):  # 門釘 5列×7段
        for ix in range(5):
            cx, cy = 26 + ix * 51, 40 + iy * 64
            d.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=gold,
                      outline=(140, 104, 42), width=2)
    # 鋪首 (獅子環の略記: 金の円環)
    d.ellipse([w // 2 - 22, 236, w // 2 + 22, 280], outline=gold, width=7)
    d.ellipse([w // 2 - 12, 226, w // 2 + 12, 250], fill=gold)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    return _save(img, "kw_door.png")


def build_all():
    return dict(
        tile_grey=tiles(), tile_amber=tiles_amber(), redwall=red_wall(),
        frieze=frieze(), frieze_o=frieze_olive(), dougong=dougong_band(),
        lattice=lattice_door(), lattice_dk=lattice_door_dark(),
        paving=stone_paving(), ongro=cloud_ramp(),
        sudare=sudare(), rough_stone=rough_stone(), door=door_red(),
    )
