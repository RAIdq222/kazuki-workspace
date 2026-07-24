# 皇宮・主殿 ヒーロービルド (Phase 1 / ゲート②様式確定用)
# 一次資料: shz_b08_17。配置は layout_kyugu.py の main_hall に一致させる
# 実行: python src/stage3d/palace/buildings/main_hall.py -- --views B,Q,G,S \
#          --samples 96 --res 1600x900 --out work/renders --tag hero1
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PAL = os.path.dirname(_HERE)
sys.path.insert(0, os.path.dirname(_PAL))  # src/stage3d
sys.path.insert(0, _PAL)                   # palace

import bpy  # noqa: E402
from stagelib import (mat, mat_image, box, cyl, sphere, plane, add_camera,  # noqa: E402
                      sun_light, set_world, render_cli)
from kit import textures  # noqa: E402
from kit.roofs import roof  # noqa: E402
from kit.structure import (terrace_tiered, grand_stair_steps, column_row,  # noqa: E402
                           balustrade_run, _link_copy)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

TEX = textures.build_all()

# ---- マテリアル ----
M = dict(
    stone=mat("stone", (0.60, 0.58, 0.53), rough=0.95),
    stone_w=mat("stone_w", (0.78, 0.76, 0.71), rough=0.9),
    red=mat("red_body", (0.40, 0.13, 0.09), rough=0.85),
    redwall=mat_image("kw_redwall", TEX["redwall"], rough=0.9, blend="OPAQUE"),
    col=mat("col_red", (0.52, 0.16, 0.10), rough=0.7),
    gold=mat("gold", (0.62, 0.47, 0.20), rough=0.4),
    tile=mat_image("kw_tile", TEX["tile_grey"], rough=0.8, blend="OPAQUE",
                   uv_scale=(1 / 0.35, 1 / 2.0)),
    tile_amber=mat_image("kw_tile_a", TEX["tile_amber"], rough=0.75, blend="OPAQUE",
                         uv_scale=(1 / 0.35, 1 / 2.0)),
    ridge=mat("ridge_dark", (0.13, 0.14, 0.15), rough=0.7),
    frieze=mat_image("kw_frieze", TEX["frieze"], rough=0.7, blend="OPAQUE"),
    dougong=mat_image("kw_dougong", TEX["dougong"], rough=0.8, blend="OPAQUE"),
    lattice=mat_image("kw_lattice", TEX["lattice"], rough=0.65, blend="OPAQUE"),
    paving=mat_image("kw_paving", TEX["paving"], rough=0.95, blend="OPAQUE",
                     uv_scale=(24, 21)),
    bronze=mat("bronze", (0.16, 0.15, 0.11), rough=0.45),
    fig=mat("fig", (0.15, 0.30, 0.75), rough=0.6),
    tree=mat("tree", (0.23, 0.36, 0.19), rough=0.9),
)

X, Y = 0.0, 160.0          # layout_kyugu の main_hall 位置
TW, TD, TH = 64.0, 44.0, 7.0   # 基壇
HW, HD = 34.0, 20.0        # 身舎
GAL = 2.2                  # 前面柱廊の奥行
Z0 = TH                    # 床レベル

# ---- 基壇+大階段 ----
_, tpls = terrace_tiered("terr", X, Y, TW, TD, TH, M, tiers=2, stair_gap=19)
grand_stair_steps("stair", X, Y - TD / 2, TH, M, tpls, width=16,
                  ongro_img=TEX["ongro"])

# ---- 1層: 柱廊+壁 ----
BAYS = [3.4, 4.0, 4.6, 5.2, 4.6, 4.0, 3.4]
span = sum(BAYS)
xs = column_row("colf", X - span / 2, Y - HD / 2, BAYS, M["col"], M["gold"],
                Z0, 6.2)
WALL_Y = Y - HD / 2 + GAL
body = box("body1", HW, HD - GAL, 6.2, (X, Y + GAL / 2, Z0 + 3.1), M["red"])
plane("wall1_f", HW, 6.2, (X, WALL_Y - 0.01, Z0 + 3.1), M["redwall"],
      rot=(math.pi / 2, 0, 0))
for sx in (-1, 1):
    plane(f"wall1_s{sx}", HD - GAL, 6.2, (X + sx * (HW / 2 + 0.01), Y + GAL / 2, Z0 + 3.1),
          M["redwall"], rot=(math.pi / 2, 0, math.pi / 2))
plane("wall1_b", HW, 6.2, (X, Y + HD / 2 + 0.01, Z0 + 3.1), M["redwall"],
      rot=(math.pi / 2, 0, math.pi))
# 中央5間は格子扉
for i in range(1, 6):
    bx0, bx1 = xs[i], xs[i + 1]
    plane(f"door{i}", bx1 - bx0 - 0.25, 4.7, ((bx0 + bx1) / 2, WALL_Y - 0.03, Z0 + 2.4),
          M["lattice"], rot=(math.pi / 2, 0, 0))
