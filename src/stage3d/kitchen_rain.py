# -*- coding: utf-8 -*-
"""美術ボード「寺院内 台所 食堂(雨)」の3Dステージ化。

原画 + GPT Image 2 生成の別アングル(逆・横)を根拠に空間化。
テクスチャは原画からの切り出し (kit_*.png)。

部屋 (単位m): X 0..7.6 (東=x大 に飾り棚), Y 0..5.8 (北=y大 がかまど・窓壁), 壁高 3.0
実行例:
    python3 src/stage3d/kitchen_rain.py -- --views A --samples 32 --res 1280x800
"""
import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from stagelib import (reset_scene, mat, mat_image, box, cyl, sphere, torus, plane,  # noqa: E402
                      add_camera, area_light, sun_light, set_world, render_cli)

R = random.Random(9)
SPR = "work/sprites"

ROOM_X = 7.6
ROOM_Y = 5.8
WALL_H = 3.0
DECK_H = 0.36   # 上がり座敷の高さ

PAL = {
    "wood_dark":  (0.075, 0.055, 0.042),
    "wood_deck":  (0.180, 0.130, 0.090),
    "stone":      (0.240, 0.240, 0.235),
    "plaster":    (0.520, 0.520, 0.500),
    "stove":      (0.420, 0.440, 0.400),
    "iron_pot":   (0.045, 0.045, 0.048),
    "clay":       (0.300, 0.200, 0.120),
    "cloth_gray": (0.500, 0.490, 0.460),
    "buns":       (0.660, 0.600, 0.500),
    "leaf_green": (0.150, 0.280, 0.100),
}


def ktex(name, **kw):
    p = f"{SPR}/kit_{name}.png"
    return mat_image(f"kit_{name}", p, blend="OPAQUE", **kw) if os.path.exists(p) else None


def build_shell():
    # 土間 (石床)
    st = ktex("stone", rough=0.85, uv_scale=(4.5, 3.4))
    plane("stone_floor", ROOM_X, ROOM_Y, (ROOM_X / 2, ROOM_Y / 2, 0),
          st or mat("stone", PAL["stone"], rough=0.9))
    # 壁 (白漆喰)
    wtex = ktex("wall", rough=0.9, uv_scale=(3.2, 1.6))
    wm = wtex or mat("plaster", PAL["plaster"], rough=0.9)
    for nm, sx, sy, loc in [
        ("wall_N", ROOM_X, 0.06, (ROOM_X / 2, ROOM_Y + 0.03, 0)),
        ("wall_W", 0.06, ROOM_Y, (-0.03, ROOM_Y / 2, 0)),
        ("wall_E", 0.06, ROOM_Y, (ROOM_X + 0.03, ROOM_Y / 2, 0)),
        ("wall_S", ROOM_X, 0.06, (ROOM_X / 2, -0.03, 0)),
    ]:
        box(nm, sx, sy, WALL_H, (loc[0], loc[1], WALL_H / 2), wm)
    wd = mat("wood_dark", PAL["wood_dark"], rough=0.7)
    # 柱
    for x, y in [(0.12, 0.12), (ROOM_X - 0.12, 0.12), (0.12, ROOM_Y - 0.12),
                 (ROOM_X - 0.12, ROOM_Y - 0.12), (3.8, ROOM_Y - 0.12), (0.12, 2.9)]:
        box(f"post_{x:.1f}_{y:.1f}", 0.18, 0.18, WALL_H, (x, y, WALL_H / 2), wd)
    # 天井: 梁 + 板 (低い木天井)
    plane("ceiling", ROOM_X, ROOM_Y, (ROOM_X / 2, ROOM_Y / 2, WALL_H),
          mat("wood_deck", PAL["wood_deck"], rough=0.85))
    for i in range(6):
        y = 0.5 + i * 1.0
        box(f"cbeam_{i}", ROOM_X, 0.16, 0.20, (ROOM_X / 2, y, WALL_H - 0.10), wd)
    box("cbeam_main", 0.20, ROOM_Y, 0.26, (3.8, ROOM_Y / 2, WALL_H - 0.13), wd)
    # 雨の格子窓 (原画の窓バンドをそのまま貼る + 弱発光)
    wtex2 = mat_image("kit_window", f"{SPR}/kit_window.png", blend="OPAQUE",
                      rough=0.8, emit=0.9)
    # 北壁: かまど上の長窓
    plane("win_N", 4.6, 0.85, (2.6, ROOM_Y - 0.045, 2.05), wtex2, rot=(math.pi / 2, 0, 0))
    box("win_N_sill", 4.7, 0.08, 0.08, (2.6, ROOM_Y - 0.06, 1.58), wd)
    box("win_N_head", 4.7, 0.08, 0.08, (2.6, ROOM_Y - 0.06, 2.52), wd)
    # 東壁寄りの窓 (原画右奥)
    plane("win_E", 1.8, 0.8, (6.3, ROOM_Y - 0.045, 2.0), wtex2, rot=(math.pi / 2, 0, 0))
    # 西壁の掛け軸
    stex = ktex("scroll", rough=0.8)
    if stex:
        plane("scroll", 0.72, 1.30, (0.045, 1.6, 2.0), stex,
              rot=(math.pi / 2, 0, math.pi / 2))


