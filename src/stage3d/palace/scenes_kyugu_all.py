# 皇宮フィールド統合シーン: ディテール棟 (主殿/別殿/正門) + 中間LOD (祝殿/庭園/
# 楼閣/客間区/廊下) + 塀・広場・点景。layout_kyugu.py に整合
# 実行: python src/stage3d/palace/scenes_kyugu_all.py -- --views W,P1,C2,Y \
#          --samples 64 --res 1600x900 --out work/renders --tag all1 \
#          --blend work/palace_kyugu_all.blend
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "buildings"))

import bpy  # noqa: E402
from stagelib import (box, cyl, plane, sphere, add_camera, sun_light,  # noqa: E402
                      set_world, render_cli)
from kit.materials import make_materials  # noqa: E402
from kit import props, textures, generic  # noqa: E402
from kit.structure import wood_rail  # noqa: E402
import layout_kyugu as LK  # noqa: E402
import lint_scene  # noqa: E402
import main_hall  # noqa: E402
import bekkuden  # noqa: E402
import gate_south  # noqa: E402

if lint_scene.run(LK):
    raise SystemExit("lint エラーを解消してから実行してください")

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

M = make_materials()

# ---- ディテール棟 ----
main_hall.build(M, ongro_img=os.path.join(textures.OUT, "kw_ongro.png"))
bekkuden.build(M, 28, 110, facing="W", tag="e")
bekkuden.build(M, -28, 110, facing="E", tag="w")
gate_south.build(M)

# ---- 中間LOD棟 (layout_kyugu 準拠) ----
generic.hall_generic(M, "shukuden", 0, 252, 38, 24, eave=7.5, ridge=5.6,
                     terr_h=2.2)                                   # 祝殿
generic.tower2_generic(M, "gtw", 40, 298, 13, 11)                  # 庭の楼閣(西)
generic.tower2_generic(M, "gte", 90, 298, 13, 11)                  # 庭の楼閣(東)
generic.corridor_gen(M, "gcorr", (48, 298), (82, 298))             # 遊廊
for sx in (-1, 1):                                                 # 隅楼×4
    generic.tower2_generic(M, f"tws{sx}", sx * 102, 8, 11, 11)
    generic.tower2_generic(M, f"twn{sx}", sx * 102, 307, 11, 11)
generic.yard_generic(M, "yguest", -75, 40, 44, 52, gate_side="E",
                     trees=[(-86, 30, 2.6), (-64, 52, 2.4)])        # 客間の院
generic.yard_generic(M, "yemp", -72, 210, 46, 54, gate_side="E",
                     trees=[(-84, 224, 2.8)])                       # 皇帝寝室の院
generic.yard_generic(M, "ydow", -72, 275, 46, 54, gate_side="E",
                     trees=[(-58, 288, 2.6)])                       # 皇太后の院
generic.corridor_gen(M, "wcorr", (-49.5, 60), (-49.5, 150), width=3.2)  # 客間→主殿廊下(c205)
# 主殿の左右に伸びる屋根付き廊 (b08_17で袖塀の上に見える橙屋根)。端は外周塀に接続
generic.corridor_gen(M, "mcorr_e", (34, 163.8), (108, 163.8), width=3.8, col_h=3.1)
generic.corridor_gen(M, "mcorr_w", (-108, 163.8), (-34, 163.8), width=3.8, col_h=3.1)
# 掖門 (袖塀の通用門 ±40): 門柱+楣+小屋根 — 主殿区と北区を行き来できる通路
for px in (-40, 40):
    for sx in (-1, 1):
        box(f"ekimon_j{px}{sx}", 0.9, 1.2, 3.8, (px + sx * 3.8, 160, 1.9), M["red"])
    box(f"ekimon_l{px}", 8.6, 1.2, 0.8, (px, 160, 4.2), M["red"])
    from kit.roofs import roof as _roof
    _roof(f"ekimon_r{px}", 9.6, 2.6, 1.3, style="wudian", lift=0.3, zone=1.4,
          material=M["tile_amber"], ridge_mat=M["ridge_amber"],
          loc=(px, 160, 4.6), shiwei=False)
# 中門 (前庭と主殿前広場の境の門構え。塀の開口だけだったのを門らしく)
for sx in (-1, 1):
    box(f"midgate_j{sx}", 1.0, 1.4, 4.6, (sx * 6.2, 62, 2.3), M["red"])
