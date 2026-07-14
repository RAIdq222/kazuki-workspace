# -*- coding: utf-8 -*-
"""尚善 美術ボード「SZ#1_台所_清書」を元にした Blender 3Dステージ自動構築スクリプト。

美術ボード(2アングル彩色画)から読み取った部屋を bpy でプロシージャルに組み立て、
ボードと同じ2カメラ(かまど側 / 入口側)でレンダリングする。

実行例 (bpy モジュール版 Blender):
    python3 src/stage3d/kitchen_stage.py --views A,B --samples 64 \
        --res 1280x830 --out work/renders --blend work/kitchen_stage.blend

部屋のレイアウト (単位: m):
    X: 0..6.4 (東西. 東=x大 が入口壁)   Y: 0..4.4 (南北. 北=y大 が かまど壁)
    壁高 2.55 / 切妻天井 棟高 3.25 (棟はX方向)
"""
import argparse
import math
import random
import sys

import bpy

R = random.Random(7)

ROOM_X = 6.4
ROOM_Y = 4.4
WALL_H = 2.55
RIDGE_H = 3.25

# ---------------------------------------------------------------- palette
PAL = {
    "wood_dark":   (0.105, 0.070, 0.045),   # 柱・梁・框
    "wood_mid":    (0.190, 0.120, 0.070),   # 床・棚
    "wood_light":  (0.420, 0.300, 0.160),   # 机の天板など明るい木
    "plaster":     (0.560, 0.535, 0.480),   # 壁の漆喰パネル
    "plaster_dim": (0.430, 0.410, 0.370),   # 腰壁の漆喰(やや暗)
    "kamado":      (0.680, 0.660, 0.590),   # かまどの白漆喰
    "ceramic":     (0.042, 0.034, 0.028),   # 黒褐色の瓶
    "ceramic_hi":  (0.090, 0.070, 0.055),   # やや明るい瓶
    "iron":        (0.020, 0.020, 0.022),   # 釜口・黒
    "straw":       (0.290, 0.205, 0.085),   # 俵・籠
    "log_bark":    (0.200, 0.130, 0.075),   # 薪
    "paper":       (0.780, 0.740, 0.660),   # 障子紙
    "veg_orange":  (0.520, 0.180, 0.050),
    "veg_green":   (0.150, 0.300, 0.080),
}

_mats = {}


