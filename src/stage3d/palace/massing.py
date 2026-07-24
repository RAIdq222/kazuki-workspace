# 宮殿 Phase 0: 箱マッシング (承認用ラフ)
# 実行: python src/stage3d/palace/massing.py -- --views T,A,F,P --samples 48 --res 1600x900 \
#          --out work/renders --tag mass1 --blend work/palace_massing.blend
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))   # src/stage3d (stagelib)
sys.path.insert(0, _HERE)                    # palace (layout / lint)

import bpy  # noqa: E402
from stagelib import (mat, box, cyl, sphere, plane, add_camera,  # noqa: E402
                      sun_light, set_world, render_cli)
from layout import SITE, WALLS, TREES, expand  # noqa: E402
import lint_scene  # noqa: E402

if lint_scene.run():
    raise SystemExit("lint エラーを解消してから実行してください")

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

# ---- マテリアル (マッシング用フラットカラー) ----
M = dict(
    body=mat("body", (0.72, 0.68, 0.58), rough=0.9),        # 白漆喰ボディ
    roof_grey=mat("roof_grey", (0.29, 0.32, 0.34), rough=0.8),   # 宮廷系 灰瓦
    roof_amber=mat("roof_amber", (0.66, 0.38, 0.10), rough=0.7),  # 皇宮系 橙瓦
    roof_dark=mat("roof_dark", (0.16, 0.17, 0.18), rough=0.8),   # 主殿 濃灰
    stone=mat("stone", (0.62, 0.60, 0.55), rough=0.95),     # 基壇・石畳
    plaza=mat("plaza", (0.55, 0.53, 0.48), rough=0.95),
    gravel=mat("gravel", (0.66, 0.63, 0.57), rough=0.95),
    wallw=mat("wallw", (0.78, 0.74, 0.64), rough=0.9),      # 白漆喰塀
    ground=mat("ground", (0.45, 0.45, 0.38), rough=0.95),
    tree=mat("tree", (0.23, 0.36, 0.19), rough=0.9),
    bronze=mat("bronze", (0.18, 0.16, 0.12), rough=0.5),
    water=mat("water", (0.30, 0.48, 0.50), rough=0.15),
)


def roof_mat(style):
    return {"grey": M["roof_grey"], "amber": M["roof_amber"],
            "dark": M["roof_dark"]}.get(style, M["roof_grey"])