def build_deck():
    """上がり座敷 (板の間) + ローテーブル + 敷物."""
    dtex = ktex("deck", rough=0.6, uv_scale=(3.2, 2.4))
    dm = dtex or mat("wood_deck", PAL["wood_deck"], rough=0.7)
    wd = mat("wood_dark", PAL["wood_dark"], rough=0.7)
    x0, x1 = 1.9, ROOM_X
    y0, y1 = 0.0, 3.1
    box("deck", x1 - x0, y1 - y0, DECK_H, ((x0 + x1) / 2, (y0 + y1) / 2, DECK_H / 2), dm)
    # 縁の框
    box("deck_edge_x", 0.10, y1 - y0, 0.10, (x0 - 0.02, (y0 + y1) / 2, DECK_H - 0.05), wd)
    box("deck_edge_y", x1 - x0, 0.10, 0.10, ((x0 + x1) / 2, y1 - 0.02, DECK_H - 0.05), wd)
    # 踏み段
    box("step", 0.9, 0.35, 0.16, (x0 - 0.25, 0.9, 0.08), wd)
    # 敷物
    box("mat", 2.0, 1.6, 0.02, (4.6, 1.7, DECK_H + 0.01),
        mat("cloth_gray", PAL["cloth_gray"], rough=0.95))
    # ローテーブル
    tm = mat("wood_deck", (0.24, 0.165, 0.105), rough=0.5)
    box("table_top", 1.35, 0.75, 0.05, (4.6, 1.7, DECK_H + 0.42), tm)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(f"table_leg{sx}{sy}", 0.07, 0.07, 0.39,
                (4.6 + sx * 0.56, 1.7 + sy * 0.28, DECK_H + 0.195), wd)
    # 卓上: 盆 + 急須 + 杯 + 小行灯
    box("tray", 0.5, 0.35, 0.03, (4.5, 1.72, DECK_H + 0.465), wd)
    clay = mat("clay", PAL["clay"], rough=0.5)
    sphere("teapot", 0.085, (4.42, 1.74, DECK_H + 0.53), clay, scale=(1, 1, 0.75))
    cyl("teapot_spout", 0.015, 0.1, (4.52, 1.77, DECK_H + 0.54), clay,
        rot=(0, math.radians(60), 0), verts=8)
    for dy in (-0.08, 0.06):
        cyl(f"cup{dy}", 0.03, 0.04, (4.62, 1.72 + dy, DECK_H + 0.50),
            mat("cloth_gray", PAL["cloth_gray"], rough=0.4), verts=10)
    # 小さな行灯 (金属の火屋)
    cyl("lamp_body", 0.05, 0.16, (4.86, 1.78, DECK_H + 0.55),
        mat("iron_pot", PAL["iron_pot"], rough=0.4), verts=10)
    cyl("lamp_top", 0.02, 0.07, (4.86, 1.78, DECK_H + 0.66),
        mat("iron_pot", PAL["iron_pot"], rough=0.4), verts=8, r2=0.001)
    # 円座 x2
    for x, y in ((3.6, 1.5), (5.4, 2.4)):
        cyl(f"zabuton_{x:.0f}", 0.24, 0.035, (x, y, DECK_H + 0.02),
            mat("cloth_gray", (0.55, 0.54, 0.50), rough=0.95), verts=20)


