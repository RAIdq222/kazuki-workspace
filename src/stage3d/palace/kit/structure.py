# 皇宮キット: 基壇・欄干・大階段・柱列 (リンク複製でポリ数を抑える)
import math

import bpy


def _link_copy(template, name, loc, rot=(0, 0, 0), scale=None):
    o = template.copy()  # obj.copy() はメッシュ共有 (竹林方式)
    o.name = name
    o.location = loc
    o.rotation_euler = rot
    if scale:
        o.scale = scale
    bpy.context.collection.objects.link(o)
    return o


def make_post_template(mat_stone, h=1.15, head_r=0.14):
    """望柱テンプレート (角柱+宝珠頭)。以後は _link_copy で増やす."""
    from stagelib import box, sphere
    post = box("tpl_post", 0.24, 0.24, h, (0, 0, -50), mat_stone)
    head = sphere("tpl_head", head_r, (0, 0, -50 + h / 2 + head_r * 0.7), mat_stone,
                  smooth=True)
    return post, head


def make_panel_template(mat_stone, h=0.85):
    from stagelib import box
    return box("tpl_panel", 1.06, 0.10, h, (0, 0, -52), mat_stone)


def balustrade_run(name, p1, p2, z, tpls, pitch=1.3):
    """p1→p2 (地上高z=床面) に望柱+欄板を並べる."""
    post, head, panel = tpls
    x1, y1 = p1
    x2, y2 = p2
    length = math.hypot(x2 - x1, y2 - y1)
    n = max(2, round(length / pitch) + 1)
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    rz = math.atan2(uy, ux)
    ph = post.dimensions.z / post.scale.z  # 実寸はテンプレ依存
    for i in range(n):
        t = i * length / (n - 1)
        px, py = x1 + ux * t, y1 + uy * t
        _link_copy(post, f"{name}_p{i}", (px, py, z + 1.15 / 2), (0, 0, rz))
        _link_copy(head, f"{name}_h{i}", (px, py, z + 1.15 + 0.10), (0, 0, rz))
        if i < n - 1:
            seg = length / (n - 1)
            mx, my = px + ux * seg / 2, py + uy * seg / 2
            _link_copy(panel, f"{name}_b{i}", (mx, my, z + 0.85 / 2), (0, 0, rz),
                       scale=(seg - 0.28, 0.10, 0.85))
    del ph


def terrace_tiered(name, x, y, w, d, h, mats, tiers=2, stair_gap=None):
    """高基壇: 段状の石壇+コーニス+高欄。stair_gap=(幅) で南辺中央を開ける."""
    from stagelib import box
    tpls = (*make_post_template(mats["stone_w"]), make_panel_template(mats["stone_w"]))
    z = 0.0
    for t in range(tiers):
        tw = w - 6 * t
        td = d - 6 * t
        th = h * (0.55 if t == 0 else 0.45) if tiers == 2 else h / tiers
        box(f"{name}_t{t}", tw, td, th, (x, y, z + th / 2), mats["stone"])
        # コーニスは天端を2cm高くして基壇上面との同一平面(z-fight→黒抜け)を回避
        box(f"{name}_t{t}c", tw + 0.9, td + 0.9, 0.32, (x, y, z + th - 0.14),
            mats["stone_w"])
        z += th
        # 高欄 (各段の縁、南辺は階段の開口を残す)
        ins = 0.55
        hw, hd = tw / 2 - ins, td / 2 - ins
        gap = (stair_gap or 0) / 2
        top = z
        balustrade_run(f"{name}_r{t}n", (x - hw, y + hd), (x + hw, y + hd), top, tpls)
        balustrade_run(f"{name}_r{t}w", (x - hw, y - hd), (x - hw, y + hd), top, tpls)
        balustrade_run(f"{name}_r{t}e", (x + hw, y - hd), (x + hw, y + hd), top, tpls)
        if gap > 0:
            balustrade_run(f"{name}_r{t}s1", (x - hw, y - hd), (x - gap, y - hd), top, tpls)
            balustrade_run(f"{name}_r{t}s2", (x + gap, y - hd), (x + hw, y - hd), top, tpls)
        else:
            balustrade_run(f"{name}_r{t}s", (x - hw, y - hd), (x + hw, y - hd), top, tpls)
    return z, tpls


