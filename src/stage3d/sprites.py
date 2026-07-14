# -*- coding: utf-8 -*-
"""竹林ステージ用の水彩風スプライト生成 (PIL)。

- 笹葉の房 (leaf_dark / leaf_mid / leaf_light): リーフカード用
- 下草の茂み (bush)
- 遠景のカルスト岩山 (mountain_a / mountain_b): 張りぼてビルボード用
- 霧のグラデーション (mist): 下ほど濃い縦グラデ

`python3 src/stage3d/sprites.py [出力ディレクトリ]` で PNG を書き出す。
"""
import math
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFilter

R = random.Random(21)


def _leaf_polygon(cx, cy, length, width, angle):
    """笹の葉 (披針形) のポリゴン点列."""
    pts = []
    n = 7
    for i in range(n + 1):
        t = i / n
        w = width * math.sin(math.pi * min(1.0, t * 1.15)) * (1 - 0.35 * t)
        pts.append((t * length, -w / 2))
    for i in range(n + 1):
        t = 1 - i / n
        w = width * math.sin(math.pi * min(1.0, t * 1.15)) * (1 - 0.35 * t)
        pts.append((t * length, w / 2))
    ca, sa = math.cos(angle), math.sin(angle)
    return [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts]


def leaf_cluster_sprite(path, tones, size=512, n_fans=14):
    """笹葉の房: 数枚ずつ扇状に出る葉の束をばら撒く."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for _ in range(n_fans):
        fx = R.uniform(size * 0.15, size * 0.85)
        fy = R.uniform(size * 0.15, size * 0.85)
        base_ang = R.uniform(0, 2 * math.pi)
        n_leaf = R.randint(3, 5)
        for k in range(n_leaf):
            ang = base_ang + (k - n_leaf / 2) * R.uniform(0.25, 0.45)
            ln = R.uniform(size * 0.16, size * 0.30)
            wd = ln * R.uniform(0.16, 0.24)
            col = R.choice(tones)
            a = R.randint(190, 245)
            jitter = tuple(max(0, min(255, c + R.randint(-14, 14))) for c in col)
            d.polygon(_leaf_polygon(fx, fy, ln, wd, ang), fill=(*jitter, a))
    # 水彩のにじみ: 軽いぼかしを重ねる
    soft = img.filter(ImageFilter.GaussianBlur(1.4))
    img = Image.alpha_composite(soft, img.filter(ImageFilter.GaussianBlur(0.5)))
    img.save(path)


def bush_sprite(path, size=512):
    """道端の下草・灌木の茂み (下が接地するシルエット)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    tones = [(40, 84, 34), (56, 106, 42), (74, 124, 50), (32, 68, 30)]
    for _ in range(70):
        x = R.uniform(size * 0.1, size * 0.9)
        y = size - abs(R.gauss(0, size * 0.28)) - size * 0.05
        r = R.uniform(size * 0.05, size * 0.13) * (0.6 + 0.6 * (y / size))
        col = R.choice(tones)
        jitter = tuple(max(0, min(255, c + R.randint(-12, 12))) for c in col)
        d.ellipse([x - r, y - r * 0.8, x + r, y + r * 0.8], fill=(*jitter, R.randint(200, 245)))
    for _ in range(28):  # 上に飛び出る葉
        x = R.uniform(size * 0.15, size * 0.85)
        y = R.uniform(size * 0.25, size * 0.75)
        ang = -math.pi / 2 + R.uniform(-0.8, 0.8)
        d.polygon(_leaf_polygon(x, y, R.uniform(size * 0.10, size * 0.2),
                                size * 0.03, ang),
                  fill=(*R.choice(tones), R.randint(190, 240)))
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    img.save(path)


