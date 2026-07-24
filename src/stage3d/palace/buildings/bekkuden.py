# 皇宮・別殿 (b08_19)。主殿前広場の左右に対で立つ長殿
# 様式: 橙琉璃瓦(単檐歇山)/朱円柱/簾壁/赤木欄干/オリーブ金彫刻帯/野面積み基壇
# build(M, x, y, facing) — facing: "W"=縁側が-X向き(東側の棟) / "E"=+X向き
# 単体実行: python src/stage3d/palace/buildings/bekkuden.py -- --views E,V ...
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PAL = os.path.dirname(_HERE)
sys.path.insert(0, os.path.dirname(_PAL))
sys.path.insert(0, _PAL)

from stagelib import box, cyl, plane  # noqa: E402
from kit.roofs import roof  # noqa: E402
from kit.structure import wood_rail, _link_copy  # noqa: E402

L, D = 42.0, 12.0     # 桁行×梁間
BASE_H = 1.4          # 野面積み基壇
COL_H = 4.2
N_BAY = 11


def build(M, x, y, facing="W", tag=""):
    """local系: 桁行=lx、正面(縁側)=-ly。facingでワールドへ回す."""
    th = {"W": -math.pi / 2, "E": math.pi / 2, "S": 0.0}[facing]
    c, s = math.cos(th), math.sin(th)

    def T(lx, ly, z):
        return (x + lx * c - ly * s, y + lx * s + ly * c, z)

    def R(base_rz=0.0):
        return (0, 0, base_rz + th)

    def RV(face_rz):  # 垂直面 (plane) 用
        return (math.pi / 2, 0, face_rz + th)

    nm = f"bek{tag}"
    # ---- 野面積み基壇+石段 ----
    box(f"{nm}_base", L + 3.6, D + 3.6, BASE_H, T(0, 0, BASE_H / 2), M["stone"],
        rot=R())
    plane(f"{nm}_basef", L + 3.7, BASE_H, T(0, -(D + 3.6) / 2 - 0.02, BASE_H / 2),
          M["rough_stone"], rot=RV(0))
    for sx in (-1, 1):
        plane(f"{nm}_bases{sx}", D + 3.7, BASE_H,
              T(sx * ((L + 3.6) / 2 + 0.02), 0, BASE_H / 2), M["rough_stone"],
              rot=RV(math.pi / 2))
        # 石段2連 (正面)
        for st in range(6):
            box(f"{nm}_st{sx}{st}", 3.0, 0.3, 0.23,
                T(sx * 10, -(D + 3.6) / 2 - 0.15 - st * 0.3,
                  BASE_H - 0.115 - st * 0.23), M["stone"], rot=R())
    plane(f"{nm}_floor", L + 2.4, D + 2.4, T(0, 0, BASE_H + 0.02), M["wood_floor"],
          rot=R())

    # ---- 朱柱列 (前後) ----
    bay = (L - 3.5) / N_BAY
    tpl_col = cyl(f"{nm}_tplc", 0.18, COL_H, (0, 0, -62), M["col"], verts=16)
    tpl_base = cyl(f"{nm}_tplb", 0.26, 0.25, (0, 0, -63), M["stone_w"], verts=12)
    xs = [-(L - 3.5) / 2 + i * bay for i in range(N_BAY + 1)]
    for i, lx in enumerate(xs):
        for ly, sfx in ((-D / 2 + 0.7, "f"), (D / 2 - 0.7, "b")):
            _link_copy(tpl_col, f"{nm}_c{sfx}{i}", T(lx, ly, BASE_H + COL_H / 2),
                       R())
            _link_copy(tpl_base, f"{nm}_cb{sfx}{i}", T(lx, ly, BASE_H + 0.12), R())
    tpl_col.location = (0, 0, -500)
    tpl_base.location = (0, 0, -500)

    # ---- 背面壁 (赤壁) と簾壁 (前面) ----
    box(f"{nm}_wall", L - 2.4, 0.4, COL_H, T(0, D / 2 - 0.7, BASE_H + COL_H / 2),
        M["red"], rot=R())
    plane(f"{nm}_wallf", L - 2.4, COL_H, T(0, D / 2 - 0.92, BASE_H + COL_H / 2),
          M["redwall"], rot=RV(0))
    for i in range(N_BAY):
        lx = (xs[i] + xs[i + 1]) / 2
        plane(f"{nm}_sud{i}", bay - 0.5, 2.6,
              T(lx, -D / 2 + 0.68, BASE_H + COL_H - 1.5), M["sudare"], rot=RV(0))
    # 赤木欄干 (縁側の前端+側端)
    e = (L + 2.4) / 2 - 0.15
    f_ = (D + 2.4) / 2 - 0.15
    wood_rail(f"{nm}_wrf1", T(-e, -f_, 0)[:2], T(-2.2, -f_, 0)[:2],
              BASE_H, M["wood_red"])
    wood_rail(f"{nm}_wrf2", T(2.2, -f_, 0)[:2], T(e, -f_, 0)[:2],
              BASE_H, M["wood_red"])
    for sx in (-1, 1):
        wood_rail(f"{nm}_wrs{sx}", T(sx * e, -f_, 0)[:2], T(sx * e, f_ * 0.55, 0)[:2],
                  BASE_H, M["wood_red"])

    # ---- 彫刻帯2段 (オリーブ金) → 屋根 ----
    z_beam = BASE_H + COL_H
    for bnm, zc, hgt, m in ((f"{nm}_g1", z_beam + 0.25, 0.5, M["frieze_o"]),
                            (f"{nm}_g2", z_beam + 0.85, 0.7, M["dougong"])):
        box(f"{bnm}_core", L + 0.3, D + 0.3, hgt, T(0, 0, zc), M["red"], rot=R())
        plane(f"{bnm}_f", L + 0.32, hgt, T(0, -D / 2 - 0.17, zc), m, rot=RV(0))
        plane(f"{bnm}_b", L + 0.32, hgt, T(0, D / 2 + 0.17, zc), m, rot=RV(math.pi))
        for sx in (-1, 1):
            plane(f"{bnm}_s{sx}", D + 0.32, hgt, T(sx * (L / 2 + 0.17), 0, zc), m,
                  rot=RV(math.pi / 2))
    ro = roof(f"{nm}_roof", L + 3.0, D + 3.0, 3.6, style="xieshan", xr=0.5,
              lift=0.45, reach=0.3, material=M["tile_amber"],
              ridge_mat=M["ridge_amber"], loc=(x, y, z_beam + 1.25))
    ro.rotation_euler = (0, 0, th)


if __name__ == "__main__":
    import bpy
    from stagelib import add_camera, sun_light, set_world, render_cli, plane as pl
    from kit.materials import make_materials

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    M = make_materials()
    pl("ground", 120, 80, (28, 110, 0.0), M["paving"])
    build(M, 28, 110, facing="W", tag="e")
    from kit import props
    props.figures(M, [(16, 104), (14, 118)])
    set_world((0.60, 0.72, 0.88), 0.68)
    sun_light("sun", rot=(math.radians(48), 0, math.radians(135)), energy=3.2,
              angle_deg=2)
    cams = {
        "E": add_camera("cam_E", (2, 110, 2.6), (28, 110, 5.0), lens=50),   # b08_19正対
        "V": add_camera("cam_V", (14, 124, 2.0), (26, 108, 4.0), lens=32),  # 縁側斜め
    }
    for cmm in cams.values():
        cmm.data.clip_end = 700.0
    render_cli(cams, default_res="1600x900", exposure=0.85)
