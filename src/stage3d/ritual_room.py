# -*- coding: utf-8 -*-
"""美術ボード「SZ#6_復活の儀の部屋(夜)」の3Dステージ化。

原画(正面) + GPT Image 2 で生成した別アングル(逆・横)を根拠に空間化。
テクスチャは原画からの切り出し (rit_*.png)。

部屋 (単位m): X 0..5.4 (幅), Y 0..7.2 (奥行, 北=y大が祭壇壁), 壁高 3.4
実行例:
    python3 src/stage3d/ritual_room.py -- --views A --samples 32 --res 1280x800
"""
import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from stagelib import (reset_scene, mat, mat_image, box, cyl, sphere, torus, plane,  # noqa: E402
                      add_camera, area_light, set_world, render_cli)

R = random.Random(3)
SPR = "work/sprites"

ROOM_X = 5.4
ROOM_Y = 7.2
WALL_H = 3.4

PAL = {
    "wood_red":   (0.170, 0.055, 0.030),   # 赤茶の柱・梁
    "wood_dark":  (0.060, 0.030, 0.020),
    "floor_dark": (0.140, 0.060, 0.035),
    "black_lac":  (0.020, 0.018, 0.016),   # 燭台の黒木枠
    "candle_wax": (0.850, 0.780, 0.620),
    "flame":      (1.000, 0.640, 0.240),
    "cloth":      (0.780, 0.760, 0.730),
    "statue":     (0.420, 0.360, 0.240),
    "blade":      (0.550, 0.560, 0.580),
    "handle_red": (0.350, 0.060, 0.040),
}


def rtex(name, **kw):
    p = f"{SPR}/rit_{name}.png"
    return mat_image(f"rit_{name}", p, blend="OPAQUE", **kw) if os.path.exists(p) else None


def build_shell():
    # 床: 板張り (原画切り出し, 板目はY方向=奥行き)
    ftex = rtex("floor", rough=0.55, uv_scale=(3.4, 6.0))
    plane("floor", ROOM_X, ROOM_Y, (ROOM_X / 2, ROOM_Y / 2, 0),
          ftex or mat("floor_dark", PAL["floor_dark"], rough=0.6))
    # 中央の畳の通路 (入口→儀式壇)
    ttex = rtex("tatami", rough=0.8, uv_scale=(1, 3.2))
    plane("tatami", 1.5, 4.6, (ROOM_X / 2, 2.3, 0.012),
          ttex or mat("cloth", PAL["cloth"], rough=0.9))
    # 壁: 茶色い土壁 (原画切り出し)
    wtex = rtex("wall", rough=0.9, uv_scale=(3.0, 2.0))
    wm = wtex or mat("wall_brown", (0.26, 0.16, 0.08), rough=0.9)
    box("wall_N", ROOM_X, 0.06, WALL_H, (ROOM_X / 2, ROOM_Y + 0.03, WALL_H / 2), wm)
    box("wall_W", 0.06, ROOM_Y, WALL_H, (-0.03, ROOM_Y / 2, WALL_H / 2), wm)
    box("wall_E", 0.06, ROOM_Y, WALL_H, (ROOM_X + 0.03, ROOM_Y / 2, WALL_H / 2), wm)
    box("wall_S", ROOM_X, 0.06, WALL_H, (ROOM_X / 2, -0.03, WALL_H / 2), wm)
    # 南壁の両開き戸 (逆アングル生成画から切り出したテクスチャ)
    wd = mat("wood_red", PAL["wood_red"], rough=0.6)
    dtex = rtex("door", rough=0.6)
    if dtex:
        plane("door", 2.1, 2.2, (ROOM_X / 2, 0.02, 1.1), dtex,
              rot=(math.pi / 2, 0, math.pi))
    else:
        for dx in (-0.55, 0.55):
            box(f"door_{dx}", 1.05, 0.08, 2.2, (ROOM_X / 2 + dx, 0.02, 1.1),
                mat("wood_dark", PAL["wood_dark"], rough=0.65))
    box("door_frame_top", 2.4, 0.10, 0.15, (ROOM_X / 2, 0.02, 2.27), wd)
    # 柱と梁 (赤茶)
    for y in (0.06, 2.3, 4.7, ROOM_Y - 0.06):
        for x in (0.10, ROOM_X - 0.10):
            box(f"post_{x:.1f}_{y:.1f}", 0.20, 0.20, WALL_H, (x, y, WALL_H / 2), wd)
    for y in (2.3, 4.7):
        box(f"beam_{y}", ROOM_X, 0.22, 0.30, (ROOM_X / 2, y, WALL_H - 0.45), wd)
    box("beam_N", ROOM_X, 0.22, 0.30, (ROOM_X / 2, ROOM_Y - 0.15, WALL_H - 0.45), wd)
    for x in (0.10, ROOM_X - 0.10):
        box(f"girder_{x:.1f}", 0.2, ROOM_Y, 0.26, (x, ROOM_Y / 2, WALL_H - 0.43), wd)
    # 天井 (暗い板)
    plane("ceiling", ROOM_X, ROOM_Y, (ROOM_X / 2, ROOM_Y / 2, WALL_H),
          mat("wood_dark", PAL["wood_dark"], rough=0.9))
    # 側面の白幕 (原画切り出し)
    ctex = rtex("curtain", rough=0.95)
    cm = ctex or mat("cloth", PAL["cloth"], rough=0.95)
    for x, sgn in ((0.12, 1), (ROOM_X - 0.12, -1)):
        for i in range(3):
            y0 = 1.4 + i * 1.75
            plane(f"curtain_{x:.1f}_{i}", 1.7, 3.1,
                  (x + sgn * 0.02, y0 + 0.85, 1.72),
                  cm, rot=(math.pi / 2, 0, sgn * math.pi / 2))
    # 掛け軸 (北壁)
    stex = rtex("scroll", rough=0.8)
    if stex:
        plane("scroll", 0.85, 1.55, (ROOM_X / 2, ROOM_Y - 0.05, 2.15), stex,
              rot=(math.pi / 2, 0, 0))
    cyl("scroll_rod", 0.025, 1.0, (ROOM_X / 2, ROOM_Y - 0.06, 2.98),
        mat("wood_dark", PAL["wood_dark"]), rot=(math.pi / 2, 0, math.pi / 2), verts=10)


