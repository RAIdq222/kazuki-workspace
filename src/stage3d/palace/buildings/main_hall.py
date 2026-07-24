# 皇宮・主殿 (b08_17)。build(M) で生成、単体実行でヒーロー検証シーン
# 実行: python src/stage3d/palace/buildings/main_hall.py -- --views B,Q,G,S ...
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PAL = os.path.dirname(_HERE)
sys.path.insert(0, os.path.dirname(_PAL))  # src/stage3d
sys.path.insert(0, _PAL)                   # palace

from stagelib import box, plane  # noqa: E402
from kit.structure import _link_copy  # noqa: E402
from kit.roofs import roof  # noqa: E402
from kit.structure import (terrace_tiered, grand_stair_steps, column_row,  # noqa: E402
                           _link_copy)

X, Y = 0.0, 160.0            # layout_kogu の main_hall 位置
TW, TD, TH = 64.0, 44.0, 7.0  # 基壇
HW, HD = 34.0, 20.0          # 身舎
GAL = 2.2                    # 前面柱廊の奥行
BAYS = [3.4, 4.0, 4.6, 5.2, 4.6, 4.0, 3.4]


def build(M, ongro_img=None):
    Z0 = TH
    # ---- 基壇+大階段 (御路+左右レーン)+側階 ----
    _, tpls = terrace_tiered("terr", X, Y, TW, TD, TH, M, tiers=2, stair_gap=22,
                             side_gaps=[(-24, 9.5), (24, 9.5)])
    grand_stair_steps("stair", X, Y - TD / 2, TH, M, tpls, width=20,
                      ongro_img=ongro_img)
    _side_stairs(M)

    # ---- 1層: 柱廊+壁 ----
    span = sum(BAYS)
    xs = column_row("colf", X - span / 2, Y - HD / 2, BAYS, M["col"], M["gold"],
                    Z0, 6.2)
    wall_y = Y - HD / 2 + GAL
    box("body1", HW, HD - GAL, 6.2, (X, Y + GAL / 2, Z0 + 3.1), M["red"])
    plane("wall1_f", HW, 6.2, (X, wall_y - 0.01, Z0 + 3.1), M["redwall"],
          rot=(math.pi / 2, 0, 0))
    for sx in (-1, 1):
        plane(f"wall1_s{sx}", HD - GAL, 6.2,
              (X + sx * (HW / 2 + 0.01), Y + GAL / 2, Z0 + 3.1), M["redwall"],
              rot=(math.pi / 2, 0, math.pi / 2))
    plane("wall1_b", HW, 6.2, (X, Y + HD / 2 + 0.01, Z0 + 3.1), M["redwall"],
          rot=(math.pi / 2, 0, math.pi))
    # 柱間ごとの建具 (Issue #6 P1-4): 中央=暗い開口 / 隣接4間=暗色格子扉
    for i in range(1, 6):
        bx0, bx1 = xs[i], xs[i + 1]
        cx, bw = (bx0 + bx1) / 2, bx1 - bx0
        if i == 3:  # 明間: 独立した暗い開口 (奥に闇、手前に金枠)
            plane(f"door_void", bw - 0.3, 4.9, (cx, wall_y + 0.9, Z0 + 2.45),
                  M["void"], rot=(math.pi / 2, 0, 0))
            for s2 in (-1, 1):
                box(f"door_fj{s2}", 0.3, 0.22, 5.0, (cx + s2 * (bw / 2 - 0.3),
                                                     wall_y - 0.05, Z0 + 2.5),
                    M["wood_dark"])
            box("door_fh", bw - 0.2, 0.22, 0.35, (cx, wall_y - 0.05, Z0 + 5.05),
                M["wood_dark"])
        else:
            plane(f"door{i}", bw - 0.25, 4.7, (cx, wall_y - 0.03, Z0 + 2.4),
                  M["lattice_dk"], rot=(math.pi / 2, 0, 0))
    # 頭貫・軒桁 (柱列の上に載る別部材) と柱礎
    from stagelib import cyl as _cyl
    box("kashiranuki", span + 1.2, 0.4, 0.5, (X, Y - HD / 2, Z0 + 5.85),
        M["wood_dark"])
    box("nokigeta", span + 1.6, 0.5, 0.35, (X, Y - HD / 2, Z0 + 6.25),
        M["wood_dark"])
    for i, cx in enumerate(xs):
        _cyl(f"colbase{i}", 0.38, 0.26, (cx, Y - HD / 2, Z0 + 0.13),
             M["stone_w"], verts=14)
    _bands("1", X, Y, HW, HD, Z0 + 6.2, M)

    # ---- 裳階(腰屋根)+軒裏 (帯の上に隙間を残さない=浮き防止) ----
    box("soffit1", HW + 1.8, HD + 1.8, 0.55, (X, Y, Z0 + 8.05), M["ridge"])
    roof("r_lower", HW + 3.2, HD + 3.2, 3.0, top_rect=(13.4, 7.4),
         lift=0.4, reach=0.28, material=M["tile"], ridge_mat=M["ridge"],
         loc=(X, Y, Z0 + 8.3))
    # ---- 平座 (木質の床+持送り)+赤い高欄 (二段貫・太柱) ----
    box("balc", 28.4, 16.4, 0.5, (X, Y, Z0 + 11.55), M["wood_floor"])
    tpl_bk = box("tpl_bracket", 0.35, 0.55, 0.4, (0, 0, -72), M["wood_dark"])
    for i in range(14):
        px = X - 13.2 + i * (26.4 / 13)
        for sy in (-1, 1):
            _link_copy(tpl_bk, f"balc_bk{i}{sy}", (px, Y + sy * 7.9, Z0 + 11.1))
    for i in range(8):
        py = Y - 7.0 + i * (14.0 / 7)
        for sx in (-1, 1):
            _link_copy(tpl_bk, f"balc_bl{i}{sx}", (X + sx * 13.9, py, Z0 + 11.1))
    tpl_bk.location = (0, 0, -500)
    tpl_rp = box("tpl_rpost", 0.19, 0.19, 1.05, (0, 0, -60), M["col"])
    for i in range(22):
        px = X - 13.6 + i * (27.2 / 21)
        for sy in (-1, 1):
            _link_copy(tpl_rp, f"balcp_{i}{sy}", (px, Y + sy * 8.0, Z0 + 12.33))
    for i in range(12):
        py = Y - 7.4 + i * (14.8 / 11)
        for sx in (-1, 1):
            _link_copy(tpl_rp, f"balcq_{i}{sx}", (X + sx * 14.0, py, Z0 + 12.33))
    tpl_rp.location = (0, 0, -500)
    for bx, by, bw, bd in ((0, -8.0, 28.6, 0.16), (0, 8.0, 28.6, 0.16),
                           (-14.0, 0, 0.16, 16.4), (14.0, 0, 0.16, 16.4)):
        box(f"balc_rail{bx}_{by}", bw, bd, 0.18, (X + bx, Y + by, Z0 + 12.92),
            M["col"])
        box(f"balc_railm{bx}_{by}", bw, bd * 0.8, 0.10,
            (X + bx, Y + by, Z0 + 12.60), M["col"])

    # ---- 2層 (Issue #6 P1-5: 前面列柱+柱間ごとの暗い建具+中央の額) ----
    box("body2", 26, 14, 4.4, (X, Y, Z0 + 11.0 + 2.2), M["red"])
    plane("wall2_b", 26, 4.4, (X, Y + 7.01, Z0 + 13.2), M["redwall"],
          rot=(math.pi / 2, 0, math.pi))
    for sx in (-1, 1):
        plane(f"wall2_s{sx}", 14, 4.4, (X + sx * 13.01, Y, Z0 + 13.2), M["redwall"],
              rot=(math.pi / 2, 0, math.pi / 2))
    xs2 = [X + (x0 - X) * (24.0 / span) for x0 in xs]  # 1層柱筋を2層幅へ縮小
    tpl_c2 = _cyl("tpl_col2", 0.16, 3.3, (0, 0, -74), M["col"], verts=14)
    for i, cx in enumerate(xs2):
        _link_copy(tpl_c2, f"col2_{i}", (cx, Y - 7.35, Z0 + 11.8 + 1.65))
    tpl_c2.location = (0, 0, -500)
    for i in range(len(xs2) - 1):  # 柱間の暗い建具
        cx = (xs2[i] + xs2[i + 1]) / 2
        bw = xs2[i + 1] - xs2[i]
        plane(f"lat2_{i}", bw - 0.3, 2.5, (cx, Y - 7.01, Z0 + 13.35),
              M["lattice_dk"], rot=(math.pi / 2, 0, 0))
    box("gaku_plaque", 2.0, 0.14, 1.2, (X, Y - 7.45, Z0 + 14.9), M["gold"])
    box("gaku_plaque_in", 1.7, 0.1, 0.95, (X, Y - 7.48, Z0 + 14.9), M["wood_dark"])
    _bands("2", X, Y, 26, 14, Z0 + 15.4, M, scale=0.85)
    box("soffit2", 26 + 1.6, 14 + 1.6, 0.55, (X, Y, Z0 + 17.05), M["ridge"])
    roof("r_upper", 29, 17, 5.6, style="xieshan", xr=0.45, lift=0.5, reach=0.35,
         material=M["tile"], ridge_mat=M["ridge"], loc=(X, Y, Z0 + 17.3))
    # 袖塀は統合シーン側 (wall_main+廊) が持つため、ここでは作らない


