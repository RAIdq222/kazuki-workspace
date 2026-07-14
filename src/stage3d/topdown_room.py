# -*- coding: utf-8 -*-
"""美術ボード「寝室(俯瞰)」の3Dステージ化。

ボードの構成: 明るい板張り床の私室を俯瞰。北面に朱色の飾り格子の建具(明かり取り)、
中央に白い敷物+ローテーブル(急須と碗)、右に黒漆の飾り箪笥と寝台(白い夜具)、
左に屏風・花瓶を載せた小机・衣桁(白い衣)・小さな踏み台、行灯。窓から床に光だまり。

実行例:
    python3 src/stage3d/topdown_room.py -- --views T --samples 64 \
        --res 1280x880 --blend work/topdown_room.blend
"""
import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from stagelib import (reset_scene, mat, mat_image, box, cyl, sphere, torus, plane,  # noqa: E402
                      add_camera, area_light, sun_light, set_world, render_cli)

SPR = "work/sprites"  # 原画から切り出したテクスチャ (room_textures.py で生成)


def rtex(name, **kw):
    """原画テクスチャがあれば返す (なければ None → 従来のフラット色)."""
    p = f"{SPR}/room_{name}.png"
    return mat_image(f"room_{name}", p, blend="OPAQUE", **kw) if os.path.exists(p) else None

R = random.Random(5)

ROOM_X = 7.2   # 東西 (画像の左右)
ROOM_Y = 5.6   # 南北 (北=窓側)
WALL_H = 3.1

PAL = {
    "floor_light": (0.500, 0.365, 0.190),   # 明るい床板
    "plaster":     (0.700, 0.690, 0.660),
    "skirt_gray":  (0.300, 0.300, 0.295),   # 巾木・腰の灰色
    "wood_dark":   (0.130, 0.085, 0.055),
    "red_frame":   (0.340, 0.060, 0.040),   # 朱色の建具枠
    "red_deep":    (0.220, 0.040, 0.030),
    "gold":        (0.560, 0.400, 0.150),   # 飾り金具・組子
    "black_lac":   (0.045, 0.040, 0.038),   # 黒漆の家具
    "white_cloth": (0.780, 0.760, 0.720),
    "rug_white":   (0.820, 0.800, 0.760),
    "table_wood":  (0.300, 0.185, 0.095),
    "clay":        (0.480, 0.300, 0.160),   # 急須
    "paper_warm":  (0.850, 0.780, 0.600),   # 行灯
    "vase_white":  (0.760, 0.760, 0.720),
    "shoji_glow":  (0.920, 0.900, 0.850),
}