def altar(idx, cx):
    """白布の祭壇 + 短剣."""
    cloth = rtex("altar", rough=0.9) or mat("cloth", PAL["cloth"], rough=0.9)
    box(f"altar{idx}_body", 1.0, 2.0, 0.72, (cx, 4.35, 0.36),
        mat("wood_dark", PAL["wood_dark"]))
    box(f"altar{idx}_cloth", 1.08, 2.08, 0.74, (cx, 4.35, 0.38), cloth)
    # 短剣 (刀身+柄)
    box(f"altar{idx}_blade", 0.05, 0.5, 0.015, (cx, 4.1, 0.77),
        mat("blade", PAL["blade"], rough=0.25), rot=(0, 0, 0.25))
    box(f"altar{idx}_hilt", 0.045, 0.18, 0.03, (cx + 0.07, 4.38, 0.77),
        mat("handle_red", PAL["handle_red"], rough=0.5), rot=(0, 0, 0.25))


def candle(name, loc, s=1.0, lit=True):
    cyl(f"{name}_wax", 0.022 * s, 0.16 * s, (loc[0], loc[1], loc[2] + 0.08 * s),
        mat("candle_wax", PAL["candle_wax"], rough=0.6), verts=10)
    if lit:
        fl = mat("flame", PAL["flame"], rough=0.5, emit=14.0)
        sphere(f"{name}_flame", 0.016 * s, (loc[0], loc[1], loc[2] + 0.185 * s), fl,
               scale=(1, 1, 1.7))


def candle_rack(idx, cx):
    """黒木枠の燭台 (祭壇の外側)."""
    lac = mat("black_lac", PAL["black_lac"], rough=0.45)
    box(f"rack{idx}_top", 0.35, 1.9, 0.07, (cx, 4.35, 0.86), lac)
    box(f"rack{idx}_shelf", 0.35, 1.9, 0.07, (cx, 4.35, 0.45), lac)
    for dy in (-0.85, 0, 0.85):
        box(f"rack{idx}_leg{dy}", 0.3, 0.08, 0.86, (cx, 4.35 + dy, 0.43), lac)
    for i in range(5):
        candle(f"rack{idx}_c{i}", (cx, 3.55 + i * 0.4, 0.90), s=1.1)


