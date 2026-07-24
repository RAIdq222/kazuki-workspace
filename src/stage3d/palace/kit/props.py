# 広場の点景 (香炉・甬道・石畳・人型・庭木)
import math

from stagelib import box, cyl, plane, sphere, torus


def censer(M, x, y, ground=0.0):
    """大香炉=三足の鼎 (胴+口縁+三足+双耳+蓋)。b08_17 中軸上."""
    # 台座は甬道(h0.5)より高くして上面の同一平面(z-fight)を避ける
    box("cen_plinth", 3.6, 3.6, 0.64, (x, y, ground + 0.32), M["stone"])
    z0 = ground + 0.64
    # 三足 (外側に開く)
    for i in range(3):
        a = math.radians(90 + i * 120)
        fx, fy = x + math.cos(a) * 0.85, y + math.sin(a) * 0.85
        cyl(f"cen_leg{i}", 0.17, 1.0, (fx, fy, z0 + 0.5), M["bronze"], verts=12,
            rot=(math.sin(a) * 0.22, -math.cos(a) * 0.22, 0))
    # 胴 (膨らみ) + 口縁
    sphere("cen_body", 1.25, (x, y, z0 + 1.55), M["bronze"], scale=(1.0, 1.0, 0.82))
    cyl("cen_neck", 1.08, 0.55, (x, y, z0 + 2.42), M["bronze"], verts=24)
    torus("cen_rim", 1.14, 0.10, (x, y, z0 + 2.72), M["bronze"])
    # 双耳 (立ち上がる取っ手)
    for sx in (-1, 1):
        torus(f"cen_ear{sx}", 0.34, 0.07, (x + sx * 1.05, y, z0 + 3.0),
              M["bronze"], rot=(0, math.pi / 2, 0))
    # 蓋 (ドーム+宝珠)
    sphere("cen_lid", 1.02, (x, y, z0 + 2.85), M["bronze"], scale=(1, 1, 0.45))
    sphere("cen_knob", 0.2, (x, y, z0 + 3.35), M["bronze"])
    # 石高欄の囲い (望柱+欄板)
    for i, (dx, dy, sw, sd) in enumerate([(0, -4.4, 9.6, 0.22), (0, 4.4, 9.6, 0.22),
                                          (-4.8, 0, 0.22, 8.5), (4.8, 0, 0.22, 8.5)]):
        box(f"cen_rail{i}", sw, sd, 0.75, (x + dx, y + dy, ground + 1.05), M["stone_w"])
    for i, (dx, dy) in enumerate([(-4.8, -4.4), (4.8, -4.4), (-4.8, 4.4), (4.8, 4.4),
                                  (0, -4.4), (0, 4.4), (-4.8, 0), (4.8, 0)]):
        box(f"cen_post{i}", 0.24, 0.24, 1.15, (x + dx, y + dy, ground + 1.25),
            M["stone_w"])
        sphere(f"cen_ph{i}", 0.13, (x + dx, y + dy, ground + 1.9), M["stone_w"])


def figures(M, spots):
    for i, (fx, fy) in enumerate(spots):
        cyl(f"fig{i}", 0.22, 1.3, (fx, fy, 0.65), M["fig"], verts=10)
        sphere(f"fig{i}_h", 0.16, (fx, fy, 1.48), M["fig"])


def court_context(M):
    """主殿前広場のコンテキスト一式 (単体検証・統合シーン共用)."""
    plane("plaza", 100, 92, (0, 110, 0.02), M["paving"])
    box("ongdo", 10, 16, 0.5, (0, 112, 0.25), M["stone"])
    censer(M, 0, 104)
    figures(M, [(2.5, 98), (-1.5, 96), (7.2, 126), (-7.2, 131)])
    for sx, ty in ((-1, 190), (1, 190)):
        sphere(f"ctx_tree{sx}", 4.5, (sx * 26, ty, 5.2), M["tree"], scale=(1, 1, 0.9))
