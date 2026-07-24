# 中間LODの汎用ビルダー (ディテール棟未着手の建物をキット屋根つきで置く)
import math

from stagelib import box, cyl, plane, sphere

from .roofs import roof
from .structure import _link_copy


def bands(name, M, x, y, w, d, z_base, g_h=0.5, d_h=0.7,
          frieze_key="frieze_o"):
    """額枋+斗栱帯を四周に回す (簡略版)."""
    for nm, zc, hgt, m in ((f"{name}_g", z_base + g_h / 2, g_h, M[frieze_key]),
                           (f"{name}_d", z_base + g_h + d_h / 2, d_h, M["dougong"])):
        box(f"{nm}_core", w + 0.3, d + 0.3, hgt, (x, y, zc), M["red"])
        plane(f"{nm}_f", w + 0.32, hgt, (x, y - d / 2 - 0.17, zc), m,
              rot=(math.pi / 2, 0, 0))
        plane(f"{nm}_b", w + 0.32, hgt, (x, y + d / 2 + 0.17, zc), m,
              rot=(math.pi / 2, 0, math.pi))
        for sx in (-1, 1):
            plane(f"{nm}_s{sx}", d + 0.32, hgt, (x + sx * (w / 2 + 0.17), y, zc), m,
                  rot=(math.pi / 2, 0, math.pi / 2))
    return z_base + g_h + d_h


def hall_generic(M, name, x, y, w, d, eave=5.4, ridge=4.2, terr_h=1.8,
                 tile="tile_amber", ridge_key="ridge_amber", steps=True):
    """中間LODの殿: 基壇+赤壁+帯+歇山屋根."""
    if terr_h > 0:
        box(f"{name}_terr", w + 5, d + 5, terr_h, (x, y, terr_h / 2), M["stone"])
        box(f"{name}_tc", w + 5.9, d + 5.9, 0.3, (x, y, terr_h - 0.13), M["stone_w"])
        if steps:
            for st in range(int(terr_h / 0.23)):
                box(f"{name}_st{st}", 6.0, 0.3, 0.23,
                    (x, y - (d + 5) / 2 - 0.15 - st * 0.3,
                     terr_h - 0.115 - st * 0.23), M["stone"])
    box(f"{name}_body", w, d, eave, (x, y, terr_h + eave / 2), M["red"])
    plane(f"{name}_wf", w, eave, (x, y - d / 2 - 0.01, terr_h + eave / 2),
          M["redwall"], rot=(math.pi / 2, 0, 0))
    z = bands(name, M, x, y, w, d, terr_h + eave)
    roof(f"{name}_roof", w + 2.8, d + 2.8, ridge, style="xieshan", xr=0.5,
         lift=0.45, reach=0.3, material=M[tile], ridge_mat=M[ridge_key],
         loc=(x, y, z + 0.15))


def tower2_generic(M, name, x, y, w, d, tile="tile_amber",
                   ridge_key="ridge_amber"):
    """中間LODの二階楼閣: 赤壁+腰屋根+上層+歇山."""
    box(f"{name}_b1", w, d, 4.8, (x, y, 2.4), M["red"])
    roof(f"{name}_skirt", w + 2.0, d + 2.0, 1.7, top_rect=(w * 0.42, d * 0.42),
         lift=0.3, reach=0.2, material=M[tile], ridge_mat=M[ridge_key],
         loc=(x, y, 4.8))
    box(f"{name}_b2", w * 0.76, d * 0.76, 3.8, (x, y, 6.5 + 1.9), M["red"])
    z = bands(name, M, x, y, w * 0.76, d * 0.76, 10.3, g_h=0.4, d_h=0.55)
    roof(f"{name}_roof", w * 0.8 + 1.8, d * 0.8 + 1.8, 3.0, style="xieshan",
         xr=0.5, lift=0.45, reach=0.3, material=M[tile], ridge_mat=M[ridge_key],
         loc=(x, y, z + 0.1))


def corridor_gen(M, name, p1, p2, width=3.4, col_h=2.9, tile="tile_amber"):
    """屋根付き廊 (遊廊/渡り廊下)。軸平行のみ対応."""
    x1, y1 = p1
    x2, y2 = p2
    length = math.hypot(x2 - x1, y2 - y1)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    along_x = abs(x2 - x1) > abs(y2 - y1)
    rz = 0.0 if along_x else math.pi / 2
    box(f"{name}_floor", length, width, 0.4, (cx, cy, 0.2), M["stone"], rot=(0, 0, rz))
    tpl = cyl(f"{name}_tplc", 0.13, col_h, (0, 0, -64), M["col"], verts=12)
    n = max(2, int(length / 3.0))
    for i in range(n + 1):
        t = i / n
        px, py = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        for s in (-1, 1):
            ox = 0 if along_x else s * (width / 2 - 0.25)
            oy = s * (width / 2 - 0.25) if along_x else 0
            _link_copy(tpl, f"{name}_c{i}{s}", (px + ox, py + oy, 0.4 + col_h / 2))
    tpl.location = (0, 0, -500)
    box(f"{name}_beam", length, width, 0.5, (cx, cy, 0.4 + col_h + 0.25), M["red"],
        rot=(0, 0, rz))
    r = roof(f"{name}_roof", length + 1.6, width + 1.6, 1.3, style="wudian",
             lift=0.25, reach=0.18, zone=1.6, material=M[tile],
             ridge_mat=M["ridge_amber"], loc=(cx, cy, 0.4 + col_h + 0.5),
             shiwei=False)
    r.rotation_euler = (0, 0, rz)


def yard_generic(M, name, x, y, w, d, hall_w=17, gate_side="E", trees=()):
    """白壁の院+小殿+開口。gate_side: 開口を設ける辺."""
    t = 0.6
    for sfx, (cx, cy, sw, sd) in dict(
            s=(x, y - d / 2, w, t), n=(x, y + d / 2, w, t),
            w=(x - w / 2, y, t, d), e=(x + w / 2, y, t, d)).items():
        if sfx == gate_side.lower():
            # 開口 (幅4) を中央に残して2分割
            if sfx in ("s", "n"):
                for k, xx in enumerate((x - w / 4 - 1, x + w / 4 + 1)):
                    box(f"{name}_w{sfx}{k}", w / 2 - 2, t, 3.0, (xx, cy, 1.5),
                        M["stone_w"])
            else:
                for k, yy in enumerate((y - d / 4 - 1, y + d / 4 + 1)):
                    box(f"{name}_w{sfx}{k}", t, d / 2 - 2, 3.0, (cx, yy, 1.5),
                        M["stone_w"])
            continue
        box(f"{name}_w{sfx}", sw, sd, 3.0, (cx, cy, 1.5), M["stone_w"])
        box(f"{name}_wc{sfx}", sw + 0.3 if sd == t else sw,
            sd + 0.3 if sw == t else sd, 0.3, (cx, cy, 3.1), M["ridge_amber"])
    hall_generic(M, f"{name}_hall", x, y + d / 4, hall_w, 9, eave=4.4, ridge=3.2,
                 terr_h=1.0)
    for i, (tx, ty, tr) in enumerate(trees):
        cyl(f"{name}_tt{i}", tr * 0.12, tr, (tx, ty, tr * 0.5), M["bronze"], verts=8)
        sphere(f"{name}_tr{i}", tr, (tx, ty, tr * 1.35), M["tree"],
               scale=(1, 1, 0.85))
