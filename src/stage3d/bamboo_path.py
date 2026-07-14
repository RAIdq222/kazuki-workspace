# -*- coding: utf-8 -*-
"""美術ボード「竹林の山道」の3Dステージ化 (v2: リーフカード方式)。

- 葉: 水彩風スプライト(sprites.py生成)を貼った板ポリ(リーフカード)を稈に沿って大量配置
- 頭上: 見上げカット用に道の上空へ天蓋カードを重ねる
- 遠景の山: 張りぼて(ビルボード板)
- 霧: 下ほど濃いグラデ板を奥行きに重ねる (fog_ 接頭辞 → ビューワーGLBからは除外)

実行例:
    python3 src/stage3d/bamboo_path.py -- --views A,U --samples 48 \
        --res 1600x900 --blend work/bamboo_path.blend
"""
import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from stagelib import (reset_scene, mat, mat_image, box, cyl, sphere, plane,  # noqa: E402
                      add_camera, sun_light, set_world, render_cli)
import sprites  # noqa: E402

R = random.Random(11)
SPR = "work/sprites"

PAL = {
    "dirt":        (0.430, 0.300, 0.140),
    "dirt_edge":   (0.300, 0.210, 0.100),
    "ground":      (0.070, 0.120, 0.045),
    "grass":       (0.085, 0.200, 0.048),
    "grass_dry":   (0.280, 0.290, 0.095),
    "rock":        (0.300, 0.295, 0.270),
    "rock_dark":   (0.185, 0.185, 0.170),
    "bamboo1":     (0.150, 0.290, 0.090),
    "bamboo2":     (0.210, 0.340, 0.110),
    "bamboo3":     (0.110, 0.230, 0.080),
    "bamboo_node": (0.320, 0.380, 0.170),
}


def scatter_copy(tpl, name, loc, rot=(0, 0, 0), scale=1.0):
    o = tpl.copy()
    o.name = name
    o.location = loc
    o.rotation_euler = rot
    o.scale = (tpl.scale[0] * scale, tpl.scale[1] * scale, tpl.scale[2] * scale)
    bpy.context.collection.objects.link(o)
    return o


def leaf_card(name, key, size, loc, rot):
    """垂直基準のリーフカード1枚 (plane は XY 面なので X軸90°回転を足す)."""
    m = mat_image(key, f"{SPR}/{key}.png", rough=0.9)
    return plane(name, size, size, loc, m,
                 rot=(rot[0] + math.pi / 2, rot[1], rot[2]))


def make_bamboo_template(idx):
    """テンプレート竹: 細めの稈 + 節 + 中〜上部のリーフカード → 1メッシュ."""
    h = R.uniform(6.5, 9.5)
    r = R.uniform(0.028, 0.048)
    key = R.choice(("bamboo1", "bamboo2", "bamboo3"))
    culm = mat(key, PAL[key], rough=0.5)
    node = mat("bamboo_node", PAL["bamboo_node"], rough=0.6)
    parts = []
    seg = R.uniform(0.5, 0.65)
    n_seg = int(h / seg)
    for i in range(n_seg):
        z = seg * (i + 0.5)
        parts.append(cyl(f"tpl{idx}_c{i}", r * (1 - 0.35 * i / n_seg), seg - 0.012,
                         (0, 0, z), culm, verts=8))
        if i < n_seg - 1:
            parts.append(cyl(f"tpl{idx}_n{i}", r * (1 - 0.35 * i / n_seg) + 0.006, 0.03,
                             (0, 0, z + seg / 2), node, verts=8))
    # リーフカード: 上部 55%〜頂部に密に、中部にまばらに
    leaf_key = R.choice(("leaf_dark", "leaf_mid", "leaf_light"))
    n_cards = R.randint(10, 15)
    for i in range(n_cards):
        zt = R.uniform(0.55, 1.02) if i > 2 else R.uniform(0.35, 0.6)
        z = h * zt
        off = R.uniform(0.15, 0.75)
        ang = R.uniform(0, 2 * math.pi)
        k = leaf_key if R.random() < 0.7 else R.choice(("leaf_dark", "leaf_mid", "leaf_light"))
        parts.append(leaf_card(f"tpl{idx}_lc{i}", k, R.uniform(0.8, 1.5),
                               (math.cos(ang) * off, math.sin(ang) * off, z),
                               (R.uniform(-0.5, 0.5), R.uniform(-0.6, 0.6),
                                R.uniform(0, 2 * math.pi))))
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    o = bpy.context.object
    o.name = f"bamboo_tpl_{idx}"
    return o