def floor_mat():
    m = bpy.data.materials.new("m_floor")
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.45
    nt = m.node_tree
    info = nt.nodes.new("ShaderNodeObjectInfo")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    c = PAL["floor_light"]
    ramp.color_ramp.elements[0].color = (*[v * 0.82 for v in c], 1)
    ramp.color_ramp.elements[1].color = (*[v * 1.14 for v in c], 1)
    nt.links.new(info.outputs["Random"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return m


def build_room():
    ftex = rtex("floor", rough=0.42, uv_scale=(4.6, 2.1))
    if ftex:
        # 原画から切り出した床板テクスチャを1枚のプレーンに (板目はY方向)
        plane("floor", ROOM_X, ROOM_Y, (ROOM_X / 2, ROOM_Y / 2, 0), ftex)
    else:
        fm = floor_mat()
        plank_w = 0.24
        n = int(ROOM_X / plank_w) + 1
        for i in range(n):  # 床板は南北方向(画像の縦)に走る
            x = min(plank_w * i + plank_w / 2, ROOM_X - plank_w / 2)
            box(f"plank_{i}", plank_w - 0.006, ROOM_Y, 0.03, (x, ROOM_Y / 2, -0.015), fm)
    pm = mat("plaster", PAL["plaster"], rough=0.9)
    sk = mat("skirt", PAL["skirt_gray"], rough=0.85)
    # 南壁はなし (ボードと同じく手前を開けたステージセット構成)
    for nm, sx, sy, loc in [
        ("wall_W", 0.06, ROOM_Y, (-0.03, ROOM_Y / 2, 0)),
        ("wall_E", 0.06, ROOM_Y, (ROOM_X + 0.03, ROOM_Y / 2, 0)),
    ]:
        box(nm, sx, sy, WALL_H, (loc[0], loc[1], WALL_H / 2), pm)
        box(nm + "_sk", sx + 0.02, sy + 0.02, 0.55, (loc[0], loc[1], 0.275), sk)
    # 天井なし: ボードが俯瞰アングルのため上方は開放 (俯瞰カメラで部屋内が見える)


def lattice_panel(idx, cx, w, h, z0):
    """北壁の朱塗り飾り格子パネル1枚 + 上部の明かり."""
    y = ROOM_Y
    red = mat("red_frame", PAL["red_frame"], rough=0.6)
    deep = mat("red_deep", PAL["red_deep"], rough=0.7)
    gold = mat("gold", PAL["gold"], rough=0.45)
    glow = mat("shoji_glow", PAL["shoji_glow"], rough=0.9, emit=2.2)
    t = 0.06
    # 枠
    for dz, hh in ((0.03, 0.10), (h - 0.03, 0.10)):
        box(f"lp{idx}_h{dz:.2f}", w, t, hh, (cx, y - 0.05, z0 + dz), red)
    for dx in (-w / 2 + 0.045, w / 2 - 0.045):
        box(f"lp{idx}_v{dx:.2f}", 0.09, t, h, (cx + dx, y - 0.05, z0 + h / 2), red)
    # 上部 1/4: 明かり(白)
    lz = z0 + h * 0.875
    box(f"lp{idx}_glowpane", w - 0.14, 0.03, h * 0.22, (cx, y - 0.03, lz), glow)
    for k in range(3):
        box(f"lp{idx}_gbar{k}", 0.035, 0.05, h * 0.22,
            (cx - w / 4 + k * w / 4, y - 0.05, lz), red)
    ltex = rtex("lattice", rough=0.55)
    if ltex:
        # 原画から切り出した格子パネル (花飾り・彫刻帯込み) を1枚に
        mz = z0 + h * 0.375
        plane(f"lp{idx}_tex", w - 0.12, h * 0.75, (cx, y - 0.045, mz), ltex,
              rot=(math.pi / 2, 0, 0))
    else:
        # 中央: 格子 + 中心の花飾り
        mz = z0 + h * 0.42
        mh = h * 0.62
        box(f"lp{idx}_back", w - 0.14, 0.02, mh, (cx, y - 0.025, mz), deep)
        nvert = 5
        for k in range(nvert):
            dx = -w / 2 + 0.10 + k * (w - 0.2) / (nvert - 1)
            box(f"lp{idx}_gv{k}", 0.028, 0.045, mh, (cx + dx, y - 0.05, mz), gold)
        for k in range(4):
            dz = -mh / 2 + 0.06 + k * (mh - 0.12) / 3
            box(f"lp{idx}_gh{k}", w - 0.16, 0.045, 0.028, (cx, y - 0.05, mz + dz), gold)
        torus(f"lp{idx}_rose", 0.11, 0.030, (cx, y - 0.06, mz), gold,
              rot=(math.pi / 2, 0, 0))
        cyl(f"lp{idx}_rosec", 0.05, 0.03, (cx, y - 0.06, mz), gold,
            rot=(math.pi / 2, 0, 0), verts=12)
        bz = z0 + h * 0.085
        box(f"lp{idx}_band", w - 0.14, 0.04, h * 0.10, (cx, y - 0.04, bz), deep)
        for k in range(6):
            dx = -w / 2 + 0.12 + k * (w - 0.24) / 5
            box(f"lp{idx}_bd{k}", 0.09, 0.05, 0.05, (cx + dx, y - 0.045, bz), gold)


def build_north_windows():
    """北壁: 5枚の飾り格子建具 + 外光."""
    n = 5
    w = ROOM_X / n
    h = 2.55
    for i in range(n):
        cx = w / 2 + i * w
        lattice_panel(i, cx, w - 0.06, h, 0.25)
    # 建具の下の框・上の壁
    red = mat("red_frame", PAL["red_frame"], rough=0.6)
    box("north_sill", ROOM_X, 0.10, 0.25, (ROOM_X / 2, ROOM_Y - 0.05, 0.125), red)
    box("north_top", ROOM_X, 0.10, WALL_H - 2.80, (ROOM_X / 2, ROOM_Y - 0.05, 2.80 + (WALL_H - 2.80) / 2),
        mat("plaster", PAL["plaster"], rough=0.9))


def build_center():
    # 白い敷物
    box("rug", 2.7, 2.7, 0.035, (3.35, 2.55, 0.018), mat("rug_white", PAL["rug_white"], rough=1.0))
    rtex_rug = rtex("rug", rough=0.95)
    if rtex_rug:
        plane("rug_top", 2.68, 2.68, (3.35, 2.55, 0.037), rtex_rug)
    # ローテーブル
    tw = mat("table_wood", PAL["table_wood"], rough=0.5)
    wd = mat("wood_dark", PAL["wood_dark"], rough=0.6)
    box("table_top", 1.55, 0.85, 0.06, (3.35, 2.55, 0.42), tw)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(f"table_leg{sx}{sy}", 0.09, 0.09, 0.39,
                (3.35 + sx * 0.62, 2.55 + sy * 0.30, 0.195), wd)
    box("table_apron", 1.30, 0.62, 0.10, (3.35, 2.55, 0.35), wd)
    # 急須と碗
    clay = mat("clay", PAL["clay"], rough=0.55)
    sphere("teapot", 0.11, (3.15, 2.75, 0.50), clay, scale=(1, 1, 0.75))
    cyl("teapot_spout", 0.020, 0.14, (3.28, 2.79, 0.51), clay,
        rot=(0, math.radians(65), math.radians(-15)), verts=8)
    torus("teapot_handle", 0.055, 0.012, (3.05, 2.72, 0.545), clay, rot=(0, math.pi / 2, 0.4))
    cyl("teapot_lid", 0.030, 0.02, (3.15, 2.75, 0.575), clay, verts=10)
    cyl("cup", 0.045, 0.07, (3.55, 2.42, 0.485), mat("vase_white", PAL["vase_white"], rough=0.4), verts=14)


def build_east_side():
    """東側: 飾り箪笥(北東) + 寝台(南東)."""
    lac = mat("black_lac", PAL["black_lac"], rough=0.35)
    gold = mat("gold", PAL["gold"], rough=0.45)
    # 箪笥 2棹
    wtex = rtex("wardrobe", rough=0.45)
    for i, cx in enumerate((ROOM_X - 0.40, ROOM_X - 0.40)):
        cy = 4.55 - i * 1.15
        box(f"cab{i}", 0.62, 1.05, 2.35, (ROOM_X - 0.33, cy, 1.175), lac)
        if wtex:
            # 原画の飾り扉テクスチャを正面(西向き)に貼る
            plane(f"cab{i}_face", 1.0, 2.30, (ROOM_X - 0.645, cy, 1.2), wtex,
                  rot=(math.pi / 2, 0, -math.pi / 2))
        else:
            for dz in (0.35, 1.15, 1.95):
                box(f"cab{i}_tr{dz}", 0.03, 0.95, 0.03, (ROOM_X - 0.65, cy, dz), gold)
            torus(f"cab{i}_ring", 0.10, 0.02, (ROOM_X - 0.66, cy, 1.55), gold,
                  rot=(0, math.pi / 2, 0))
            for dy in (-0.35, 0.35):
                box(f"cab{i}_knob{dy}", 0.03, 0.10, 0.05, (ROOM_X - 0.65, cy + dy, 0.72), gold)
    # 寝台
    wd = mat("wood_dark", PAL["wood_dark"], rough=0.6)
    cloth = mat("white_cloth", PAL["white_cloth"], rough=0.95)
    box("bed_frame", 1.15, 2.3, 0.45, (ROOM_X - 0.60, 1.15, 0.225), wd)
    box("bed_futon", 1.10, 2.2, 0.22, (ROOM_X - 0.60, 1.15, 0.56), cloth)
    sphere("bed_fold1", 0.30, (ROOM_X - 0.62, 0.65, 0.68), cloth, scale=(1.6, 1.0, 0.45))
    sphere("bed_pillow", 0.16, (ROOM_X - 0.60, 1.95, 0.70), cloth, scale=(1.5, 1.0, 0.55))
    # ヘッドボード格子
    for k in range(5):
        box(f"bed_hb{k}", 0.05, 0.05, 0.7, (ROOM_X - 1.10 + k * 0.25, 2.28, 0.80), wd)
    box("bed_hb_top", 1.15, 0.06, 0.06, (ROOM_X - 0.60, 2.28, 1.15), wd)


def build_west_side():
    """西側: 屏風(北西の壁際) + 花瓶の小机 + 衣桁 + 踏み台 + 行灯."""
    lac = mat("black_lac", PAL["black_lac"], rough=0.4)
    gold = mat("gold", PAL["gold"], rough=0.5)
    # 屏風 4曲 (ジグザグ)
    stex = rtex("screen", rough=0.5)
    px, py = 0.28, 3.4
    for i in range(4):
        ang = math.radians(12 if i % 2 == 0 else -12)
        w = 0.72
        cy = py - i * (w * 0.97)
        xoff = 0.10 if i % 2 else 0
        box(f"screen_{i}", 0.05, w, 2.35, (px + xoff, cy, 1.175), lac, rot=(0, 0, ang))
        if stex:
            # 原画の屏風パネルを東向きの面に貼る
            plane(f"screen_tex{i}", w - 0.05, 2.28, (px + xoff + 0.03, cy, 1.175), stex,
                  rot=(math.pi / 2, 0, math.pi / 2 + ang))
        else:
            box(f"screen_g{i}", 0.02, w * 0.55, 0.5, (px + 0.05 + xoff, cy, 1.5),
                gold, rot=(0, 0, ang))
            box(f"screen_g2{i}", 0.02, w * 0.4, 0.3, (px + 0.05 + xoff, cy, 0.7),
                gold, rot=(0, 0, ang))
    # 花瓶の小机 (北西)
    tw = mat("table_wood", PAL["table_wood"], rough=0.5)
    box("side_top", 0.62, 0.62, 0.05, (0.95, 4.95, 0.62), tw)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(f"side_leg{sx}{sy}", 0.06, 0.06, 0.60,
                (0.95 + sx * 0.24, 4.95 + sy * 0.24, 0.30), tw)
    vase = mat("vase_white", PAL["vase_white"], rough=0.3)
    sphere("vase_body", 0.17, (0.95, 4.95, 0.90), vase, scale=(1, 1, 1.25))
    cyl("vase_neck", 0.055, 0.16, (0.95, 4.95, 1.13), vase, verts=14)
    torus("vase_lip", 0.075, 0.018, (0.95, 4.95, 1.21), vase)
    # 衣桁 (鳥居型) + 白衣
    wd = mat("wood_dark", PAL["wood_dark"], rough=0.6)
    cloth = mat("white_cloth", PAL["white_cloth"], rough=0.95)
    kx, ky = 1.45, 1.15
    for dy in (-0.65, 0.65):
        cyl(f"iko_post{dy}", 0.035, 1.55, (kx, ky + dy, 0.775), wd, verts=10)
        box(f"iko_foot{dy}", 0.42, 0.08, 0.06, (kx, ky + dy, 0.03), wd)
    cyl("iko_bar", 0.030, 1.65, (kx, ky, 1.52), wd, rot=(math.pi / 2, 0, 0), verts=10)
    cyl("iko_bar2", 0.022, 1.45, (kx, ky, 1.05), wd, rot=(math.pi / 2, 0, 0), verts=10)
    # 掛けた白衣: 中央の身頃 + 垂れ袖
    box("robe_body", 0.16, 0.85, 0.95, (kx, ky, 1.02), cloth, rot=(0.06, 0, 0))
    box("robe_sleeveL", 0.14, 0.30, 0.70, (kx - 0.02, ky - 0.55, 1.10), cloth, rot=(0.15, 0.1, 0))
    box("robe_sleeveR", 0.14, 0.28, 0.62, (kx + 0.02, ky + 0.53, 1.08), cloth, rot=(-0.12, -0.08, 0))
    # 踏み台
    box("stool_top", 0.42, 0.30, 0.05, (2.5, 0.85, 0.28), tw)
    for sx in (-1, 1):
        box(f"stool_leg{sx}", 0.05, 0.26, 0.26, (2.5 + sx * 0.16, 0.85, 0.13), tw)
    # 行灯 (窓際)
    paper = mat("paper_warm", PAL["paper_warm"], rough=0.8, emit=1.6)
    cyl("lamp_shade", 0.16, 0.62, (2.6, 4.55, 1.05), paper, verts=14)
    cyl("lamp_cap", 0.17, 0.03, (2.6, 4.55, 1.38), wd, verts=14)
    cyl("lamp_pole", 0.025, 0.55, (2.6, 4.55, 0.45), wd, verts=8)
    for a in range(3):
        ang = a * 2 * math.pi / 3
        box(f"lamp_leg{a}", 0.05, 0.26, 0.04,
            (2.6 + math.cos(ang) * 0.12, 4.55 + math.sin(ang) * 0.12, 0.10), wd,
            rot=(0, 0, ang))


def build_lights():
    # 北窓からの外光 (各パネル上部の明かりに面光源)
    n = 5
    w = ROOM_X / n
    for i in range(n):
        cx = w / 2 + i * w
        area_light(f"win_{i}", (cx, ROOM_Y - 0.12, 2.45),
                   (math.radians(115), 0, 0), w * 0.8, 55, (1.0, 0.96, 0.88), size_y=0.6)
    # 差し込む日光 (床の光だまり)
    sun_light("sun", rot=(math.radians(38), 0, math.radians(178)), energy=2.6,
              color=(1.0, 0.95, 0.85), angle_deg=3)
    # 全体の環境
    set_world((0.045, 0.042, 0.038), strength=1.0)
    area_light("fill", (3.6, 2.4, WALL_H - 0.2), (0, 0, 0), 3.2, 40, (1.0, 0.92, 0.80))


def build_scene():
    reset_scene()
    build_room()
    build_north_windows()
    build_center()
    build_east_side()
    build_west_side()
    build_lights()
    cams = {
        # ボード再現: 南側上方からの俯瞰
        "T": add_camera("cam_T", (3.55, -2.6, 6.8), (3.5, 3.3, 0.2), lens=34),
        # 眼高 (南西から)
        "E": add_camera("cam_E", (0.8, 0.5, 1.45), (5.8, 4.6, 1.1), lens=24),
        # 真俯瞰
        "P": add_camera("cam_P", (3.6, 2.8, 8.5), (3.6, 2.81, 0.0), lens=30),
    }
    return cams


if __name__ == "__main__":
    cams = build_scene()
    render_cli(cams, default_res="1280x880", exposure=0.8)
