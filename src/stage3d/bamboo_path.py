# -*- coding: utf-8 -*-
"""美術ボード「竹林の山道」の3Dステージ化。

ボードの構成: 中央に土の一本道(消失点へ)、両脇に石垣と草、密な竹林、
中景に広葉樹の茂み、遠景に霧に霞むカルスト状の岩山、明るい曇り空。

実行例:
    python3 src/stage3d/bamboo_path.py -- --views A --samples 64 \
        --res 1280x720 --blend work/bamboo_path.blend
"""
import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from stagelib import (reset_scene, mat, box, cyl, sphere, plane, add_camera,  # noqa: E402
                      sun_light, set_world, render_cli)

R = random.Random(11)

PAL = {
    "dirt":        (0.360, 0.240, 0.110),
    "dirt_edge":   (0.240, 0.170, 0.080),
    "ground":      (0.055, 0.085, 0.035),
    "grass":       (0.100, 0.190, 0.055),
    "grass_dry":   (0.230, 0.240, 0.080),
    "rock":        (0.280, 0.290, 0.280),
    "rock_dark":   (0.160, 0.170, 0.165),
    "bamboo1":     (0.130, 0.240, 0.080),
    "bamboo2":     (0.180, 0.290, 0.100),
    "bamboo3":     (0.090, 0.190, 0.070),
    "bamboo_node": (0.280, 0.330, 0.150),
    "leaf_dark":   (0.055, 0.140, 0.050),
    "leaf_mid":    (0.095, 0.200, 0.070),
    "leaf_light":  (0.160, 0.280, 0.100),
    "cliff":       (0.340, 0.260, 0.210),
    "cliff_green": (0.120, 0.200, 0.090),
    "fog_white":   (0.900, 0.930, 0.910),
}


def leaf_cluster(name, loc, r, key):
    """アニメ的な葉の塊: 潰した球を数個."""
    m = mat(key, PAL[key], rough=0.9)
    n = R.randint(2, 4)
    for i in range(n):
        sphere(f"{name}_{i}", r * R.uniform(0.55, 0.95),
               (loc[0] + R.uniform(-r, r) * 0.7,
                loc[1] + R.uniform(-r, r) * 0.7,
                loc[2] + R.uniform(-r, r) * 0.45),
               m, scale=(1, 1, R.uniform(0.45, 0.7)))


def make_bamboo_template(idx):
    """テンプレート竹1本 (原点に直立): 節付きの稈 + 上部の葉 → 1メッシュに結合."""
    h = R.uniform(6.0, 8.5)
    r = R.uniform(0.04, 0.06)
    key = R.choice(("bamboo1", "bamboo2", "bamboo3"))
    culm = mat(key, PAL[key], rough=0.55)
    node = mat("bamboo_node", PAL["bamboo_node"], rough=0.6)
    parts = []
    seg = R.uniform(0.55, 0.7)
    n_seg = int(h / seg)
    for i in range(n_seg):
        z = seg * (i + 0.5)
        parts.append(cyl(f"tpl{idx}_c{i}", r * (1 - 0.3 * i / n_seg), seg - 0.015,
                         (0, 0, z), culm, verts=10))
        if i < n_seg - 1:
            parts.append(cyl(f"tpl{idx}_n{i}", r * (1 - 0.3 * i / n_seg) + 0.008, 0.035,
                             (0, 0, z + seg / 2), node, verts=10))
    key_leaf = R.choice(("leaf_dark", "leaf_mid", "leaf_light"))
    m = mat(key_leaf, PAL[key_leaf], rough=0.9)
    for i in range(R.randint(3, 5)):
        rr = R.uniform(0.35, 0.75)
        parts.append(sphere(f"tpl{idx}_lf{i}", rr,
                            (R.uniform(-0.6, 0.6), R.uniform(-0.6, 0.6),
                             h * R.uniform(0.82, 0.98)),
                            m, scale=(1, 1, R.uniform(0.4, 0.65))))
    if R.random() < 0.6:
        parts.append(sphere(f"tpl{idx}_lm", R.uniform(0.2, 0.4),
                            (R.uniform(-0.4, 0.4), R.uniform(-0.4, 0.4),
                             h * R.uniform(0.5, 0.7)),
                            m, scale=(1, 1, 0.5)))
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    o = bpy.context.object
    o.name = f"bamboo_tpl_{idx}"
    return o


