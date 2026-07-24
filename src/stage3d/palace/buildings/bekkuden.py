# 皇宮・別殿 (b08_19)。主殿前広場の左右に対で立つ長殿
# 立面の積層 (Issue #6 P0-3, 下から): 野面積み基壇(切石帯で押さえ)/切石階段/
#   厚い縁側床/赤木欄干(親柱+縦子)/朱円柱+簾壁(軒影)/桁帯/赤壁+柱型+
#   オリーブ金帯2本/持送り/軒裏/橙瓦屋根(瓦当列)
# build(M, x, y, facing) — facing: "W"=縁側が-X向き(東側の棟) / "E"=+X向き
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PAL = os.path.dirname(_HERE)
sys.path.insert(0, os.path.dirname(_PAL))
sys.path.insert(0, _PAL)

from stagelib import box, cyl, plane, torus  # noqa: E402
from kit.roofs import roof  # noqa: E402
from kit.structure import wood_rail, _link_copy  # noqa: E402

L, D = 42.0, 12.0     # 桁行×梁間
BASE_H = 2.0          # 野面積み基壇 (b08_19: 画面下部で十分読める高さ)
FLOOR_T = 0.35        # 縁側床の厚み
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
    z_floor = BASE_H + FLOOR_T

    # ---- 野面積み基壇 (切石の水平帯で押さえる) + 切石階段 ----
    box(f"{nm}_base", L + 3.6, D + 3.6, BASE_H, T(0, 0, BASE_H / 2), M["stone"],
        rot=R())
    box(f"{nm}_basecap", L + 3.9, D + 3.9, 0.26, T(0, 0, BASE_H - 0.11),
        M["stone_w"], rot=R())
    plane(f"{nm}_basef", L + 3.7, BASE_H - 0.2, T(0, -(D + 3.6) / 2 - 0.02,
                                                  (BASE_H - 0.2) / 2),
          M["rough_stone"], rot=RV(0))
    for sxx in (-1, 1):
        plane(f"{nm}_bases{sxx}", D + 3.7, BASE_H - 0.2,
              T(sxx * ((L + 3.6) / 2 + 0.02), 0, (BASE_H - 0.2) / 2),
              M["rough_stone"], rot=RV(math.pi / 2))
        for st in range(9):  # 石段 (整形切石)
            box(f"{nm}_st{sxx}{st}", 3.0, 0.3, 0.225,
                T(sxx * 10, -(D + 3.6) / 2 - 0.15 - st * 0.3,
                  BASE_H - 0.112 - st * 0.225), M["stone_w"], rot=R())

    # ---- 厚い縁側床 (木) ----
    box(f"{nm}_floor", L + 2.4, D + 2.4, FLOOR_T, T(0, 0, BASE_H + FLOOR_T / 2),
        M["wood_floor"], rot=R())

    # ---- 朱円柱 (太め r0.24+柱礎+金環) ----
    bay = (L - 3.5) / N_BAY
    tpl_col = cyl(f"{nm}_tplc", 0.24, COL_H, (0, 0, -62), M["col"], verts=18)
    tpl_base = cyl(f"{nm}_tplb", 0.34, 0.26, (0, 0, -63), M["stone_w"], verts=14)
    xs = [-(L - 3.5) / 2 + i * bay for i in range(N_BAY + 1)]
    for i, lx in enumerate(xs):
        for ly, sfx in ((-D / 2 + 0.7, "f"), (D / 2 - 0.7, "b")):
            _link_copy(tpl_col, f"{nm}_c{sfx}{i}", T(lx, ly, z_floor + COL_H / 2),
                       R())
            _link_copy(tpl_base, f"{nm}_cb{sfx}{i}", T(lx, ly, z_floor + 0.13), R())
        torus(f"{nm}_cg{i}", 0.25, 0.03, T(lx, -D / 2 + 0.7, z_floor + COL_H - 0.4),
              M["gold"])
    tpl_col.location = (0, 0, -500)
    tpl_base.location = (0, 0, -500)

    # ---- 背面壁 (赤壁) と簾壁 (前面、上端に軒影の暗帯) ----
    box(f"{nm}_wall", L - 2.4, 0.4, COL_H, T(0, D / 2 - 0.7, z_floor + COL_H / 2),
        M["red"], rot=R())
    plane(f"{nm}_wallf", L - 2.4, COL_H, T(0, D / 2 - 0.92, z_floor + COL_H / 2),
          M["redwall"], rot=RV(0))
    for i in range(N_BAY):
        lx = (xs[i] + xs[i + 1]) / 2
        plane(f"{nm}_sud{i}", bay - 0.55, 2.5,
              T(lx, -D / 2 + 0.68, z_floor + COL_H - 1.45), M["sudare"], rot=RV(0))
        plane(f"{nm}_shade{i}", bay - 0.55, 0.6,
              T(lx, -D / 2 + 0.66, z_floor + COL_H - 0.45), M["void"], rot=RV(0))

    # ---- 赤木欄干 (縁側の前端+側端、縦子つき)。開口は階段位置 (±10) ----
    e = (L + 2.4) / 2 - 0.15
    f_ = (D + 2.4) / 2 - 0.15
    wood_rail(f"{nm}_wrf1", T(-e, -f_, 0)[:2], T(-11.7, -f_, 0)[:2],
              z_floor, M["wood_red"])
    wood_rail(f"{nm}_wrf2", T(-8.3, -f_, 0)[:2], T(8.3, -f_, 0)[:2],
              z_floor, M["wood_red"])
    wood_rail(f"{nm}_wrf3", T(11.7, -f_, 0)[:2], T(e, -f_, 0)[:2],
              z_floor, M["wood_red"])
    for sxx in (-1, 1):
        wood_rail(f"{nm}_wrs{sxx}", T(sxx * e, -f_, 0)[:2],
                  T(sxx * e, f_ * 0.55, 0)[:2], z_floor, M["wood_red"])

    # ---- 上部の積層: 桁帯 → 赤壁+柱型+金帯2本 → 持送り → 軒裏 ----
    z_beam = z_floor + COL_H
    box(f"{nm}_keta", L + 0.6, D + 0.6, 0.32, T(0, 0, z_beam + 0.16),
        M["wood_tan"], rot=R())
    z0r = z_beam + 0.32
    RW_H = 1.5
    box(f"{nm}_rw", L + 0.3, D + 0.3, RW_H, T(0, 0, z0r + RW_H / 2), M["red"],
        rot=R())
    plane(f"{nm}_rwf", L + 0.32, RW_H, T(0, -(D + 0.3) / 2 - 0.02, z0r + RW_H / 2),
          M["redwall"], rot=RV(0))
    for znm, zz in ((f"{nm}_gb1", z0r + 0.18), (f"{nm}_gb2", z0r + RW_H - 0.18)):
        plane(znm, L + 0.34, 0.34, T(0, -(D + 0.3) / 2 - 0.05, zz), M["frieze_o"],
              rot=RV(0))
        for sxx in (-1, 1):
            plane(f"{znm}s{sxx}", D + 0.34, 0.34,
                  T(sxx * ((L + 0.3) / 2 + 0.05), 0, zz), M["frieze_o"],
                  rot=RV(math.pi / 2))
    tpl_pl = box(f"{nm}_tplp", 0.30, 0.14, RW_H, (0, 0, -76), M["wood_dark"])
    tpl_bk = box(f"{nm}_tplk", 0.36, 0.5, 0.42, (0, 0, -77), M["wood_dark"])
    for i, lx in enumerate(xs):  # 柱型 (壁面の縦分割) と持送り
        _link_copy(tpl_pl, f"{nm}_pl{i}",
                   T(lx, -(D + 0.3) / 2 - 0.08, z0r + RW_H / 2), R())
        _link_copy(tpl_bk, f"{nm}_bk{i}",
                   T(lx, -(D + 0.3) / 2 - 0.12, z0r + RW_H + 0.21), R())
    tpl_pl.location = (0, 0, -500)
    tpl_bk.location = (0, 0, -500)
    box(f"{nm}_soffit", L + 1.8, D + 1.8, 0.3, T(0, 0, z0r + RW_H + 0.55),
        M["wood_tan"], rot=R())

    # ---- 橙瓦屋根 (単檐歇山、瓦当列つき) ----
    ro = roof(f"{nm}_roof", L + 3.0, D + 3.0, 3.6, style="xieshan", xr=0.5,
              lift=0.45, reach=0.3, material=M["tile_amber"],
              ridge_mat=M["ridge_amber"], loc=(x, y, z0r + RW_H + 0.85))
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
        "E": add_camera("cam_E", (10, 116, 1.3), (28, 112, 3.5), lens=55),
        "V": add_camera("cam_V", (14, 124, 2.0), (26, 108, 4.0), lens=32),
    }
    for cmm in cams.values():
        cmm.data.clip_end = 700.0
    render_cli(cams, default_res="1600x996", exposure=0.85)