# 額枋(金彫刻帯)+斗栱帯
for tag, zc, hgt, m in (("gaku1", Z0 + 6.2 + 0.35, 0.7, M["frieze"]),
                        ("dou1", Z0 + 6.2 + 1.15, 0.9, M["dougong"])):
    box(f"{tag}_core", HW + 0.4, HD + 0.4, hgt, (X, Y, zc), M["red"])
    plane(f"{tag}_f", HW + 0.42, hgt, (X, Y - HD / 2 - 0.22, zc), m,
          rot=(math.pi / 2, 0, 0))
    plane(f"{tag}_b", HW + 0.42, hgt, (X, Y + HD / 2 + 0.22, zc), m,
          rot=(math.pi / 2, 0, math.pi))
    for sx in (-1, 1):
        plane(f"{tag}_s{sx}", HD + 0.42, hgt, (X + sx * (HW / 2 + 0.22), Y, zc), m,
              rot=(math.pi / 2, 0, math.pi / 2))

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
    box(f"balc_rail{bx}_{by}", bw, bd, 0.12, (X + bx, Y + by, Z0 + 12.80), M["col"])

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
for tag, zc, hgt, m in (("gaku2", Z0 + 15.4 + 0.3, 0.6, M["frieze"]),
                        ("dou2", Z0 + 15.4 + 1.05, 0.85, M["dougong"])):
    box(f"{tag}_core", 26.4, 14.4, hgt, (X, Y, zc), M["red"])
    plane(f"{tag}_f", 26.4, hgt, (X, Y - 7.22, zc), m, rot=(math.pi / 2, 0, 0))
    plane(f"{tag}_b", 26.4, hgt, (X, Y + 7.22, zc), m, rot=(math.pi / 2, 0, math.pi))
    for sx in (-1, 1):
        plane(f"{tag}_s{sx}", 14.4, hgt, (X + sx * 13.22, Y, zc), m,
              rot=(math.pi / 2, 0, math.pi / 2))
roof("r_upper", 29, 17, 5.6, style="xieshan", xr=0.45, lift=0.5, reach=0.35,
     material=M["tile"], ridge_mat=M["ridge"], loc=(X, Y, Z0 + 17.3))

# ---- 袖塀 (基壇の左右から) ----
for sx in (-1, 1):
    box(f"sode{sx}", 46, 1.0, 4.6, (X + sx * (TW / 2 + 23), Y, 2.3), M["red"])
    box(f"sode_cap{sx}", 46.4, 1.5, 0.5, (X + sx * (TW / 2 + 23), Y, 4.85),
        M["ridge"])

# ---- 広場コンテキスト (b08_17の構図確認用) ----
plane("plaza", 100, 92, (0, 110, 0.02), M["paving"])
box("ongdo", 10, 34, 0.8, (0, 121, 0.4), M["stone"])
cyl("censer", 1.35, 2.7, (0, 104, 1.35 + 0.8), M["bronze"], verts=24)
cyl("censer_lid", 0.9, 0.9, (0, 104, 3.4), M["bronze"], verts=24, r2=0.35)
for i, (dx, dy, sw, sd) in enumerate([(0, -4.4, 9.6, 0.35), (0, 4.4, 9.6, 0.35),
                                      (-4.8, 0, 0.35, 8.5), (4.8, 0, 0.35, 8.5)]):
    box(f"cen_rail{i}", sw, sd, 0.95, (dx, 104 + dy, 0.8 + 0.5), M["stone_w"])
for i, (fx, fy) in enumerate([(2.5, 98), (-1.5, 96), (7.2, 126), (-7.2, 131)]):
    cyl(f"fig{i}", 0.22, 1.3, (fx, fy, 0.65), M["fig"], verts=10)
    sphere(f"fig{i}_h", 0.16, (fx, fy, 1.48), M["fig"])
# 背景の脇殿屋根と樹木 (構図の奥行き用ダミー)
for sx in (-1, 1):
    box(f"bg_body{sx}", 30, 12, 6, (sx * 42, 196, 3), M["red"])
    roof(f"bg_roof{sx}", 33, 15, 4.4, style="wudian", lift=0.4,
         material=M["tile_amber"], ridge_mat=M["ridge"], loc=(sx * 42, 196, 6))
    sphere(f"bg_tree{sx}", 4.5, (sx * 26, 190, 5.2), M["tree"], scale=(1, 1, 0.9))

set_world((0.60, 0.72, 0.88), 0.68)
sun_light("sun", rot=(math.radians(48), 0, math.radians(135)), energy=3.2, angle_deg=2)

cams = {
    "B": add_camera("cam_B", (0, 30, 7.0), (0, 160, 17), lens=45),     # b08_17再現
    "Q": add_camera("cam_Q", (46, 114, 4.5), (-4, 158, 15), lens=30),  # 斜め3/4
    "G": add_camera("cam_G", (13, 140.5, 8.8), (-6, 153, 11), lens=30),  # 柱廊を斜めに
    "S": add_camera("cam_S", (8.5, 89, 1.65), (-1, 148, 10), lens=30),  # 人目線(香炉と階段)
}
for c in cams.values():
    c.data.clip_end = 700.0

render_cli(cams, default_res="1600x900", exposure=0.85)