box("midgate_l", 13.8, 1.4, 0.9, (0, 62, 5.05), M["red"])
_roof("midgate_r", 15.2, 3.2, 1.6, style="wudian", lift=0.35, zone=1.8,
      material=M["tile_amber"], ridge_mat=M["ridge_amber"], loc=(0, 62, 5.5),
      shiwei=False)

# ---- 塀 (白壁+橙瓦笠) ----
for wdef in LK.WALLS:
    (x1, y1), (x2, y2) = wdef["p1"], wdef["p2"]
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    ln = math.hypot(x2 - x1, y2 - y1)
    rz = math.atan2(y2 - y1, x2 - x1)
    mat_w = M["red"] if "main" in wdef["id"] else M["stone_w"]
    box(wdef["id"], ln, 0.8, wdef["h"], (cx, cy, wdef["h"] / 2), mat_w,
        rot=(0, 0, rz))
    box(wdef["id"] + "_cap", ln + 0.3, 1.2, 0.35, (cx, cy, wdef["h"] + 0.17),
        M["ridge_amber"], rot=(0, 0, rz))

# ---- 地面・広場・庭園・点景 ----
plane("ground_all", 240, 420, (0, 128, -0.02), M["stone"])  # 正門の南側の地面も確保
plane("fore_court", 100, 52, (0, 34, 0.02), M["paving"])  # 両脇の院に食い込まない幅
props.court_context(M)
plane("garden", 88, 100, (64, 262, 0.03), M["stone_w"])
plane("pond", 36, 20, (60, 248, 0.08), M["water"])
for ex, ey, ew, ed in ((60, 237.6, 37.6, 0.8), (60, 258.4, 37.6, 0.8),
                       (41.2, 248, 0.8, 20.8), (78.8, 248, 0.8, 20.8)):
    box(f"pond_edge{ex}_{ey}", ew, ed, 0.4, (ex, ey, 0.2), M["stone_w"])  # 池の縁石
for i, (rx, ry, rr) in enumerate([(84, 240, 2.2), (44, 276, 2.6), (70, 286, 1.8),
                                  (50, 240, 1.5), (88, 278, 1.9)]):
    sphere(f"grock{i}", rr, (rx, ry, rr * 0.35), M["stone"],
           scale=(1.6, 1.15, 0.55), smooth=False)  # 岩は平たく・面を残す
    sphere(f"grock{i}b", rr * 0.6, (rx + rr * 0.7, ry + 0.4, rr * 0.3), M["stone"],
           scale=(1.2, 1.0, 0.6), smooth=False)
box("gbridge", 3, 14, 0.5, (66, 248, 0.9), M["stone_w"])
for i, (tx, ty, tr) in enumerate(LK.TREES):
    cyl(f"trunk{i}", tr * 0.12, tr, (tx, ty, tr * 0.5), M["bronze"], verts=8)
    sphere(f"tree{i}", tr, (tx, ty, tr * 1.35), M["tree"], scale=(1, 1, 0.85))
props.figures(M, [(0, -14), (-3, -18), (2, 20), (-46, 100), (52, 266)])

set_world((0.60, 0.72, 0.88), 0.68)
sun_light("sun", rot=(math.radians(48), 0, math.radians(135)), energy=3.2,
          angle_deg=2)

cams = {
    "W": add_camera("cam_W", (155, -70, 90), (-25, 175, 2), lens=35),   # 全景(南東上空)
    "P1": add_camera("cam_P1", (5, -34, 1.8), (0, 10, 9), lens=28),     # 正門前
    "C2": add_camera("cam_C2", (-49.5, 63, 2.4), (-49.5, 150, 2.4), lens=30),  # 廊下(c205)
    "Y": add_camera("cam_Y", (-56, 20, 2.0), (-80, 50, 4), lens=26),    # 客間の院
    "B2": add_camera("cam_B2", (0, 70, 7.0), (0, 160, 17), lens=45),    # ボード角(広場内)
    "CU": add_camera("cam_CU", (58, 126, 10.0), (0, 162, 13), lens=30),  # 東寄り(指摘角)
    "ST": add_camera("cam_ST", (3, 100, 1.8), (0, 150, 10), lens=35),   # 階段正面
    "G": add_camera("cam_G", (36, 230, 3.4), (88, 292, 8), lens=28),    # 庭園
}
for c in cams.values():
    c.data.clip_end = 900.0

render_cli(cams, default_res="1600x900", exposure=0.85)
