# 広場の点景 (香炉・甬道・石畳・人型・庭木)
from stagelib import box, cyl, plane, sphere


def censer(M, x, y, ground=0.0):
    """大香炉+石高欄囲い (b08_17 中軸上)."""
    cyl("censer", 1.35, 2.7, (x, y, ground + 0.8 + 1.35), M["bronze"], verts=24)
    cyl("censer_lid", 0.9, 0.9, (x, y, ground + 3.4), M["bronze"], verts=24, r2=0.35)
    for i, (dx, dy, sw, sd) in enumerate([(0, -4.4, 9.6, 0.35), (0, 4.4, 9.6, 0.35),
                                          (-4.8, 0, 0.35, 8.5), (4.8, 0, 0.35, 8.5)]):
        box(f"cen_rail{i}", sw, sd, 0.95, (x + dx, y + dy, ground + 1.3), M["stone_w"])


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