def _side_stairs(M):
    """基壇前面の側階 (b08_17で中央階段の左右に見える斜めの欄干の正体)。1段目まで."""
    h1 = TH * 0.55
    y_front = Y - TD / 2
    n = int(h1 / 0.146)
    run = n * 0.32
    ang = math.atan2(h1, run)
    slope = math.hypot(run, h1)
    for sx in (-1, 1):
        px = X + sx * 24
        tpl = box(f"sstpl{sx}", 8.0, 0.32, 0.146, (0, 0, -70), M["stone"])
        y = y_front - run
        z = 0.0
        for i in range(n):
            _link_copy(tpl, f"sst{sx}_{i}", (px, y + 0.16, z + 0.073))
            y += 0.32
            z += 0.146
        tpl.location = (0, 0, -500)
        for s2 in (-1, 1):  # 垂帯石
            fl = box(f"ssfl{sx}{s2}", 0.45, slope + 0.5, 1.1,
                     (px + s2 * 4.2, y_front - run / 2, h1 / 2 - 0.3), M["stone"])
            fl.rotation_euler = (ang, 0, 0)


def _bands(tag, x, y, w, d, z_base, M, scale=1.0):
    """額枋(金彫刻帯)+斗栱帯を四周に回す."""
    g_h, d_h = 0.7 * scale, 0.9 * scale
    for nm, zc, hgt, m in ((f"gaku{tag}", z_base + g_h / 2, g_h, M["frieze"]),
                           (f"dou{tag}", z_base + g_h + d_h / 2, d_h, M["dougong"])):
        box(f"{nm}_core", w + 0.4, d + 0.4, hgt, (x, y, zc), M["red"])
        plane(f"{nm}_f", w + 0.42, hgt, (x, y - d / 2 - 0.22, zc), m,
              rot=(math.pi / 2, 0, 0))
        plane(f"{nm}_b", w + 0.42, hgt, (x, y + d / 2 + 0.22, zc), m,
              rot=(math.pi / 2, 0, math.pi))
        for sx in (-1, 1):
            plane(f"{nm}_s{sx}", d + 0.42, hgt, (x + sx * (w / 2 + 0.22), y, zc), m,
                  rot=(math.pi / 2, 0, math.pi / 2))


if __name__ == "__main__":
    import bpy
    from stagelib import add_camera, sun_light, set_world, render_cli
    from kit.materials import make_materials
    from kit import props

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    M = make_materials()
    from kit import textures as _t
    build(M, ongro_img=os.path.join(_t.OUT, "kw_ongro.png"))
    props.court_context(M)
    set_world((0.60, 0.72, 0.88), 0.68)
    sun_light("sun", rot=(math.radians(48), 0, math.radians(135)), energy=3.2,
              angle_deg=2)
    cams = {
        "B": add_camera("cam_B", (0, 30, 7.0), (0, 160, 17), lens=45),
        "Q": add_camera("cam_Q", (46, 114, 4.5), (-4, 158, 15), lens=30),
        "G": add_camera("cam_G", (13, 140.5, 8.8), (-6, 153, 11), lens=30),
        "S": add_camera("cam_S", (8.5, 89, 1.65), (-1, 148, 10), lens=30),
    }
    for c in cams.values():
        c.data.clip_end = 700.0
    render_cli(cams, default_res="1600x900", exposure=0.85)