def scatter_copy(tpl, name, loc, rot=(0, 0, 0), scale=1.0):
    """リンク複製 (メッシュ共有) の高速配置."""
    o = tpl.copy()
    o.name = name
    o.location = loc
    o.rotation_euler = rot
    o.scale = (tpl.scale[0] * scale, tpl.scale[1] * scale, tpl.scale[2] * scale)
    bpy.context.collection.objects.link(o)
    return o


def build_ground():
    plane("ground", 90, 140, (0, 45, 0), mat("ground", PAL["ground"], rough=1.0))
    # 道: 消失点へ向かってわずかに細くなる台形を重ねる
    dirt = mat("dirt", PAL["dirt"], rough=0.95)
    dirt_e = mat("dirt_edge", PAL["dirt_edge"], rough=1.0)
    n = 14
    for i in range(n):
        y0 = -4 + i * 3.0
        wshrink = 1.0 - 0.55 * (i / n)
        wob = R.uniform(-0.12, 0.12)
        plane(f"path_{i}", 2.5 * wshrink, 3.2, (wob, y0 + 1.5, 0.012 + 0.0004 * i), dirt)
        plane(f"pathe_{i}", 3.1 * wshrink, 3.2, (wob, y0 + 1.5, 0.008 + 0.0004 * i), dirt_e)
    # 道端の石 (テンプレート4種をリンク複製)
    rock = mat("rock", PAL["rock"], rough=0.9)
    rock_d = mat("rock_dark", PAL["rock_dark"], rough=0.9)
    rock_tpls = []
    for i in range(4):
        t = sphere(f"rock_tpl_{i}", 1.0, (0, -60, -5),
                   rock if i < 3 else rock_d,
                   scale=(1, R.uniform(0.7, 1.3), R.uniform(0.4, 0.6)), smooth=False)
        rock_tpls.append(t)
    for i in range(90):
        side = 1 if i % 2 == 0 else -1
        y = R.uniform(-4, 30)
        shrink = max(0.45, 1.0 - 0.55 * ((y + 4) / 42))
        x = side * (1.35 * shrink + R.uniform(0, 0.9))
        s = R.uniform(0.08, 0.30) * (0.5 + shrink)
        scatter_copy(R.choice(rock_tpls), f"rock_{i}", (x, y, s * 0.35),
                     rot=(0, 0, R.uniform(0, 6.28)), scale=s)
    # 草むら (束を1メッシュ化したテンプレートを複製)
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
    for i in range(140):
        side = 1 if i % 2 == 0 else -1
        y = R.uniform(-4, 32)
        shrink = max(0.45, 1.0 - 0.55 * ((y + 4) / 42))
        x = side * (1.6 * shrink + R.uniform(0, 1.6))
        s = R.uniform(0.15, 0.5) * (0.5 + shrink)
        scatter_copy(R.choice(grass_tpls), f"grass_{i}", (x, y, 0),
                     rot=(0, 0, R.uniform(0, 6.28)), scale=s)


