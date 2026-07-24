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
from kit.roofs import roof  # noqa: E402
from kit.structure import (terrace_tiered, grand_stair_steps, column_row,  # noqa: E402
                           _link_copy)

X, Y = 0.0, 160.0            # layout_kyugu の main_hall 位置
TW, TD, TH = 64.0, 44.0, 7.0  # 基壇
HW, HD = 34.0, 20.0          # 身舎
GAL = 2.2                    # 前面柱廊の奥行
BAYS = [3.4, 4.0, 4.6, 5.2, 4.6, 4.0, 3.4]


def build(M, ongro_img=None):
    Z0 = TH
    # ---- 基壇+大階段 ----
    _, tpls = terrace_tiered("terr", X, Y, TW, TD, TH, M, tiers=2, stair_gap=17.4)
    grand_stair_steps("stair", X, Y - TD / 2, TH, M, tpls, width=16,
                      ongro_img=ongro_img)

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
    for i in range(1, 6):  # 中央5間は格子扉
        bx0, bx1 = xs[i], xs[i + 1]
        plane(f"door{i}", bx1 - bx0 - 0.25, 4.7,
              ((bx0 + bx1) / 2, wall_y - 0.03, Z0 + 2.4), M["lattice"],
              rot=(math.pi / 2, 0, 0))
    _bands("1", X, Y, HW, HD, Z0 + 6.2, M)

    # ---- 裳階(腰屋根)+平座 ----
    roof("r_lower", HW + 3.2, HD + 3.2, 3.0, top_rect=(13.4, 7.4),
         lift=0.4, reach=0.28, material=M["tile"], ridge_mat=M["ridge"],
         loc=(X, Y, Z0 + 8.3))
    box("balc", 28.4, 16.4, 0.5, (X, Y, Z0 + 11.55), M["stone_w"])
    tpl_rp = box("tpl_rpost", 0.14, 0.14, 0.95, (0, 0, -60), M["col"])
    for i in range(22):
        px = X - 13.6 + i * (27.2 / 21)
        for sy in (-1, 1):
            _link_copy(tpl_rp, f"balcp_{i}{sy}", (px, Y + sy * 8.0, Z0 + 12.28))
    for i in range(12):
        py = Y - 7.4 + i * (14.8 / 11)
        for sx in (-1, 1):
            _link_copy(tpl_rp, f"balcq_{i}{sx}", (X + sx * 14.0, py, Z0 + 12.28))
    tpl_rp.location = (0, 0, -500)
    for bx, by, bw, bd in ((0, -8.0, 28.4, 0.12), (0, 8.0, 28.4, 0.12),
                           (-14.0, 0, 0.12, 16.2), (14.0, 0, 0.12, 16.2)):
        box(f"balc_rail{bx}_{by}", bw, bd, 0.12, (X + bx, Y + by, Z0 + 12.80),
            M["col"])

    # ---- 2層 ----
    box("body2", 26, 14, 4.4, (X, Y, Z0 + 11.0 + 2.2), M["red"])
    plane("wall2_f", 26, 3.4, (X, Y - 7.01, Z0 + 13.3), M["redwall"],
          rot=(math.pi / 2, 0, 0))
    plane("wall2_b", 26, 4.4, (X, Y + 7.01, Z0 + 13.2), M["redwall"],
          rot=(math.pi / 2, 0, math.pi))
    for sx in (-1, 1):
        plane(f"wall2_s{sx}", 14, 4.4, (X + sx * 13.01, Y, Z0 + 13.2), M["redwall"],
              rot=(math.pi / 2, 0, math.pi / 2))
    plane("lat2", 19, 1.9, (X, Y - 7.03, Z0 + 13.55), M["lattice"],
          rot=(math.pi / 2, 0, 0))
    _bands("2", X, Y, 26, 14, Z0 + 15.4, M, scale=0.85)
    roof("r_upper", 29, 17, 5.6, style="xieshan", xr=0.45, lift=0.5, reach=0.35,
         material=M["tile"], ridge_mat=M["ridge"], loc=(X, Y, Z0 + 17.3))

    # ---- 袖塀 ----
    for sx in (-1, 1):
        box(f"sode{sx}", 46, 1.0, 4.6, (X + sx * (TW / 2 + 23), Y, 2.3), M["red"])
        box(f"sode_cap{sx}", 46.4, 1.5, 0.5, (X + sx * (TW / 2 + 23), Y, 4.85),
            M["ridge"])


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