def build_props():
    # 中央の儀式壇: 黒い台 + 陰陽紋 + 像
    lac = mat("black_lac", PAL["black_lac"], rough=0.4)
    box("dais", 1.7, 1.15, 0.10, (ROOM_X / 2, 4.35, 0.05), lac)
    yy = mat_image("rit_yinyang", f"{SPR}/rit_yinyang.png", blend="CLIP", rough=0.5)
    plane("yinyang", 0.95, 0.95, (ROOM_X / 2, 4.35, 0.105), yy)
    # 香炉像
    st = mat("statue", PAL["statue"], rough=0.7)
    sphere("statue_base", 0.14, (ROOM_X / 2, 3.62, 0.16), st, scale=(1, 1, 0.6))
    sphere("statue_body", 0.10, (ROOM_X / 2, 3.62, 0.30), st, scale=(1, 1, 1.2))
    sphere("statue_head", 0.055, (ROOM_X / 2, 3.62, 0.46), st)
    altar(0, ROOM_X / 2 - 1.35)
    altar(1, ROOM_X / 2 + 1.35)
    candle_rack(0, ROOM_X / 2 - 2.32)
    candle_rack(1, ROOM_X / 2 + 2.32)
    # 吊り燈籠 x2
    for i, cx in enumerate((ROOM_X / 2 - 1.6, ROOM_X / 2 + 1.6)):
        cyl(f"lant{i}_wire", 0.008, 0.75, (cx, 4.9, WALL_H - 0.38),
            mat("wood_dark", PAL["wood_dark"]), verts=6)
        shade = mat("lantern", (0.95, 0.75, 0.40), rough=0.7, emit=5.0)
        cyl(f"lant{i}_shade", 0.14, 0.30, (cx, 4.9, 2.42), shade, verts=14)
        cyl(f"lant{i}_cap", 0.16, 0.03, (cx, 4.9, 2.585), lac, verts=14)
        # 房飾り
        cyl(f"lant{i}_fringe", 0.15, 0.09, (cx, 4.9, 2.23),
            mat("fringe", (0.75, 0.60, 0.30), rough=0.9), verts=14)
    # 壁の燭台 (柱の上部)
    for i, (cx, sgn) in enumerate(((0.35, 1), (ROOM_X - 0.35, -1))):
        for k, y in enumerate((2.5, 3.3)):
            box(f"sconce{i}_{k}", 0.10, 0.10, 0.18, (cx, y, 2.05), lac)
            candle(f"sconce{i}_{k}c", (cx, y, 2.14), s=0.9)


def build_lights():
    set_world((0.010, 0.008, 0.007), strength=1.0)
    # 蝋燭・燈籠まわりの補助光 (emitだけだとCPUレンダでノイズが多いため)
    for i, (x, y, z, e, col) in enumerate([
        (ROOM_X / 2 - 1.6, 4.9, 2.35, 55, (1.0, 0.65, 0.28)),   # 吊り燈籠
        (ROOM_X / 2 + 1.6, 4.9, 2.35, 55, (1.0, 0.65, 0.28)),
        (ROOM_X / 2 - 2.3, 4.3, 1.35, 24, (1.0, 0.58, 0.24)),   # 燭台列
        (ROOM_X / 2 + 2.3, 4.3, 1.35, 24, (1.0, 0.58, 0.24)),
        (0.45, 2.9, 2.3, 13, (1.0, 0.58, 0.24)),                # 壁蝋燭
        (ROOM_X - 0.45, 2.9, 2.3, 13, (1.0, 0.58, 0.24)),
        (ROOM_X / 2, 3.6, 1.3, 9, (0.9, 0.62, 0.32)),           # 中央の淡い返し
        (ROOM_X / 2, 1.2, 2.6, 6, (0.55, 0.60, 0.75)),          # 入口側の冷えた微光
    ]):
        d = bpy.data.lights.new(f"pl_{i}", type="POINT")
        d.energy = e
        d.color = col
        d.shadow_soft_size = 0.25
        o = bpy.data.objects.new(f"pl_{i}", d)
        o.location = (x, y, z)
        bpy.context.collection.objects.link(o)


def build_scene():
    reset_scene()
    build_shell()
    build_props()
    build_lights()
    cams = {
        # ボード再現 (正面)
        "A": add_camera("cam_A", (ROOM_X / 2, 0.6, 1.35), (ROOM_X / 2, 6.5, 1.45), lens=30),
        # 逆アングル (祭壇側から入口へ)
        "B": add_camera("cam_B", (ROOM_X / 2, 6.4, 1.5), (ROOM_X / 2, 0.3, 1.2), lens=26),
        # 横アングル
        "C": add_camera("cam_C", (0.55, 2.6, 1.5), (ROOM_X, 4.8, 1.1), lens=24),
        # 俯瞰
        "T": add_camera("cam_T", (ROOM_X / 2, 1.2, 3.1), (ROOM_X / 2, 4.9, 0.4), lens=28),
    }
    return cams


if __name__ == "__main__":
    cams = build_scene()
    render_cli(cams, default_res="1280x800", view_transform="AgX", exposure=1.2)