def hip_roof(name, w, d, h, loc, material, rot_z=0.0, overhang=1.4):
    """寄棟プリズム。ridge は長辺(w)方向。w<d なら自動で90°回す."""
    if d > w:
        w, d = d, w
        rot_z += math.pi / 2
    w += overhang * 2
    d += overhang * 2
    ridge = max((w - d) / 2, 0.0)
    verts = [(-w / 2, -d / 2, 0), (w / 2, -d / 2, 0),
             (w / 2, d / 2, 0), (-w / 2, d / 2, 0),
             (-ridge, 0, h), (ridge, 0, h)]
    faces = [(0, 1, 5, 4), (2, 3, 4, 5), (1, 2, 5), (3, 0, 4)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new(name, me)
    o.location = loc
    o.rotation_euler = (0, 0, rot_z)
    o.data.materials.append(material)
    bpy.context.collection.objects.link(o)
    return o


def face_rot(face):
    """建物の正面方位 → ローカルX(間口)がどちらを向くか。S/N=間口X沿い."""
    return math.pi / 2 if face in ("E", "W") else 0.0


def bld_hall(b, eave, ridge, terr=None, style=None):
    """基壇(任意)+ボディ+寄棟 の基本形."""
    st = style or b.get("style", "grey")
    x, y = b["x"], b["y"]
    rz = face_rot(b.get("face", "S"))
    z0 = 0.0
    if terr:
        box(f"{b['id']}_terr", terr["w"], terr["d"], terr["h"],
            (x, y, terr["h"] / 2), M["stone"], rot=(0, 0, rz))
        z0 = terr["h"]
    box(f"{b['id']}_body", b["w"], b["d"], eave, (x, y, z0 + eave / 2),
        M["body"], rot=(0, 0, rz))
    hip_roof(f"{b['id']}_roof", b["w"], b["d"], ridge, (x, y, z0 + eave),
             roof_mat(st), rot_z=rz)
    return z0 + eave + ridge


def build(b):
    k, x, y = b["kind"], b["x"], b["y"]
    st = b.get("style", "grey")
    rz = face_rot(b.get("face", "S"))

    if k == "plaza":
        plane(b["id"], b["w"], b["d"], (x, y, 0.03), M["plaza"])
    elif k == "gravel":
        plane(b["id"], b["w"], b["d"], (x, y, 0.03), M["gravel"])
        for i, (rx, ry, rr) in enumerate([(38, -16, 2.0), (-44, 14, 2.4), (20, 22, 1.6)]):
            sphere(f"{b['id']}_rock{i}", rr, (x + rx, y + ry, rr * 0.5), M["stone"],
                   scale=(1.3, 1.0, 0.8))
    elif k == "pond":
        plane(b["id"], b["w"], b["d"], (x, y, 0.06), M["water"])
    elif k == "censer":
        cyl(b["id"], 1.3, 2.6, (x, y, 1.3), M["bronze"])
    elif k == "wall":
        box(b["id"], b["w"], b["d"], b["h"], (x, y, b["h"] / 2), M["wallw"])
    elif k == "gate3":  # 三重楼閣城門楼: 城台+3層
        box(f"{b['id']}_base", b["w"], b["d"], 6, (x, y, 3), M["stone"], rot=(0, 0, rz))
        z, w, d = 6.0, b["w"] * 0.86, b["d"] * 0.8
        for t in range(3):
            box(f"{b['id']}_t{t}", w, d, 3.2, (x, y, z + 1.6), M["body"], rot=(0, 0, rz))
            hip_roof(f"{b['id']}_r{t}", w, d, 2.6 if t < 2 else 3.6,
                     (x, y, z + 3.2), roof_mat(st), rot_z=rz)
            z += 5.0
            w *= 0.82
            d *= 0.82
    elif k == "gate2":  # 二階重檐門楼
        th = b.get("terrace_h", 3.0)
        box(f"{b['id']}_terr", b["w"] + 8, b["d"] + 8, th, (x, y, th / 2),
            M["stone"], rot=(0, 0, rz))
        box(f"{b['id']}_body", b["w"], b["d"], 8, (x, y, th + 4), M["body"], rot=(0, 0, rz))
        hip_roof(f"{b['id']}_skirt", b["w"], b["d"], 2.2, (x, y, th + 8),
                 roof_mat(st), rot_z=rz)
        box(f"{b['id']}_up", b["w"] * 0.72, b["d"] * 0.72, 3.6, (x, y, th + 10.2 + 1.8),
            M["body"], rot=(0, 0, rz))
        hip_roof(f"{b['id']}_top", b["w"] * 0.72, b["d"] * 0.72, 4.4,
                 (x, y, th + 10.2 + 3.6), roof_mat(st), rot_z=rz)
    elif k == "gate_arch":  # 玄関門
        box(f"{b['id']}_body", b["w"], b["d"], 5.5, (x, y, 2.75), M["body"], rot=(0, 0, rz))
        hip_roof(f"{b['id']}_roof", b["w"], b["d"], 2.8, (x, y, 5.5), roof_mat(st), rot_z=rz)
    elif k == "hall2":  # 重檐正殿
        t = b["terrace"]
        box(f"{b['id']}_terr1", t["w"], t["d"], t["h"] * 0.5, (x, y, t["h"] * 0.25),
            M["stone"], rot=(0, 0, rz))
        box(f"{b['id']}_terr2", t["w"] - 8, t["d"] - 8, t["h"] * 0.5,
            (x, y, t["h"] * 0.75), M["stone"], rot=(0, 0, rz))
        z0 = t["h"]
        box(f"{b['id']}_body", b["w"], b["d"], 11, (x, y, z0 + 5.5), M["body"], rot=(0, 0, rz))
        hip_roof(f"{b['id']}_skirt", b["w"], b["d"], 3.0, (x, y, z0 + 11),
                 roof_mat(b["style"]), rot_z=rz)
        box(f"{b['id']}_up", b["w"] * 0.76, b["d"] * 0.72, 4.5, (x, y, z0 + 14 + 2.25),
            M["body"], rot=(0, 0, rz))
        hip_roof(f"{b['id']}_top", b["w"] * 0.76, b["d"] * 0.72, 6.5,
                 (x, y, z0 + 18.5), roof_mat(b["style"]), rot_z=rz)
        # 正面大階段 (踊り場付き) — 中軸上のスロープで略記
        box(f"{b['id']}_stair", 10, 10, 1.2, (x, y - t["d"] / 2 - 3.2, t["h"] / 2 - 0.5),
            M["stone"], rot=(math.radians(-18), 0, 0))
    elif k == "wing":  # 脇殿 (低基壇+単檐)
        bld_hall(b, eave=7, ridge=5,
                 terr=dict(w=b["w"] + 4, d=b["d"] + 4, h=1.5), style=st)
    elif k == "hall":
        bld_hall(b, eave=8, ridge=6, terr=dict(w=b["w"] + 5, d=b["d"] + 5, h=2.0), style=st)
    elif k == "hall_s":
        bld_hall(b, eave=5.5, ridge=3.5, style=st)
    elif k == "tower2":  # 二階楼閣
        box(f"{b['id']}_b1", b["w"], b["d"], 5.5, (x, y, 2.75), M["body"], rot=(0, 0, rz))
        hip_roof(f"{b['id']}_skirt", b["w"], b["d"], 1.6, (x, y, 5.5),
                 roof_mat(st), rot_z=rz, overhang=1.0)
        box(f"{b['id']}_b2", b["w"] * 0.8, b["d"] * 0.8, 5.0, (x, y, 7.1 + 2.5),
            M["body"], rot=(0, 0, rz))
        hip_roof(f"{b['id']}_roof", b["w"] * 0.8, b["d"] * 0.8, 3.4,
                 (x, y, 12.1), roof_mat(st), rot_z=rz, overhang=1.2)
    elif k == "pavilion":
        box(f"{b['id']}_body", b["w"], b["d"], 3.2, (x, y, 1.6), M["body"], rot=(0, 0, rz))
        hip_roof(f"{b['id']}_roof", b["w"], b["w"], 3.8, (x, y, 3.2), roof_mat(st))
    elif k == "corridor":  # 遊廊 (低い屋根付き)
        box(f"{b['id']}_body", b["w"], b["d"], 3.2, (x, y, 1.6), M["body"], rot=(0, 0, rz))
        hip_roof(f"{b['id']}_roof", b["w"], b["d"], 1.4, (x, y, 3.2),
                 roof_mat(st), rot_z=rz, overhang=0.8)
    elif k == "gallery":  # 高架通路 (白石高欄)
        box(f"{b['id']}_deck", b["w"], b["d"], 1.0, (x, y, 2.6), M["stone"], rot=(0, 0, rz))
        box(f"{b['id']}_rail", b["w"], b["d"] - 1.2, 1.0, (x, y, 3.6), M["wallw"], rot=(0, 0, rz))
        for i in range(int(b["w"] // 12)):
            px = x - b["w"] / 2 + 6 + i * 12
            box(f"{b['id']}_p{i}", 1.2, 1.2, 2.1, (px, y, 1.05), M["stone"])
    elif k == "yard":  # 白壁の小院: 塀+小殿+木
        w, d, t = b["w"], b["d"], 0.7
        for sfx, (cx, cy, sw, sd) in dict(
                s=(x, y - d / 2, w, t), n=(x, y + d / 2, w, t),
                w=(x - w / 2, y, t, d), e=(x + w / 2, y, t, d)).items():
            box(f"{b['id']}_w{sfx}", sw, sd, 3.2, (cx, cy, 1.6), M["wallw"])
        hall = dict(id=b["id"] + "_hall", x=x, y=y + d / 4, w=w * 0.45, d=9,
                    face="S", style=b.get("style", "grey"))
        bld_hall(hall, eave=5.0, ridge=3.2)
        if b.get("pond"):
            plane(b["id"] + "_pond", w * 0.4, d * 0.25, (x - w * 0.15, y - d * 0.2, 0.05),
                  M["water"])


for b in expand():
    build(b)

for wdef in WALLS:
    (x1, y1), (x2, y2) = wdef["p1"], wdef["p2"]
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    L = math.hypot(x2 - x1, y2 - y1)
    rz = math.atan2(y2 - y1, x2 - x1)
    box(wdef["id"], L, 0.8, wdef["h"], (cx, cy, wdef["h"] / 2), M["wallw"], rot=(0, 0, rz))

for i, (tx, ty, tr) in enumerate(TREES):
    cyl(f"trunk{i}", tr * 0.12, tr, (tx, ty, tr * 0.5), M["bronze"], verts=8)
    sphere(f"tree{i}", tr, (tx, ty, tr * 1.35), M["tree"], scale=(1, 1, 0.85))

plane("ground", 230, 330, (0, 138, 0), M["ground"])

# ---- ライティング (昼・様式確認用) ----
set_world((0.62, 0.70, 0.82), 0.55)
sun_light("sun", rot=(math.radians(50), 0, math.radians(140)), energy=3.0, angle_deg=3)

# ---- カメラ ----
cams = {
    "T": add_camera("cam_T", (-120, -55, 95), (0, 150, 0), lens=32),    # 俯瞰(南西上空)
    "A": add_camera("cam_A", (68, 16, 13), (-30, 180, 6), lens=26),     # b08_01全景の再現角(南東隅楼上)
    "F": add_camera("cam_F", (0, 66, 3.0), (0, 124, 12), lens=30),      # 正殿正対(中門の内側から)
    "P": add_camera("cam_P", (0, 138, 300), (0, 138.5, 0), lens=20),    # 真俯瞰(配置図・全域)
}
for c in cams.values():
    c.data.clip_end = 700.0

render_cli(cams, default_res="1600x900", exposure=0.8)