def build_stoves():
    """かまど列 (北壁沿い・土間側)."""
    stex = ktex("stove", rough=0.85, uv_scale=(2.5, 1.2))
    sm = stex or mat("stove", PAL["stove"], rough=0.9)
    iron = mat("iron_pot", PAL["iron_pot"], rough=0.35)
    wd = mat("wood_dark", PAL["wood_dark"], rough=0.7)
    y0 = ROOM_Y - 0.85
    # 3段構成: 低い作業台 - かまど本体(高) - 低い台
    box("bench_w", 1.5, 0.75, 0.72, (0.9, y0 + 0.375, 0.36), sm)
    box("stove_main", 2.2, 0.85, 0.80, (2.75, y0 + 0.35, 0.40), sm)
    box("bench_e", 1.3, 0.70, 0.68, (4.6, y0 + 0.40, 0.34), sm)
    # 焚口 (アーチ)
    for i, cx in enumerate((2.35, 3.15)):
        box(f"taki_sq_{i}", 0.34, 0.03, 0.26, (cx, y0 - 0.075, 0.20), iron)
        cyl(f"taki_arc_{i}", 0.17, 0.03, (cx, y0 - 0.075, 0.33), iron,
            rot=(math.pi / 2, 0, 0), verts=20)
    # 大釜 x2 (黒い鉄鍋 + 蓋)
    for i, (cx, s) in enumerate(((2.45, 1.0), (3.25, 0.85))):
        sphere(f"pot{i}", 0.30 * s, (cx, y0 + 0.35, 0.80 + 0.14 * s), iron,
               scale=(1, 1, 0.75))
        cyl(f"pot{i}_lid", 0.26 * s, 0.05, (cx, y0 + 0.35, 0.80 + 0.30 * s), wd, verts=16)
        sphere(f"pot{i}_knob", 0.035, (cx, y0 + 0.35, 0.80 + 0.34 * s), wd)
    # 作業台上の小物: 鉢・まな板・箸立て
    clay = mat("clay", PAL["clay"], rough=0.6)
    cyl("bowl1", 0.11, 0.10, (0.55, y0 + 0.35, 0.77), clay, verts=14)
    cyl("bowl2", 0.09, 0.08, (0.85, y0 + 0.30, 0.76), clay, verts=14)
    box("manaita", 0.38, 0.22, 0.03, (1.25, y0 + 0.35, 0.745), mat("wood_deck", PAL["wood_deck"]))
    cyl("hashitate", 0.045, 0.14, (0.42, y0 + 0.30, 0.79), wd, verts=10)
    # 薪の束 (かまど脇)
    for k in range(4):
        cyl(f"wood_{k}", 0.035, 0.55, (4.05 + 0.05 * (k % 2), y0 + 0.1, 0.06 + 0.07 * (k // 2)),
            mat("clay", (0.22, 0.15, 0.09), rough=0.8), rot=(0, math.pi / 2, 0.1 * k), verts=8)
    # 竹籠 (芋)
    cyl("basket", 0.2, 0.18, (5.5, y0 + 0.3, 0.09), mat("buns", (0.42, 0.32, 0.16), rough=0.9), verts=16)
    for i in range(4):
        a = i * 1.7
        sphere(f"imo_{i}", 0.06, (5.5 + math.cos(a) * 0.09, y0 + 0.3 + math.sin(a) * 0.09, 0.20),
               mat("clay", PAL["clay"], rough=0.7))
    # 壁の編笠
    cyl("kasa", 0.17, 0.06, (5.15, ROOM_Y - 0.06, 2.15),
        mat("buns", (0.45, 0.36, 0.20), rough=0.9), rot=(math.pi / 2, 0, 0), verts=16, r2=0.02)


def build_east():
    """東壁: 飾り棚 (原画テクスチャの張りぼて) + 蒸し饅頭の小机."""
    ctex = ktex("cabinet", rough=0.6)
    wd = mat("wood_dark", PAL["wood_dark"], rough=0.7)
    if ctex:
        box("cab_body", 0.45, 1.55, 2.62, (ROOM_X - 0.24, 3.95, DECK_H + 1.31), wd)
        plane("cab_face", 1.5, 2.58, (ROOM_X - 0.475, 3.95, DECK_H + 1.31), ctex,
              rot=(math.pi / 2, 0, -math.pi / 2))
    # 蒸し饅頭の小机 (南西の土間)
    tm = mat("wood_deck", PAL["wood_deck"], rough=0.6)
    box("side_top", 0.95, 0.55, 0.05, (0.85, 2.10, 0.66), tm)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(f"side_leg{sx}{sy}", 0.06, 0.06, 0.63,
                (0.85 + sx * 0.4, 2.10 + sy * 0.21, 0.315), wd)
    bm = mat("buns", PAL["buns"], rough=0.8)
    cyl("plate", 0.16, 0.03, (0.75, 2.07, 0.70), mat("cloth_gray", (0.6, 0.58, 0.54), rough=0.5), verts=18)
    for i in range(5):
        a = i * 2 * math.pi / 5
        sphere(f"bun_{i}", 0.05, (0.75 + math.cos(a) * 0.08, 2.07 + math.sin(a) * 0.08, 0.735), bm)
    sphere("bun_c", 0.05, (0.75, 2.07, 0.78), bm)
    # 竹の花瓶
    cyl("vase", 0.045, 0.24, (1.08, 2.28, 0.78), mat("cloth_gray", (0.62, 0.62, 0.58), rough=0.5), verts=12)
    for i in range(3):
        box(f"leafb_{i}", 0.012, 0.07, 0.26, (1.08 + 0.02 * i, 2.28, 0.98 + 0.04 * i),
            mat("leaf_green", PAL["leaf_green"], rough=0.8), rot=(0.25 * i - 0.25, 0.15, 0.5 * i))
    # 巻物 (机上)
    cyl("makimono", 0.045, 0.5, (1.15, 1.95, 0.71), mat("cloth_gray", (0.66, 0.63, 0.56), rough=0.7),
        rot=(0, math.pi / 2, 0.3), verts=12)


def build_lights():
    set_world((0.16, 0.17, 0.185), strength=1.0)  # 雨の日の冷えた環境光
    # 窓からの雨天光 (青灰色)
    for i, (x, w) in enumerate([(1.4, 2.0), (3.6, 2.0), (6.3, 1.6)]):
        area_light(f"win_l{i}", (x, ROOM_Y - 0.2, 2.05), (math.radians(105), 0, 0),
                   w, 115, (0.72, 0.78, 0.88), size_y=0.8)
    # 全体の淡いフィル
    area_light("fill", (3.8, 2.6, WALL_H - 0.15), (0, 0, 0), 3.5, 75, (0.80, 0.82, 0.86))


def build_scene():
    reset_scene()
    build_shell()
    build_deck()
    build_stoves()
    build_east()
    build_lights()
    cams = {
        # ボード再現 (南西から北東へ)
        "A": add_camera("cam_A", (0.7, 0.55, 1.5), (6.2, 4.4, 0.9), lens=22),
        # 逆アングル (飾り棚側から)
        "B": add_camera("cam_B", (6.9, 3.6, 1.5), (0.6, 0.8, 0.9), lens=22),
        # 横 (西壁からかまど列に沿って)
        "C": add_camera("cam_C", (0.6, 3.4, 1.4), (7.2, 2.6, 0.9), lens=24),
        # 俯瞰
        "T": add_camera("cam_T", (1.2, -1.5, 4.6), (4.8, 3.6, 0.3), lens=30),
    }
    return cams


if __name__ == "__main__":
    cams = build_scene()
    render_cli(cams, default_res="1280x800", view_transform="AgX", exposure=0.95)