def mat(key, rough=0.65, emit=0.0, color=None):
    name = f"m_{key}_{emit}"
    if name in _mats:
        return _mats[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    c = color or PAL[key]
    bsdf.inputs["Base Color"].default_value = (*c, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    if emit > 0:
        bsdf.inputs["Emission Color"].default_value = (*c, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emit
    _mats[name] = m
    return m


def floor_mat():
    """床板: オブジェクトごとに明度を少し揺らす."""
    if "m_floor" in _mats:
        return _mats["m_floor"]
    m = bpy.data.materials.new("m_floor")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.62
    info = nt.nodes.new("ShaderNodeObjectInfo")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*[v * 0.75 for v in PAL["wood_mid"]], 1)
    ramp.color_ramp.elements[1].color = (*[v * 1.20 for v in PAL["wood_mid"]], 1)
    nt.links.new(info.outputs["Random"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _mats["m_floor"] = m
    return m


# ---------------------------------------------------------------- primitives
def _obj(o, name, material):
    o.name = name
    if material:
        o.data.materials.append(material)
    return o


def box(name, sx, sy, sz, loc, material, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.object
    o.scale = (sx, sy, sz)  # size=1 の立方体は一辺1 → scaleがそのまま寸法になる
    return _obj(o, name, material)


def cyl(name, r, depth, loc, material, rot=(0, 0, 0), verts=24):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, vertices=verts,
                                        location=loc, rotation=rot)
    return _obj(bpy.context.object, name, material)


def sphere(name, r, loc, material, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc,
                                         segments=24, ring_count=16)
    o = bpy.context.object
    o.scale = scale
    bpy.ops.object.shade_smooth()
    return _obj(o, name, material)


def torus(name, r, r_minor, loc, material, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=r, minor_radius=r_minor,
                                     location=loc, rotation=rot)
    bpy.ops.object.shade_smooth()
    return _obj(bpy.context.object, name, material)


# ---------------------------------------------------------------- room shell
def build_floor():
    plank_w = 0.275
    n = int(ROOM_Y / plank_w) + 1
    fm = floor_mat()
    for i in range(n):
        y = min(plank_w * i + plank_w / 2, ROOM_Y - plank_w / 2)
        box(f"floor_plank_{i}", ROOM_X, plank_w - 0.008, 0.03,
            (ROOM_X / 2, y, -0.015), fm)


def wall_frame(name, length, origin, axis, inward):
    """柱・貫(ぬき)・土台・桁 の軸組を1枚の壁に沿って作る.

    axis: 'x' or 'y'  … 壁の走る方向
    origin: 壁の始点 (x, y)
    inward: 壁面から室内側への法線符号 (+1/-1)
    """
    wd = mat("wood_dark")
    t = 0.13          # 柱の見付け
    proud = 0.045     # 漆喰面からの出
    rails_z = [(0.075, 0.15), (1.30, 0.10), (1.90, 0.10), (WALL_H - 0.06, 0.12)]

    def place(px_along, pz, sx_along, sz, depth=t):
        along = origin[0] + px_along if axis == "x" else origin[1] + px_along
        off = inward * proud
        if axis == "x":
            box(f"{name}_f{px_along:.2f}_{pz:.2f}", sx_along, depth, sz,
                (along + (0 if sx_along == length else 0), origin[1] + off, pz), wd)
        else:
            box(f"{name}_f{px_along:.2f}_{pz:.2f}", depth, sx_along, sz,
                (origin[0] + off, along, pz), wd)

    # 柱 (両端 + 等間隔)
    n_span = max(1, round(length / 1.6))
    for i in range(n_span + 1):
        p = min(max(i * length / n_span, t / 2), length - t / 2)
        if axis == "x":
            box(f"{name}_post_{i}", t, t, WALL_H,
                (origin[0] + p, origin[1] + inward * proud, WALL_H / 2), wd)
        else:
            box(f"{name}_post_{i}", t, t, WALL_H,
                (origin[0] + inward * proud, origin[1] + p, WALL_H / 2), wd)
    # 横材
    for z, h in rails_z:
        if axis == "x":
            box(f"{name}_rail_{z}", length, t * 0.8, h,
                (origin[0] + length / 2, origin[1] + inward * proud * 0.8, z), wd)
        else:
            box(f"{name}_rail_{z}", t * 0.8, length, h,
                (origin[0] + inward * proud * 0.8, origin[1] + length / 2, z), wd)


def build_walls():
    pm = mat("plaster", rough=0.9)
    pm_low = mat("plaster_dim", rough=0.9)
    # 漆喰面 (腰から下をやや暗く塗り分け)
    for nm, sx, sy, loc in [
        ("wall_N", ROOM_X, 0.04, (ROOM_X / 2, ROOM_Y + 0.02, 0)),
        ("wall_S", ROOM_X, 0.04, (ROOM_X / 2, -0.02, 0)),
        ("wall_W", 0.04, ROOM_Y, (-0.02, ROOM_Y / 2, 0)),
        ("wall_E", 0.04, ROOM_Y, (ROOM_X + 0.02, ROOM_Y / 2, 0)),
    ]:
        box(nm + "_up", sx, sy, WALL_H - 1.30, (loc[0], loc[1], 1.30 + (WALL_H - 1.30) / 2), pm)
        box(nm + "_low", sx, sy, 1.30, (loc[0], loc[1], 0.65), pm_low)
        # 妻壁 (東西のみ、壁上〜棟)
        if nm in ("wall_W", "wall_E"):
            box(nm + "_gable", sx, ROOM_Y, RIDGE_H - WALL_H,
                (loc[0], loc[1], WALL_H + (RIDGE_H - WALL_H) / 2), pm)
    wall_frame("fr_N", ROOM_X, (0, ROOM_Y), "x", -1)
    wall_frame("fr_S", ROOM_X, (0, 0), "x", +1)
    wall_frame("fr_W", ROOM_Y, (0, 0), "y", +1)
    wall_frame("fr_E", ROOM_Y, (ROOM_X, 0), "y", -1)


def build_ceiling():
    wd = mat("wood_dark")
    wm = mat("wood_mid", rough=0.7)
    half = ROOM_Y / 2
    slope = math.atan2(RIDGE_H - WALL_H, half)
    slope_len = math.hypot(half, RIDGE_H - WALL_H) + 0.15
    for sgn, nm in [(+1, "roof_S"), (-1, "roof_N")]:
        # 屋根裏の面
        yc = half - sgn * half / 2
        box(nm, ROOM_X + 0.3, slope_len, 0.045,
            (ROOM_X / 2, yc, (WALL_H + RIDGE_H) / 2 + 0.05), wm,
            rot=(sgn * slope, 0, 0))
    # 垂木
    n = int(ROOM_X / 0.55)
    for i in range(n + 1):
        x = 0.15 + i * (ROOM_X - 0.3) / n
        for sgn in (+1, -1):
            yc = half - sgn * half / 2
            box(f"rafter_{i}_{sgn}", 0.09, slope_len - 0.1, 0.15,
                (x, yc, (WALL_H + RIDGE_H) / 2 - 0.06), wd,
                rot=(sgn * slope, 0, 0))
    # 棟木・母屋
    box("ridge_beam", ROOM_X + 0.2, 0.16, 0.20, (ROOM_X / 2, half, RIDGE_H - 0.16), wd)
    for y in (half / 2, ROOM_Y - half / 2):
        box(f"purlin_{y:.1f}", ROOM_X + 0.2, 0.13, 0.15,
            (ROOM_X / 2, y, WALL_H + (RIDGE_H - WALL_H) / 2 - 0.14), wd)
    # 太い梁 (Y方向に渡す)
    for x in (2.15, 4.35):
        box(f"tie_beam_{x}", 0.18, ROOM_Y, 0.24, (x, ROOM_Y / 2, WALL_H - 0.10), wd)


def slat_window(name, wall, center, width=1.5, z0=1.30, z1=1.90):
    """格子窓: 枠 + 縦格子 + 背後の明かり面 + 外の面光源.

    wall: 'N','S','W','E'
    center: 壁に沿った中心位置
    """
    wd = mat("wood_dark")
    glow = mat("paper", rough=0.9, emit=3.0)
    h = z1 - z0
    zc = (z0 + z1) / 2
    n_slat = int(width / 0.105)

    def put(sx_along, sz, off_along, off_normal, material, name2):
        if wall in ("N", "S"):
            y = ROOM_Y if wall == "N" else 0
            sgn = -1 if wall == "N" else 1
            box(name2, sx_along, 0.045, sz,
                (center + off_along, y + sgn * off_normal, zc + 0), material)
        else:
            x = 0 if wall == "W" else ROOM_X
            sgn = 1 if wall == "W" else -1
            box(name2, 0.045, sx_along, sz,
                (x + sgn * off_normal, center + off_along, zc), material)

    # 枠 (上下)
    for dz, hh in [(-h / 2 - 0.04, 0.08), (h / 2 + 0.04, 0.08)]:
        if wall in ("N", "S"):
            y = ROOM_Y if wall == "N" else 0
            sgn = -1 if wall == "N" else 1
            box(f"{name}_frame{dz:.2f}", width + 0.16, 0.07, hh,
                (center, y + sgn * 0.05, zc + dz), wd)
        else:
            x = 0 if wall == "W" else ROOM_X
            sgn = 1 if wall == "W" else -1
            box(f"{name}_frame{dz:.2f}", 0.07, width + 0.16, hh,
                (x + sgn * 0.05, center, zc + dz), wd)
    # 縦格子
    for i in range(n_slat + 1):
        a = -width / 2 + i * width / n_slat
        put(0.045, h, a, 0.06, wd, f"{name}_slat_{i}")
    # 明かり面 (外側)
    if wall in ("N", "S"):
        y = ROOM_Y if wall == "N" else 0
        sgn = -1 if wall == "N" else 1
        box(f"{name}_glow", width + 0.05, 0.02, h + 0.05, (center, y - sgn * 0.10, zc), glow)
        ldata = bpy.data.lights.new(f"{name}_light", type="AREA")
        ldata.energy = 90; ldata.color = (1.0, 0.95, 0.86)
        ldata.shape = "RECTANGLE"; ldata.size = width; ldata.size_y = h
        lo = bpy.data.objects.new(f"{name}_light", ldata)
        lo.location = (center, y - sgn * 0.08, zc)
        lo.rotation_euler = (sgn * math.pi / 2, 0, 0) if wall == "N" else (-math.pi / 2, 0, 0)
        # 北壁: 光は -Y へ … rotation で室内へ向ける
        lo.rotation_euler = (math.radians(90) * (1 if wall == "N" else -1), 0, 0)
        bpy.context.collection.objects.link(lo)
    else:
        x = 0 if wall == "W" else ROOM_X
        sgn = 1 if wall == "W" else -1
        box(f"{name}_glow", 0.02, width + 0.05, h + 0.05, (x - sgn * 0.10, center, zc), glow)
        ldata = bpy.data.lights.new(f"{name}_light", type="AREA")
        ldata.energy = 90; ldata.color = (1.0, 0.95, 0.86)
        ldata.shape = "RECTANGLE"; ldata.size = width; ldata.size_y = h
        lo = bpy.data.objects.new(f"{name}_light", ldata)
        lo.location = (x - sgn * 0.08, center, zc)
        lo.rotation_euler = (0, math.radians(90) * sgn, 0)
        bpy.context.collection.objects.link(lo)


# ---------------------------------------------------------------- props
def build_kamado():
    """かまど: 白漆喰の竈. 天板に釜口2つ、正面に焚口2つ."""
    km = mat("kamado", rough=0.85)
    iron = mat("iron", rough=0.4)
    wd = mat("wood_mid", rough=0.7)
    cx, w, d = 2.1, 2.3, 0.85
    y0 = ROOM_Y - d - 0.05
    body_h = 0.60
    box("kamado_body", w, d, body_h, (cx, y0 + d / 2, body_h / 2), km)
    box("kamado_top", w + 0.14, d + 0.12, 0.10, (cx, y0 + d / 2, body_h + 0.05), km)
    for i, dx in enumerate((-0.55, 0.55)):
        # 釜口 (黒い開口 + 縁)
        cyl(f"kama_rim_{i}", 0.26, 0.05, (cx + dx, y0 + d / 2, body_h + 0.11), iron)
        cyl(f"kama_hole_{i}", 0.22, 0.03, (cx + dx, y0 + d / 2, body_h + 0.13), iron)
        # 焚口 (正面の黒いアーチ)
        box(f"taki_sq_{i}", 0.36, 0.03, 0.24, (cx + dx, y0 - 0.005, 0.17), iron)
        cyl(f"taki_arc_{i}", 0.18, 0.03, (cx + dx, y0 - 0.005, 0.29), iron,
            rot=(math.pi / 2, 0, 0), verts=24)
        # 焚口の薪
        for k in range(2):
            cyl(f"taki_log_{i}_{k}", 0.035, 0.5,
                (cx + dx - 0.05 + 0.09 * k, y0 + 0.1, 0.06),
                mat("log_bark"), rot=(math.pi / 2, 0.15 * k, 0), verts=12)
    # まな板 (かまど右に立てかけ)
    for k in range(2):
        box(f"manaita_{k}", 0.26, 0.035, 0.55,
            (cx + w / 2 + 0.25 + 0.06 * k, ROOM_Y - 0.13 - 0.05 * k, 0.265), wd,
            rot=(-0.20, 0, 0.06 * k))


def build_shelf_above_kamado():
    wd = mat("wood_dark")
    wm = mat("wood_light", rough=0.6)
    z = 1.66
    box("shelf_board", 1.5, 0.24, 0.04, (2.1, ROOM_Y - 0.16, z), wm)
    for dx in (-0.6, 0.6):
        box(f"shelf_brk_{dx}", 0.05, 0.2, 0.18, (2.1 + dx, ROOM_Y - 0.14, z - 0.10), wd)
    # 小物: 瓶・徳利・鉢
    items = [(-0.55, 0.06, 0.20, "ceramic_hi"), (-0.35, 0.05, 0.16, "ceramic"),
             (-0.12, 0.07, 0.13, "ceramic"), (0.18, 0.09, 0.10, "ceramic_hi"),
             (0.45, 0.06, 0.18, "ceramic")]
    for i, (dx, r, h, key) in enumerate(items):
        cyl(f"shelf_item_{i}", r, h, (2.1 + dx, ROOM_Y - 0.16, z + 0.02 + h / 2),
            mat(key, rough=0.45), verts=16)
    # 吊るした杓子
    box("ladle_handle", 0.02, 0.02, 0.30, (2.95, ROOM_Y - 0.10, 1.45), wm)
    sphere("ladle_cup", 0.05, (2.95, ROOM_Y - 0.10, 1.30), wm, scale=(1, 1, 0.6))


def jar(name, r, h, loc, key="ceramic"):
    """壺: 胴 + 口."""
    m = mat(key, rough=0.38)
    sphere(f"{name}_body", r, (loc[0], loc[1], h * 0.45), m, scale=(1, 1, h / (2 * r) * 1.1))
    cyl(f"{name}_neck", r * 0.45, h * 0.18, (loc[0], loc[1], h * 0.92), m, verts=20)
    torus(f"{name}_lip", r * 0.45, r * 0.09, (loc[0], loc[1], h * 1.0), m)


def build_west_side():
    # 大瓶 x2 (北西角)
    jar("jar_big1", 0.30, 0.80, (0.48, 3.95))
    jar("jar_big2", 0.28, 0.74, (0.52, 3.30), key="ceramic_hi")
    # 薪の山
    logm = mat("log_bark", rough=0.8)
    y0, rows = 2.05, [5, 4, 3, 2]
    for row, cnt in enumerate(rows):
        for i in range(cnt):
            y = y0 + 0.30 + row * 0.065 * 0 + i * 0.14 + row * 0.07
            cyl(f"wlog_{row}_{i}", 0.062, 0.72,
                (0.42, y0 + 0.10 + i * 0.135 + row * 0.068, 0.065 + row * 0.115),
                logm, rot=(0, math.pi / 2, 0), verts=12)


def build_entrance_wall():
    """東壁: 格子戸(両開き) + 脇の収納棚."""
    wd = mat("wood_dark")
    paper = mat("paper", rough=0.85, emit=1.2)
    door_c, door_w, door_h = 2.55, 1.7, 2.0
    x = ROOM_X
    # 戸の枠
    box("door_lintel", 0.10, door_w + 0.3, 0.12, (x - 0.05, door_c, door_h + 0.06), wd)
    for dy in (-door_w / 2 - 0.08, door_w / 2 + 0.08):
        box(f"door_jamb_{dy:.2f}", 0.10, 0.10, door_h + 0.1,
            (x - 0.05, door_c + dy, (door_h + 0.1) / 2), wd)
    # 2枚の格子戸
    for s, dy in ((0, -door_w / 4), (1, door_w / 4)):
        pc = door_c + dy
        pw = door_w / 2 - 0.02
        box(f"door_paper_{s}", 0.02, pw - 0.06, door_h - 0.08, (x - 0.03, pc, door_h / 2), paper)
        for e_dy in (-pw / 2 + 0.035, pw / 2 - 0.035):
            box(f"door_stile_{s}_{e_dy:.2f}", 0.05, 0.07, door_h, (x - 0.06, pc + e_dy, door_h / 2), wd)
        for zz in (0.05, 0.65, 1.35, door_h - 0.05):
            box(f"door_rail_{s}_{zz}", 0.05, pw, 0.09, (x - 0.06, pc, zz), wd)
        nv = 7
        for i in range(nv):
            yy = pc - pw / 2 + 0.07 + i * (pw - 0.14) / (nv - 1)
            box(f"door_bar_{s}_{i}", 0.03, 0.035, 1.35 - 0.65, (x - 0.055, yy, 1.0), wd)
        # 縦格子は上段のみ、下段は板
        box(f"door_panel_{s}", 0.035, pw, 0.60, (x - 0.055, pc, 0.35), mat("wood_mid"))
    # 収納棚 (戸の南脇)
    rack_c, rack_w, rack_d, rack_h = 1.0, 1.15, 0.42, 1.65
    for dy in (-rack_w / 2, rack_w / 2):
        for dx in (-rack_d + 0.04, -0.04):
            box(f"rack_post_{dy:.2f}_{dx:.2f}", 0.06, 0.06, rack_h,
                (x + dx, rack_c + dy, rack_h / 2), wd)
    shelf_zs = (0.28, 0.80, 1.32)
    wm = mat("wood_mid", rough=0.7)
    for z in shelf_zs:
        box(f"rack_shelf_{z}", rack_d, rack_w + 0.06, 0.045, (x - rack_d / 2, rack_c, z), wm)
    # 棚の中身
    jar("rack_jar1", 0.13, 0.34, (x - rack_d / 2, rack_c - 0.30), key="ceramic")
    jar("rack_jar2", 0.11, 0.30, (x - rack_d / 2, rack_c + 0.02), key="ceramic_hi")
    basket_with_veg("rack_basket1", (x - rack_d / 2, rack_c + 0.05, 0.80 + 0.025), 0.16, "veg_orange")
    basket_with_veg("rack_basket2", (x - rack_d / 2, rack_c - 0.28, 0.80 + 0.025), 0.15, "veg_green")
    cyl("rack_bowls", 0.11, 0.14, (x - rack_d / 2, rack_c + 0.32, 1.32 + 0.09),
        mat("ceramic_hi", rough=0.4), verts=20)


def basket_with_veg(name, loc, r, veg_key):
    bm = mat("straw", rough=0.9)
    cyl(f"{name}_body", r, r * 0.75, (loc[0], loc[1], loc[2] + r * 0.375), bm, verts=20)
    cyl(f"{name}_in", r * 0.88, r * 0.1, (loc[0], loc[1], loc[2] + r * 0.72), mat("iron"), verts=20)
    for i in range(5):
        a = i * 2 * math.pi / 5
        sphere(f"{name}_veg_{i}", r * 0.30,
               (loc[0] + math.cos(a) * r * 0.45, loc[1] + math.sin(a) * r * 0.45,
                loc[2] + r * 0.78), mat(veg_key, rough=0.55))


def table(name, cx, cy, w, d, h, top_key="wood_light", sturdy=True):
    tm = mat(top_key, rough=0.55)
    wd = mat("wood_dark")
    box(f"{name}_top", w, d, 0.05, (cx, cy, h - 0.025), tm)
    leg_in = 0.09
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(f"{name}_leg_{sx}_{sy}", 0.07, 0.07, h - 0.05,
                (cx + sx * (w / 2 - leg_in), cy + sy * (d / 2 - leg_in), (h - 0.05) / 2), wd)
    if sturdy:
        box(f"{name}_apron1", w - 0.16, 0.05, 0.09, (cx, cy - d / 2 + leg_in, h - 0.11), wd)
        box(f"{name}_apron2", w - 0.16, 0.05, 0.09, (cx, cy + d / 2 - leg_in, h - 0.11), wd)
        box(f"{name}_stretch", w - 0.16, 0.05, 0.05, (cx, cy, 0.16), wd)


def build_tables_and_misc():
    # 作業机 (かまど側ビューの右) + 籠
    table("worktable", 5.15, 3.55, 1.05, 0.72, 0.82)
    basket_with_veg("wt_basket", (5.15, 3.55, 0.82), 0.17, "veg_orange")
    # 長机 (南壁沿い)
    table("bench", 2.3, 0.55, 2.2, 0.5, 0.78)
    basket_with_veg("bench_basket", (1.8, 0.55, 0.78), 0.15, "veg_orange")
    # 俵 (かまど右)
    sm = mat("straw", rough=1.0)
    cyl("tawara", 0.21, 0.62, (3.65, ROOM_Y - 0.35, 0.21), sm, rot=(0, math.pi / 2, 0), verts=36)
    for dx in (-0.18, 0.18):
        torus("tawara_rope" + str(dx), 0.215, 0.012, (3.65 + dx, ROOM_Y - 0.35, 0.21),
              mat("wood_dark"), rot=(0, math.pi / 2, 0))
    # 予備の瓶 (東壁の戸の北脇, 入口ビューの背景用)
    jar("jar_e1", 0.24, 0.62, (ROOM_X - 0.45, 3.55))
    jar("jar_e2", 0.19, 0.50, (ROOM_X - 0.42, 3.05), key="ceramic_hi")
    jar("jar_e3", 0.17, 0.44, (ROOM_X - 0.40, 2.65), key="ceramic")


# ---------------------------------------------------------------- lights & cams
def build_lights():
    # 天井下の淡い環境光 (全体を持ち上げる)
    for x, e in ((1.8, 36), (4.6, 36)):
        d = bpy.data.lights.new(f"fill_{x}", type="AREA")
        d.energy = e; d.color = (1.0, 0.88, 0.72); d.size = 2.6
        o = bpy.data.objects.new(f"fill_{x}", d)
        o.location = (x, ROOM_Y / 2, WALL_H - 0.25)
        bpy.context.collection.objects.link(o)
    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.020, 0.017, 0.014, 1)
    bg.inputs["Strength"].default_value = 1.0


def add_camera(name, loc, look_at, lens=24):
    cam = bpy.data.cameras.new(name)
    cam.lens = lens
    o = bpy.data.objects.new(name, cam)
    o.location = loc
    d = (look_at[0] - loc[0], look_at[1] - loc[1], look_at[2] - loc[2])
    rot_z = math.atan2(d[1], d[0]) - math.pi / 2
    rot_x = math.atan2(math.hypot(d[0], d[1]), -d[2]) - 0 * math.pi
    o.rotation_euler = (rot_x, 0, rot_z)
    bpy.context.collection.objects.link(o)
    return o


# ---------------------------------------------------------------- build & render
def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    build_floor()
    build_walls()
    build_ceiling()
    slat_window("win_N", "N", center=3.9, width=1.4)
    slat_window("win_W", "W", center=1.55, width=1.6)
    slat_window("win_S", "S", center=2.2, width=1.5)
    build_kamado()
    build_shelf_above_kamado()
    build_west_side()
    build_entrance_wall()
    build_tables_and_misc()
    build_lights()
    cams = {
        "A": add_camera("cam_A", (5.55, 0.55, 1.40), (1.35, 4.05, 1.15), lens=22),
        "B": add_camera("cam_B", (0.75, 3.75, 1.45), (5.9, 1.35, 1.05), lens=22),
    }
    return cams


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--views", default="A,B")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--res", default="1280x830")
    ap.add_argument("--out", default="work/renders")
    ap.add_argument("--blend", default="")
    ap.add_argument("--tag", default="")
    args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None)

    cams = build_scene()
    scn = bpy.context.scene
    w, h = (int(v) for v in args.res.split("x"))
    scn.render.resolution_x = w
    scn.render.resolution_y = h
    scn.cycles.samples = args.samples
    scn.cycles.use_denoising = True
    scn.cycles.device = "CPU"
    scn.view_settings.view_transform = "AgX"
    scn.view_settings.look = "AgX - Base Contrast"
    scn.view_settings.exposure = 0.9

    import os
    os.makedirs(args.out, exist_ok=True)
    for v in args.views.split(","):
        scn.camera = cams[v.strip()]
        scn.render.filepath = os.path.join(args.out, f"view{v.strip()}{args.tag}.png")
        bpy.ops.render.render(write_still=True)
        print("rendered", scn.render.filepath)
    if args.blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.blend))
        print("saved", args.blend)


if __name__ == "__main__":
    main()
