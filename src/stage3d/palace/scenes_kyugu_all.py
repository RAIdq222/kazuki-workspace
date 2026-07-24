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

# ---- 背景の充填 (Issue #6 P0-2: 樹冠と屋根列で地平線を閉じ、空白帯をなくす) ----
from kit.roofs import roof as _r2
for i, (bx, by, bw, bd, bh) in enumerate([
        (-72, 194, 24, 11, 6.5), (72, 194, 24, 11, 6.5),   # 廊のすぐ背後の二階級
        (-44, 204, 18, 10, 5.0), (44, 206, 18, 10, 5.0),
        (-90, 212, 20, 10, 7.0), (90, 214, 20, 10, 7.0),
        (-28, 212, 15, 9, 4.5), (28, 214, 15, 9, 4.5),     # 主殿の両脇の奥
        (-60, 228, 18, 9, 6.0), (60, 230, 18, 9, 6.0)]):
    box(f"bgh{i}", bw, bd, bh, (bx, by, bh / 2), M["red"])
    _r2(f"bgh{i}_r", bw + 2.2, bd + 2.2, 3.4, style="xieshan", xr=0.5, lift=0.4,
        material=M["tile_amber"], ridge_mat=M["ridge_amber"], loc=(bx, by, bh),
        shiwei=False, with_ridges=False)
for i in range(30):  # 主殿背後〜東西の樹冠帯 (廊の屋根越しに覗く高さ)
    tx = -102 + (i * 7.1) % 204
    ty = 176 + ((i * 37) % 5) * 8
    tr = 3.8 + ((i * 13) % 3) * 0.9
    cyl(f"bgt{i}t", tr * 0.1, tr * 1.6, (tx, ty, tr * 0.8), M["bronze"], verts=6)
    sphere(f"bgt{i}", tr, (tx, ty, tr * 1.9), M["tree"], scale=(1.15, 1, 0.9))
for i in range(14):  # 広場の東西外側 (別殿の背後) の樹冠
    sx = -1 if i % 2 else 1
    tx = sx * (60 + (i * 11) % 34)
    ty = 66 + (i * 17) % 80
    tr = 3.2 + (i % 3) * 0.9
    cyl(f"bgs{i}t", tr * 0.1, tr * 1.5, (tx, ty, tr * 0.75), M["bronze"], verts=6)
    sphere(f"bgs{i}", tr, (tx, ty, tr * 1.8), M["tree"], scale=(1.1, 1, 0.9))

set_world((0.60, 0.72, 0.88), 0.68)
sun_light("sun", rot=(math.radians(48), 0, math.radians(135)), energy=3.2,
          angle_deg=2)

# カメラは configs/kyugu.json を単一の情報源とする (Issue #6 P0-1: 手転記の廃止)
# config は three.js 座標系 (x, z, -y) なので blender 座標へ逆変換する
import json  # noqa: E402

with open(os.path.join(os.path.dirname(_HERE), "configs", "kyugu.json"),
          encoding="utf-8") as _f:
    _CFG = json.load(_f)


def _b(p):  # three -> blender: (x, y_up, z_south) -> (x, -z, y)
    return (p[0], -p[2], p[1])


cams = {}
for _k, _v in list(_CFG["presets"].items()) + list(_CFG.get("qaCams", {}).items()):
    if _k in cams:
        continue
    cams[_k] = add_camera(f"cam_{_k}", _b(_v["pos"]), _b(_v["tgt"]),
                          lens=_v.get("mm", 35))
for c in cams.values():
    c.data.clip_end = 900.0

render_cli(cams, default_res="1600x900", exposure=0.85)