def mountain_sprite(path, size=1024, seed=1, towers=3):
    """霧に霞むカルスト岩山の張りぼて。下端は霧に溶けるように透明へ."""
    rr = random.Random(seed)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rock = (150, 148, 138)
    rock_sh = (114, 118, 116)
    green = (96, 128, 78)
    green_d = (72, 104, 62)
    for t in range(towers):
        cx = size * (0.5 + (t - (towers - 1) / 2) * rr.uniform(0.24, 0.3))
        top = size * rr.uniform(0.06, 0.22) + t * size * 0.06
        base_w = size * rr.uniform(0.26, 0.36)
        # 岩塔本体: 縦長の不規則シルエット
        pts = []
        n = 14
        for i in range(n + 1):
            u = i / n
            y = top + (size - top) * u
            w = base_w * (0.55 + 0.45 * u) * (1 + 0.18 * math.sin(u * 9 + t))
            pts.append((cx - w / 2 + rr.uniform(-8, 8), y))
        for i in range(n + 1):
            u = 1 - i / n
            y = top + (size - top) * u
            w = base_w * (0.55 + 0.45 * u) * (1 + 0.18 * math.sin(u * 7 + t * 2))
            pts.append((cx + w / 2 + rr.uniform(-8, 8), y))
        d.polygon(pts, fill=(*rock, 235))
        # 縦の岩肌ストローク
        for _ in range(26):
            x = cx + rr.uniform(-base_w * 0.45, base_w * 0.45)
            y0 = top + rr.uniform(0.05, 0.5) * (size - top)
            ln = rr.uniform(size * 0.06, size * 0.22)
            d.line([(x, y0), (x + rr.uniform(-6, 6), y0 + ln)],
                   fill=(*rock_sh, rr.randint(60, 120)), width=rr.randint(3, 8))
        # 頂と段の緑
        d.ellipse([cx - base_w * 0.42, top - size * 0.03,
                   cx + base_w * 0.42, top + size * 0.06],
                  fill=(*green, 235))
        for _ in range(10):
            x = cx + rr.uniform(-base_w * 0.5, base_w * 0.5)
            y = top + rr.uniform(0.08, 0.75) * (size - top)
            r = rr.uniform(size * 0.015, size * 0.05)
            g = green if rr.random() < 0.6 else green_d
            d.ellipse([x - r, y - r * 0.6, x + r, y + r * 0.6], fill=(*g, rr.randint(150, 220)))
    img = img.filter(ImageFilter.GaussianBlur(2.2))
    # 下端を霧に溶かす + 全体をわずかに白へ寄せる(空気遠近)
    px = img.load()
    for yy in range(size):
        fade = min(1.0, max(0.0, (size * 0.92 - yy) / (size * 0.45)))  # 下端ほど0
        fade = fade if yy > size * 0.5 else 1.0
        haze = 0.12
        for xx in range(size):
            r0, g0, b0, a0 = px[xx, yy]
            if a0 == 0:
                continue
            r0 = int(r0 * (1 - haze) + 236 * haze)
            g0 = int(g0 * (1 - haze) + 240 * haze)
            b0 = int(b0 * (1 - haze) + 238 * haze)
            px[xx, yy] = (r0, g0, b0, int(a0 * fade))
    img.save(path)