def build_ground():
    plane("ground", 90, 140, (0, 45, 0), mat("ground", PAL["ground"], rough=1.0))
    dirt = mat("dirt", PAL["dirt"], rough=0.95)
    dirt_e = mat("dirt_edge", PAL["dirt_edge"], rough=1.0)
    n = 14
    for i in range(n):
        y0 = -4 + i * 3.0
        wshrink = 1.0 - 0.55 * (i / n)
        wob = R.uniform(-0.12, 0.12)
        plane(f"path_{i}", 2.5 * wshrink, 3.2, (wob, y0 + 1.5, 0.012 + 0.0004 * i), dirt)
        plane(f"pathe_{i}", 3.1 * wshrink, 3.2, (wob, y0 + 1.5, 0.008 + 0.0004 * i), dirt_e)
    # 道端の石
    rock = mat("rock", PAL["rock"], rough=0.9)
    rock_d = mat("rock_dark", PAL["rock_dark"], rough=0.9)
    rock_tpls = []
    for i in range(4):
        rock_tpls.append(sphere(f"rock_tpl_{i}", 1.0, (0, -60, -5),
                                rock if i < 3 else rock_d,
                                scale=(1, R.uniform(0.7, 1.3), R.uniform(0.4, 0.6)),
                                smooth=False))
    for i in range(110):
        side = 1 if i % 2 == 0 else -1
        y = R.uniform(-4, 30)
        shrink = max(0.45, 1.0 - 0.55 * ((y + 4) / 42))
        x = side * (1.35 * shrink + R.uniform(0, 0.9))
        s = R.uniform(0.08, 0.30) * (0.5 + shrink)
        scatter_copy(R.choice(rock_tpls), f"rock_{i}", (x, y, s * 0.35),
                     rot=(0, 0, R.uniform(0, 6.28)), scale=s)
    # 草 (円錐の束)
    grass_tpls = []
    for i in range(3):
        key = ("grass", "grass", "grass_dry")[i]
        m = mat(key, PAL[key], rough=1.0)
        parts = []
        for k in range(4):
            parts.append(cyl(f"grass_tpl{i}_{k}", 0.05, 1.0,
                             (R.uniform(-0.3, 0.3), R.uniform(-0.3, 0.3), 0.5),
                             m, rot=(R.uniform(-0.5, 0.5), R.uniform(-0.5, 0.5), 0),
                             verts=5, r2=0.002))
        bpy.ops.object.select_all(action="DESELECT")
        for p in parts:
            p.select_set(True)
        bpy.context.view_layer.objects.active = parts[0]
        bpy.ops.object.join()
        t = bpy.context.object
        t.name = f"grass_tpl_{i}"
        t.location = (0, -60, -5)
        grass_tpls.append(t)
    for i in range(150):
        side = 1 if i % 2 == 0 else -1
        y = R.uniform(-4, 32)
        shrink = max(0.45, 1.0 - 0.55 * ((y + 4) / 42))
        x = side * (1.6 * shrink + R.uniform(0, 1.6))
        s = R.uniform(0.12, 0.32) * (0.5 + shrink)
        scatter_copy(R.choice(grass_tpls), f"grass_{i}", (x, y, 0),
                     rot=(0, 0, R.uniform(0, 6.28)), scale=s)
    # 道端の茂み (bushカード)
    bush = mat_image("bush", f"{SPR}/bush.png", rough=0.95)
    for i in range(46):
        side = 1 if i % 2 == 0 else -1
        y = R.uniform(0, 34)
        shrink = max(0.45, 1.0 - 0.55 * ((y + 4) / 42))
        x = side * (1.9 * shrink + R.uniform(0, 1.3))
        s = R.uniform(0.7, 1.5) * (0.45 + shrink)
        plane(f"bushcard_{i}", s, s, (x, y, s * 0.42),
              bush, rot=(math.pi / 2, 0, R.uniform(-0.5, 0.5)))