def build_bamboo_groves():
    # テンプレート6種 (画面外に置いておく)
    tpls = []
    for i in range(6):
        t = make_bamboo_template(i)
        t.location = (0, -60, -20)
        tpls.append(t)
    idx = 0
    # 手前〜中景: 道の両側に帯状に配置 (奥ほど道に寄る=遠近感)
    for band_y0, band_y1, step in ((-6, 12, 1.15), (12, 26, 1.35), (26, 38, 1.6)):
        y = band_y0
        while y < band_y1:
            for side in (-1, 1):
                shrink = max(0.4, 1.0 - 0.55 * ((y + 4) / 42))
                x_in = side * (2.2 * shrink + R.uniform(0.1, 0.7))
                n_row = 3 if y < 12 else 2
                for k in range(n_row):
                    x = x_in + side * (k * R.uniform(0.9, 1.5) + R.uniform(0, 0.5))
                    if abs(x) > 11:
                        continue
                    # 道側へ軽く傾ける + 向き・大きさをばらす
                    lean = R.uniform(0.0, math.radians(7)) * (-side)
                    scatter_copy(R.choice(tpls), f"bamboo_{idx}",
                                 (x, y + R.uniform(-0.5, 0.5), 0),
                                 rot=(0, lean, R.uniform(0, 6.28)),
                                 scale=R.uniform(0.8, 1.25))
                    idx += 1
            y += step
    print("bamboo count:", idx)
    # 中景の広葉樹の茂み (板ではなく塊で)
    for i, (x, y, s) in enumerate([(-4.5, 20, 2.2), (4.2, 18, 2.0), (-3.2, 27, 2.6),
                                   (3.6, 28, 2.4), (0.0, 36, 3.0), (-6.5, 33, 2.8),
                                   (6.4, 34, 2.6)]):
        key = R.choice(("leaf_mid", "leaf_light"))
        for k in range(4):
            sphere(f"bush_{i}_{k}", s * R.uniform(0.5, 0.8),
                   (x + R.uniform(-s, s) * 0.5, y + R.uniform(-s, s) * 0.5,
                    R.uniform(1.5, 3.5) + k * 0.6),
                   mat(key, PAL[key], rough=0.95), scale=(1, 1, 0.7))


def build_cliffs():
    """遠景のカルスト岩山: 霧に霞む縦長の岩塔."""
    cliff = mat("cliff", PAL["cliff"], rough=0.95)
    green = mat("cliff_green", PAL["cliff_green"], rough=0.95)
    defs = [
        (0, 95, 14, 34),    # 主峰 (道の正面)
        (-16, 105, 12, 26),
        (14, 110, 10, 22),
        (-30, 120, 14, 20),
        (30, 125, 16, 24),
    ]
    for i, (x, y, w, h) in enumerate(defs):
        cyl(f"cliff_{i}", w * 0.5, h, (x, y, h * 0.45), cliff, verts=9, r2=w * 0.33)
        # 頂上と中腹の緑
        sphere(f"cliffg_{i}", w * 0.42, (x, y, h * 0.95), green, scale=(1, 1, 0.5), smooth=False)
        for k in range(3):
            sphere(f"cliffg_{i}_{k}", w * R.uniform(0.15, 0.25),
                   (x + R.uniform(-w, w) * 0.35, y - w * 0.3, h * R.uniform(0.35, 0.8)),
                   green, scale=(1, 1, 0.6), smooth=False)


def build_fog_and_sky():
    """アニメ的な霧: 半透明の白い板を奥行きに重ねる (名前は fog_ 始まり)."""
    for i, (y, a) in enumerate([(30, 0.18), (45, 0.30), (62, 0.42), (80, 0.55)]):
        m = mat(f"fog{i}", PAL["fog_white"], rough=1.0, emit=0.35, alpha=a)
        plane(f"fog_{i}", 220, 60, (0, y, 25), m, rot=(math.pi / 2, 0, 0))
    set_world((0.72, 0.76, 0.74), strength=1.0)


def build_scene():
    reset_scene()
    build_ground()
    build_bamboo_groves()
    build_cliffs()
    build_fog_and_sky()
    sun_light("sun", rot=(math.radians(58), 0, math.radians(15)), energy=3.2,
              color=(1.0, 0.98, 0.92), angle_deg=12)
    cams = {
        "A": add_camera("cam_A", (0.0, -6.5, 1.3), (0.0, 20.0, 5.2), lens=24),
        "B": add_camera("cam_B", (-3.2, -2.0, 1.6), (2.5, 18.0, 3.5), lens=28),
        "T": add_camera("cam_T", (0.0, -14.0, 14.0), (0.0, 22.0, 2.0), lens=35),
    }
    return cams


if __name__ == "__main__":
    cams = build_scene()
    render_cli(cams, default_res="1280x720", exposure=0.55)