def mist_sprite(path, size=512):
    """下ほど濃い霧のグラデーション板."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    for yy in range(size):
        a = int(185 * (yy / size) ** 2.4)
        for xx in range(size):
            px[xx, yy] = (235, 240, 237, a)
    img.save(path)


def ground_texture(path, size=768):
    """地面: 苔・下草のまだら (不透明・タイル用)."""
    img = Image.new("RGB", (size, size), (34, 54, 24))
    d = ImageDraw.Draw(img)
    tones = [(30, 50, 22), (42, 66, 28), (54, 80, 36), (64, 90, 40),
             (46, 60, 26), (70, 80, 36), (38, 46, 22)]
    for _ in range(650):
        x, y = R.uniform(0, size), R.uniform(0, size)
        r = R.uniform(size * 0.008, size * 0.05)
        col = R.choice(tones)
        jitter = tuple(max(0, min(255, c + R.randint(-8, 8))) for c in col)
        d.ellipse([x - r, y - r * 0.7, x + r, y + r * 0.7], fill=jitter)
    for _ in range(220):  # 細かい草ストローク
        x, y = R.uniform(0, size), R.uniform(0, size)
        ln = R.uniform(size * 0.01, size * 0.03)
        ang = R.uniform(-0.6, 0.6) - math.pi / 2
        col = R.choice(tones[2:5])
        d.line([(x, y), (x + math.cos(ang) * ln, y + math.sin(ang) * ln)],
               fill=col, width=2)
    img = img.filter(ImageFilter.GaussianBlur(1.0))
    img.save(path)


def path_texture(path, size=768):
    """道: 乾いた土 + 轍 + 小石。u方向(横断方向)の両端を暗く."""
    img = Image.new("RGB", (size, size), (168, 128, 76))
    d = ImageDraw.Draw(img)
    tones = [(150, 112, 64), (178, 138, 84), (190, 152, 96), (140, 104, 60), (162, 124, 74)]
    for _ in range(420):
        x, y = R.uniform(0, size), R.uniform(0, size)
        r = R.uniform(size * 0.01, size * 0.06)
        d.ellipse([x - r, y - r * 0.5, x + r, y + r * 0.5], fill=R.choice(tones))
    for _ in range(18):  # 進行方向のかすかな筋 (轍)。強すぎると板張りに見えるので控えめに
        x = R.uniform(0, size)
        y0 = R.uniform(0, size * 0.7)
        ln = R.uniform(size * 0.1, size * 0.35)
        c = R.choice([(158, 120, 70), (176, 138, 86)])
        d.line([(x, y0), (x + R.uniform(-24, 24), y0 + ln)], fill=c, width=2)
    for _ in range(90):  # 小石
        x, y = R.uniform(0, size), R.uniform(0, size)
        r = R.uniform(2, 6)
        g = R.randint(120, 175)
        d.ellipse([x - r, y - r * 0.8, x + r, y + r * 0.8],
                  fill=(g, g - R.randint(5, 20), g - R.randint(20, 40)))
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    # 両端(u=0,1)を暗く湿った感じに
    px = img.load()
    for x in range(size):
        u = x / size
        edge = min(u, 1 - u) / 0.18
        f = 0.72 + 0.28 * min(1.0, edge)
        for y in range(size):
            r0, g0, b0 = px[x, y]
            px[x, y] = (int(r0 * f), int(g0 * f), int(b0 * f))
    img.save(path)


def rock_texture(path, size=512):
    """石: 水彩の岩肌 (濃淡のウォッシュ + ひび)."""
    img = Image.new("RGB", (size, size), (128, 126, 120))
    d = ImageDraw.Draw(img)
    tones = [(96, 98, 94), (146, 144, 134), (168, 166, 156), (112, 108, 100),
             (84, 88, 86), (140, 132, 118), (158, 152, 138)]
    for _ in range(220):
        x, y = R.uniform(0, size), R.uniform(0, size)
        r = R.uniform(size * 0.03, size * 0.18)
        d.ellipse([x - r, y - r * 0.7, x + r, y + r * 0.7], fill=R.choice(tones))
    for _ in range(40):  # ひび・陰線
        x, y = R.uniform(0, size), R.uniform(0, size)
        pts = [(x, y)]
        for _ in range(4):
            x += R.uniform(-size * 0.08, size * 0.08)
            y += R.uniform(size * 0.02, size * 0.09)
            pts.append((x, y))
        d.line(pts, fill=(70, 74, 74), width=R.randint(2, 5))
    img = img.filter(ImageFilter.GaussianBlur(1.4))
    # 上面ほど明るく (立体感)
    px = img.load()
    for yy in range(size):
        f = 1.14 - 0.34 * (yy / size)
        for xx in range(size):
            r0, g0, b0 = px[xx, yy]
            px[xx, yy] = (min(255, int(r0 * f)), min(255, int(g0 * f)), min(255, int(b0 * f)))
    img.save(path)


def generate_all(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    leaf_cluster_sprite(os.path.join(out_dir, "leaf_dark.png"),
                        [(38, 84, 40), (52, 100, 48), (30, 70, 36)])
    leaf_cluster_sprite(os.path.join(out_dir, "leaf_mid.png"),
                        [(72, 130, 58), (92, 148, 66), (58, 112, 50)])
    leaf_cluster_sprite(os.path.join(out_dir, "leaf_light.png"),
                        [(120, 172, 84), (142, 188, 96), (100, 156, 74)])
    bush_sprite(os.path.join(out_dir, "bush.png"))
    mountain_sprite(os.path.join(out_dir, "mountain_a.png"), seed=3, towers=3)
    mountain_sprite(os.path.join(out_dir, "mountain_b.png"), seed=8, towers=2)
    mist_sprite(os.path.join(out_dir, "mist.png"))
    ground_texture(os.path.join(out_dir, "ground.png"))
    path_texture(os.path.join(out_dir, "path.png"))
    rock_texture(os.path.join(out_dir, "rock.png"))
    print("sprites ->", out_dir)


if __name__ == "__main__":
    generate_all(sys.argv[1] if len(sys.argv) > 1 else "work/sprites")
