# -*- coding: utf-8 -*-
"""東中野の路地シーン用テクスチャ生成 (PIL)。

実写ボードは受け渡しがチャット貼付のため原画クロップは使えない。
ブロック塀・スタッコ・アスファルト・看板(実テキスト)を手続き生成する。
出力: work/sprites/aly_*.png
"""
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = os.path.join(os.path.dirname(__file__), "..", "..", "work", "sprites")
os.makedirs(OUT, exist_ok=True)
FONT = "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"
rng = random.Random(7)


def _noise(img, amp=10, blur=1.2, seed=0):
    r = random.Random(seed)
    w, h = img.size
    n = Image.new("L", (w // 2, h // 2))
    n.putdata([128 + r.randint(-amp, amp) for _ in range((w // 2) * (h // 2))])
    n = n.resize((w, h)).filter(ImageFilter.GaussianBlur(blur))
    px, npx = img.load(), n.load()
    for y in range(h):
        for x in range(w):
            d = npx[x, y] - 128
            c = px[x, y]
            px[x, y] = tuple(max(0, min(255, v + d)) for v in c[:3]) + c[3:]
    return img


def _stains(dr, w, h, n, color, rmin, rmax, alpha_img=None, seed=1):
    """雨だれ・カビ風の丸ジミ (下側ほど多い)."""
    r = random.Random(seed)
    for _ in range(n):
        x = r.uniform(0, w)
        y = h - abs(r.gauss(0, h * 0.45))
        rad = r.uniform(rmin, rmax)
        dr.ellipse([x - rad, y - rad, x + rad, y + rad], fill=color)


def blockwall():
    """CBブロック塀タイル。1タイル=幅0.8m×高さ0.8m (ブロック2×4段)."""
    w, h = 512, 512
    img = Image.new("RGB", (w, h), (152, 150, 144))
    dr = ImageDraw.Draw(img, "RGBA")
    bw, bh = w // 2, h // 4  # 390x190mm 相当
    for row in range(4):
        off = (row % 2) * bw // 2
        for col in range(-1, 3):
            x0 = col * bw + off
            y0 = row * bh
            tone = rng.randint(-9, 9)
            dr.rectangle([x0 + 3, y0 + 3, x0 + bw - 3, y0 + bh - 3],
                         fill=(152 + tone, 150 + tone, 144 + tone - 2))
            # ブロック面の穴の影 (フェイスシェル風の2つの薄い凹み)
            for k in (0.28, 0.72):
                cx = x0 + bw * k
                dr.rectangle([cx - bw * 0.16, y0 + bh * 0.22,
                              cx + bw * 0.16, y0 + bh * 0.78],
                             fill=(0, 0, 0, 10))
    # 目地
    for row in range(5):
        dr.line([(0, row * bh), (w, row * bh)], fill=(120, 118, 112), width=5)
    for row in range(4):
        off = (row % 2) * bw // 2
        for col in range(3):
            x = col * bw + off
            dr.line([(x % w, row * bh), (x % w, row * bh + bh)],
                    fill=(126, 124, 118), width=5)
    _stains(dr, w, h, 60, (60, 62, 58, 26), 6, 42, seed=3)
    _stains(dr, w, h, 25, (218, 218, 212, 30), 4, 22, seed=4)
    img = _noise(img, 7, 1.0, seed=5)
    img.save(f"{OUT}/aly_block.png")


def stucco(name, base, amp=8, speck=None, seed=11):
    w = h = 512
    img = Image.new("RGB", (w, h), base)
    img = _noise(img, amp, 0.8, seed=seed)
    if speck:
        dr = ImageDraw.Draw(img, "RGBA")
        r = random.Random(seed + 1)
        for _ in range(2600):
            x, y = r.uniform(0, w), r.uniform(0, h)
            rad = r.uniform(0.6, 2.0)
            dr.ellipse([x - rad, y - rad, x + rad, y + rad], fill=speck)
    img.save(f"{OUT}/{name}.png")


def asphalt():
    w = h = 512
    img = Image.new("RGB", (w, h), (76, 77, 80))
    img = _noise(img, 9, 0.7, seed=21)
    dr = ImageDraw.Draw(img, "RGBA")
    r = random.Random(22)
    for _ in range(4000):  # 骨材の粒
        x, y = r.uniform(0, w), r.uniform(0, h)
        g = r.randint(70, 150)
        dr.point([x, y], fill=(g, g, g + 2, 90))
    for _ in range(10):  # 補修痕・シミ
        x, y = r.uniform(0, w), r.uniform(0, h)
        rad = r.uniform(24, 80)
        dr.ellipse([x - rad, y - rad, x + rad, y + rad], fill=(70, 71, 72, 22))
    img = img.filter(ImageFilter.GaussianBlur(0.4))
    img.save(f"{OUT}/aly_asphalt.png")


def concrete_gutter():
    """側溝の蓋。1タイル=長さ0.6m (継ぎ目1本+水抜き穴2つ)."""
    w, h = 256, 256
    img = Image.new("RGB", (w, h), (138, 138, 134))
    img = _noise(img, 7, 0.9, seed=31)
    dr = ImageDraw.Draw(img, "RGBA")
    dr.line([(0, 4), (w, 4)], fill=(104, 104, 100), width=6)  # 継ぎ目
    for k in (0.35, 0.65):
        dr.ellipse([w * k - 5, h * 0.5 - 10, w * k + 5, h * 0.5 + 10],
                   fill=(96, 96, 92))
    _stains(dr, w, h, 18, (80, 82, 76, 30), 4, 26, seed=32)
    img.save(f"{OUT}/aly_gutter.png")


def siding(name, base, dark, step=42, seed=41):
    """横張りサイディング。1タイル=高さ約1.2m."""
    w = h = 512
    img = Image.new("RGB", (w, h), base)
    dr = ImageDraw.Draw(img, "RGBA")
    for y in range(0, h, step):
        dr.line([(0, y), (w, y)], fill=dark, width=4)
        dr.line([(0, y + 4), (w, y + 4)], fill=(255, 255, 255, 26), width=2)
    img = _noise(img, 6, 1.0, seed=seed)
    img.save(f"{OUT}/{name}.png")


def wood_panel():
    """右アパート2Fの焦げ茶板壁。縦板+うっすら木目."""
    w = h = 512
    img = Image.new("RGB", (w, h), (68, 50, 38))
    dr = ImageDraw.Draw(img, "RGBA")
    for x in range(0, w, 64):
        tone = rng.randint(-8, 8)
        dr.rectangle([x, 0, x + 64, h], fill=(68 + tone, 50 + tone, 38 + tone))
        dr.line([(x, 0), (x, h)], fill=(40, 30, 22), width=3)
    for _ in range(60):  # 木目スジ
        x = rng.uniform(0, w)
        dr.line([(x, 0), (x + rng.uniform(-6, 6), h)],
                fill=(0, 0, 0, 14), width=1)
    img = _noise(img, 5, 1.2, seed=51)
    img.save(f"{OUT}/aly_wood.png")


def sign_bosyu():
    """入居者募集看板 (左建物)。実写の文字を転記."""
    w, h = 384, 512
    img = Image.new("RGB", (w, h), (250, 250, 248))
    dr = ImageDraw.Draw(img)
    f_big = ImageFont.truetype(FONT, 62)
    f_mid = ImageFont.truetype(FONT, 44)
    f_sml = ImageFont.truetype(FONT, 30)
    dr.rectangle([0, 0, w, 96], fill=(20, 120, 62))
    dr.text((w / 2, 48), "入居者募集", font=f_big, fill=(255, 255, 255), anchor="mm")
    dr.text((w / 2, 165), "(株) ABCホーム", font=f_mid, fill=(30, 100, 55), anchor="mm")
    dr.text((w / 2, 245), "TEL: 03-1234-5678", font=f_sml, fill=(40, 40, 45), anchor="mm")
    dr.text((w / 2, 320), "お気軽にお問合せください", font=f_sml, fill=(60, 60, 65), anchor="mm")
    dr.rectangle([40, 390, w - 40, 470], fill=(200, 40, 40))
    dr.text((w / 2, 430), "空室あり", font=f_mid, fill=(255, 255, 255), anchor="mm")
    img = _noise(img, 3, 0.6, seed=61)
    img.save(f"{OUT}/aly_sign_bosyu.png")


def sign_bosyu_small():
    """右の壁の入居者募集 (小・色あせ)."""
    w, h = 320, 448
    img = Image.new("RGB", (w, h), (240, 240, 236))
    dr = ImageDraw.Draw(img)
    f_big = ImageFont.truetype(FONT, 50)
    f_sml = ImageFont.truetype(FONT, 26)
    dr.rectangle([0, 0, w, 82], fill=(60, 140, 90))
    dr.text((w / 2, 41), "入居者募集", font=f_big, fill=(250, 250, 250), anchor="mm")
    dr.text((w / 2, 150), "(株)中野ホーム", font=f_sml, fill=(70, 90, 80), anchor="mm")
    dr.text((w / 2, 210), "TEL 03-9876-5432", font=f_sml, fill=(90, 90, 95), anchor="mm")
    dr.text((w / 2, 270), "1K・2DK 空室あり", font=f_sml, fill=(90, 90, 95), anchor="mm")
    img = _noise(img, 5, 0.8, seed=62)
    img.save(f"{OUT}/aly_sign_small.png")


def nameplate():
    """ハイツグリーン東中野 の館銘板 (焦げ茶メタル+白文字)."""
    w, h = 448, 320
    img = Image.new("RGB", (w, h), (74, 58, 44))
    dr = ImageDraw.Draw(img, "RGBA")
    f = ImageFont.truetype(FONT, 58)
    dr.rectangle([6, 6, w - 6, h - 6], outline=(100, 84, 66), width=4)
    dr.text((w / 2, h / 2 - 42), "ハイツグリーン", font=f, fill=(235, 232, 225), anchor="mm")
    dr.text((w / 2, h / 2 + 46), "東中野", font=f, fill=(235, 232, 225), anchor="mm")
    _stains(dr, w, h, 14, (30, 24, 18, 40), 4, 18, seed=71)
    img = _noise(img, 5, 1.0, seed=72)
    img.save(f"{OUT}/aly_plate.png")


def door_brown():
    """焦げ茶の玄関ドア (鋼板フラット+ノブ影)."""
    w, h = 256, 512
    img = Image.new("RGB", (w, h), (56, 44, 38))
    dr = ImageDraw.Draw(img, "RGBA")
    dr.rectangle([10, 10, w - 10, h - 10], outline=(38, 30, 26), width=6)
    dr.rectangle([28, 40, w - 28, 120], fill=(62, 50, 43))  # 上部パネル
    dr.rectangle([w - 60, h // 2 - 8, w - 32, h // 2 + 8], fill=(150, 145, 135))
    dr.rectangle([30, h - 90, w - 30, h - 70], fill=(48, 38, 33))  # 蹴込み
    img = _noise(img, 4, 1.0, seed=81)
    img.save(f"{OUT}/aly_door.png")


def sky_clouds():
    """曇り混じりの青空 (ワールド/ビューワー背景ボード用)."""
    w, h = 1024, 512
    img = Image.new("RGB", (w, h), (120, 158, 205))
    dr = ImageDraw.Draw(img, "RGBA")
    # 上ほど濃い青
    for y in range(h):
        t = y / h
        dr.line([(0, y), (w, y)],
                fill=(int(104 + 62 * t), int(146 + 54 * t), int(198 + 40 * t)))
    r = random.Random(91)
    for _ in range(46):  # もこもこ雲
        cx, cy = r.uniform(0, w), r.uniform(h * 0.25, h * 0.95)
        for _ in range(r.randint(6, 14)):
            x = cx + r.gauss(0, 60)
            y = cy + r.gauss(0, 16)
            rad = r.uniform(18, 55)
            dr.ellipse([x - rad, y - rad * 0.55, x + rad, y + rad * 0.55],
                       fill=(248, 250, 252, 60))
    img = img.filter(ImageFilter.GaussianBlur(6))
    img.save(f"{OUT}/aly_sky.png")


if __name__ == "__main__":
    blockwall()
    stucco("aly_stucco_w", (226, 224, 216), amp=6, speck=(200, 198, 190, 60))
    stucco("aly_stucco_p", (150, 120, 110), amp=8, speck=(108, 84, 78, 70), seed=13)
    stucco("aly_stucco_c", (206, 196, 178), amp=7, speck=(178, 168, 150, 60), seed=15)
    asphalt()
    concrete_gutter()
    siding("aly_siding_g", (142, 156, 138), (98, 112, 96))
    siding("aly_siding_w", (214, 214, 208), (168, 168, 162), step=48, seed=43)
    wood_panel()
    sign_bosyu()
    sign_bosyu_small()
    nameplate()
    door_brown()
    sky_clouds()
    print("wrote aly_* textures ->", os.path.abspath(OUT))