def build_bamboo_groves():
    tpls = []
    for i in range(6):
        t = make_bamboo_template(i)
        t.location = (0, -60, -20)
        tpls.append(t)
    idx = 0
    for band_y0, band_y1, step in ((-7, 12, 0.85), (12, 26, 1.0), (26, 40, 1.2)):
        y = band_y0
        while y < band_y1:
            for side in (-1, 1):
                shrink = max(0.4, 1.0 - 0.55 * ((y + 4) / 42))
                x_in = side * (2.1 * shrink + R.uniform(0.1, 0.6))
                n_row = 4 if y < 12 else 3
                for k in range(n_row):
                    x = x_in + side * (k * R.uniform(0.7, 1.2) + R.uniform(0, 0.4))
                    if abs(x) > 12:
                        continue
                    lean = R.uniform(math.radians(1), math.radians(8)) * (-side)
                    scatter_copy(R.choice(tpls), f"bamboo_{idx}",
                                 (x, y + R.uniform(-0.4, 0.4), 0),
                                 rot=(R.uniform(-0.03, 0.03), lean, R.uniform(0, 6.28)),
                                 scale=R.uniform(0.75, 1.25))
                    idx += 1
            y += step
    print("bamboo count:", idx)
    # 頭上の天蓋カード (見上げ用): 道の上空に大きめの葉カードを重ねる
    canopy_tpls = {}
    for key in ("leaf_dark", "leaf_mid", "leaf_light"):
        m = mat_image(key, f"{SPR}/{key}.png", rough=0.9)
        t = plane(f"canopy_tpl_{key}", 1, 1, (0, -60, -25), m)
        canopy_tpls[key] = t
    for i in range(120):
        y = R.uniform(-6, 34)
        shrink = max(0.4, 1.0 - 0.55 * ((y + 4) / 42))
        # 道の真上にも薄く、両脇に濃く
        if i % 3 == 0:
            x = R.uniform(-1.2, 1.2) * shrink
            z = R.uniform(7.0, 9.5) * (0.55 + 0.45 * shrink)
        else:
            side = 1 if i % 2 == 0 else -1
            x = side * R.uniform(1.2, 5.0) * shrink
            z = R.uniform(5.0, 9.0) * (0.55 + 0.45 * shrink)
        key = R.choice(("leaf_dark", "leaf_dark", "leaf_mid", "leaf_light"))
        s = R.uniform(1.6, 2.8) * (0.5 + 0.5 * shrink)
        o = scatter_copy(canopy_tpls[key], f"canopy_{i}", (x, y, z),
                         rot=(R.uniform(-0.35, 0.35), R.uniform(-0.35, 0.35),
                              R.uniform(0, 6.28)),
                         scale=s)


def build_backdrop():
    """張りぼての山 + 奥の竹の壁."""
    ma = mat_image("mountain_a", f"{SPR}/mountain_a.png", rough=1.0, blend="BLEND")
    mb = mat_image("mountain_b", f"{SPR}/mountain_b.png", rough=1.0, blend="BLEND")
    # plane は XY面 → X軸90°回転で立てる (カメラ正面向き)
    plane("mtn_main", 62, 62, (0, 66, 24.0), ma, rot=(math.pi / 2, 0, 0))
    plane("mtn_l", 38, 38, (-26, 80, 14.5), mb, rot=(math.pi / 2, 0, 0))
    plane("mtn_r", 34, 34, (24, 84, 13.0), mb, rot=(math.pi / 2, 0, 0))
    # 奥の竹の壁 (遠景のシルエット): 濃緑の背の高い板
    wall = mat("far_bamboo", (0.24, 0.34, 0.26), rough=1.0)
    for i, (x, y, w, h) in enumerate([(-9, 42, 10, 12), (9, 44, 10, 13),
                                      (-16, 48, 12, 14), (16, 50, 12, 14)]):
        plane(f"farwall_{i}", w, h, (x, y, h / 2), wall, rot=(math.pi / 2, 0, 0))


def build_fog_and_sky():
    """霧: 下ほど濃いグラデ板 (fog_ 接頭辞: GLBから除外しビューワーはFogで代替)."""
    mist = mat_image("mist", f"{SPR}/mist.png", rough=1.0, blend="BLEND", emit=0.4)
    defs = [(12, 4), (20, 7), (32, 11), (48, 18)]
    for i, (y, h) in enumerate(defs):
        # mist.png は上が透明・下が濃い → そのまま立てる
        plane(f"fog_{i}", 200, h, (0, y, h / 2 - 0.2), mist, rot=(math.pi / 2, 0, 0))
    set_world((0.80, 0.84, 0.82), strength=1.0)


def build_scene():
    if not os.path.exists(f"{SPR}/leaf_mid.png"):
        sprites.generate_all(SPR)
    reset_scene()
    build_ground()
    build_bamboo_groves()
    build_backdrop()
    build_fog_and_sky()
    # 逆光気味の主光 (奥から手前へ) + 手前からの弱い返し
    sun_light("sun_back", rot=(math.radians(-52), 0, math.radians(8)), energy=3.4,
              color=(1.0, 0.99, 0.94), angle_deg=15)
    sun_light("sun_fill", rot=(math.radians(50), 0, math.radians(-12)), energy=1.1,
              color=(0.95, 1.0, 0.96), angle_deg=25)
    cams = {
        "A": add_camera("cam_A", (0.0, -6.5, 1.3), (0.0, 20.0, 6.2), lens=24),
        "B": add_camera("cam_B", (-3.2, -2.0, 1.6), (2.5, 18.0, 3.5), lens=28),
        "U": add_camera("cam_U", (0.3, 6.0, 1.2), (1.5, 9.0, 30.0), lens=20),
        "T": add_camera("cam_T", (0.0, -14.0, 14.0), (0.0, 22.0, 2.0), lens=35),
    }
    return cams


if __name__ == "__main__":
    cams = build_scene()
    render_cli(cams, default_res="1600x900", view_transform="Standard", exposure=0.0)