def grand_stair_steps(name, x, y_front, h, mats, tpls, width=20, ongro_img=None,
                      fill_depth=6.4, ongro_w=6.0):
    """大階段 (b08_17構成): 中央=御路(雲紋の連続斜路)、左右=実段レーン、欄干4列.

    下(南)から上(北=基壇 y_front)へ登る。踊り場1つ。最上段の背後には詰め壇。
    """
    from stagelib import box, plane, mat_image
    step_h, step_d = 0.146, 0.32
    n_total = int(h / step_h)
    n1 = n_total // 2
    run = n_total * step_d + 2.9  # 総水平距離 (踊り場込み)
    ang = math.atan2(h, run)
    slope = math.hypot(run, h)
    lane_w = (width - ongro_w) / 2 - 0.6
    # ---- 左右レーンの実段 ----
    tpl_step = box("tpl_step", lane_w, step_d, step_h, (0, 0, -54), mats["stone"])
    for sx in (-1, 1):
        px = x + sx * (ongro_w / 2 + 0.6 + lane_w / 2)
        y = y_front - run
        z = 0.0
        for i in range(n_total):
            if i == n1:  # 踊り場
                box(f"{name}_land{sx}", lane_w + 1, 3.2, step_h,
                    (px, y + 1.45, z + step_h / 2), mats["stone"])
                y += 2.9
            _link_copy(tpl_step, f"{name}_s{sx}_{i}",
                       (px, y + step_d / 2, z + step_h / 2))
            y += step_d
            z += step_h
    tpl_step.location = (0, 0, -500)
    # ---- 中央の御路 (連続斜路+雲紋) ----
    ramp = box(f"{name}_ongro_base", ongro_w, slope + 0.4, 0.5,
               (x, y_front - run / 2, h / 2 - 0.18), mats["stone"])
    ramp.rotation_euler = (ang, 0, 0)
    if ongro_img:
        mo = mat_image("kw_ongro", ongro_img, rough=0.85)
        pl = plane(f"{name}_ongro", ongro_w - 0.5, slope,
                   (x, y_front - run / 2, h / 2 + 0.10), mo)
        pl.rotation_euler = (ang, 0, 0)
    if fill_depth > 0:  # 最上段の背後の詰め壇 (2段基壇の凹みまで)
        box(f"{name}_fill", width + 3, fill_depth, h,
            (x, y_front + fill_depth / 2, h / 2), mats["stone"])
    # ---- 垂帯石 (外縁のみ) ----
    for sx in (-1, 1):
        fl = box(f"{name}_flank{sx}", 0.5, slope + 0.6, 1.5,
                 (x + sx * (width / 2 + 0.2), y_front - run / 2, h / 2 - 0.42),
                 mats["stone"])
        fl.rotation_euler = (ang, 0, 0)
    # ---- 欄干4列: 外縁± と 御路の両脇± ----
    for px, tag in ((x - width / 2 - 0.4, "w"), (x + width / 2 + 0.4, "e"),
                    (x - ongro_w / 2 - 0.3, "cw"), (x + ongro_w / 2 + 0.3, "ce")):
        for nm, tt, hh, zoff in ((f"{name}_rb{tag}", 0.16, 0.5, 0.30),
                                 (f"{name}_rc{tag}", 0.30, 0.15, 0.62)):
            r = box(nm, tt, slope + 0.6, hh,
                    (px, y_front - run / 2, h / 2 + zoff), mats["stone_w"])
            r.rotation_euler = (ang, 0, 0)
        n_posts = max(6, int(slope / 2.6))
        for i in range(n_posts + 1):
            t = i / n_posts  # t=0が基壇側(上)、t=1が広場側(下)
            _link_copy(tpls[0], f"{name}_rp{tag}{i}",
                       (px, y_front - run * t, h * (1 - t) + 0.50))
            _link_copy(tpls[1], f"{name}_rh{tag}{i}",
                       (px, y_front - run * t, h * (1 - t) + 1.15))


def wood_rail(name, p1, p2, z, mat_wood, h=0.85, pitch=1.4):
    """赤木欄干 (角柱+上下2段の貫)。別殿・平座・回廊用."""
    from stagelib import box
    x1, y1 = p1
    x2, y2 = p2
    length = math.hypot(x2 - x1, y2 - y1)
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    rz = math.atan2(uy, ux)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    box(f"{name}_top", length, 0.12, 0.10, (cx, cy, z + h), mat_wood, rot=(0, 0, rz))
    box(f"{name}_mid", length, 0.08, 0.07, (cx, cy, z + h * 0.55), mat_wood,
        rot=(0, 0, rz))
    tpl = box(f"{name}_tpl", 0.10, 0.10, h, (0, 0, -58), mat_wood)
    n = max(2, round(length / pitch) + 1)
    for i in range(n):
        t = i * length / (n - 1)
        _link_copy(tpl, f"{name}_p{i}", (x1 + ux * t, y1 + uy * t, z + h / 2))
    tpl.location = (0, 0, -500)


def column_row(name, x0, y, bays, mat_col, mat_gold, z0, col_h, r=0.28):
    """柱列: bays=柱間幅リスト。戻り値=柱のx座標リスト."""
    from stagelib import cyl, torus
    xs = [x0]
    for b in bays:
        xs.append(xs[-1] + b)
    tpl = cyl("tpl_col", r, col_h, (0, 0, -56), mat_col, verts=20)
    for i, cx in enumerate(xs):
        _link_copy(tpl, f"{name}_c{i}", (cx, y, z0 + col_h / 2))
        torus(f"{name}_g{i}", r * 1.05, 0.035, (cx, y, z0 + col_h - 0.5), mat_gold)
    tpl.location = (0, 0, -500)
    return xs
