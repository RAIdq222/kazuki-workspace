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
for i, (rx, ry, rr) in enumerate([(84, 240, 2.0), (44, 276, 2.4), (70, 286, 1.6)]):
    sphere(f"grock{i}", rr, (rx, ry, rr * 0.5), M["stone"], scale=(1.3, 1, 0.8))
box("gbridge", 3, 14, 0.5, (66, 248, 0.9), M["stone_w"])
for i, (tx, ty, tr) in enumerate(LK.TREES):
    cyl(f"trunk{i}", tr * 0.12, tr, (tx, ty, tr * 0.5), M["bronze"], verts=8)
    sphere(f"tree{i}", tr, (tx, ty, tr * 1.35), M["tree"], scale=(1, 1, 0.85))
props.figures(M, [(0, -14), (-3, -18), (2, 20), (-46, 100), (60, 255)])

set_world((0.60, 0.72, 0.88), 0.68)
sun_light("sun", rot=(math.radians(48), 0, math.radians(135)), energy=3.2,
          angle_deg=2)

cams = {
    "W": add_camera("cam_W", (155, -70, 90), (-25, 175, 2), lens=35),   # 全景(南東上空)
    "P1": add_camera("cam_P1", (5, -34, 1.8), (0, 10, 9), lens=28),     # 正門前
    "C2": add_camera("cam_C2", (-49.5, 63, 2.4), (-49.5, 150, 2.4), lens=30),  # 廊下(c205)
    "Y": add_camera("cam_Y", (-56, 20, 2.0), (-80, 50, 4), lens=26),    # 客間の院
}
for c in cams.values():
    c.data.clip_end = 900.0

render_cli(cams, default_res="1600x900", exposure=0.85)
