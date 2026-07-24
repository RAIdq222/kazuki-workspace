# 反り屋根ジェネレータ (Phase 0.5 スパイク → Phase 1 キット本体)
#
# 方式: u×v グリッドロフト
#   v方向(軒→棟) = 清式挙架の離散列 (0.5→0.65→0.75→0.9) を積分した凹カーブ
#   u方向(桁行)  = 各vで平面外形を補間。廡殿(寄棟)は45°の隅棟線に頂点を吸着、
#                  歇山(入母屋)は xr 以降で妻側の縮みを凍結し山花板で塞ぐ
#   翼角起翘     = 隅からの平面距離 zone 内で t³ カーブで持ち上げ+外に突き出し
#                  (三次なので中央の軒線は完全に水平を保つ = 北方官式)
# 検証: palace/roof_spike.py (--style line でボードのシルエットと重ね比較)
import math

import bmesh
import bpy


def _profile(d_half, h, ratios, sub):
    """挙架カーブ: [(s=水平進行0..1, z=高さ)] を返す。z は h にスケール."""
    n = len(ratios)
    run = d_half / n
    pts = [(0.0, 0.0)]
    z = 0.0
    for r in ratios:
        z += run * r
        pts.append((pts[-1][0] + run, z))
    scale = h / z
    pts = [(s / d_half, zz * scale) for s, zz in pts]
    out = []
    for i in range(len(pts) - 1):
        (s0, z0), (s1, z1) = pts[i], pts[i + 1]
        for k in range(sub):
            f = k / sub
            out.append((s0 + (s1 - s0) * f, z0 + (z1 - z0) * f))
    out.append(pts[-1])
    return out  # nv 行


def roof(name, w, d, h, style="xieshan", ratios=(0.5, 0.65, 0.75, 0.9), sub=3,
         lift=0.45, reach=0.3, zone=None, xr=0.45, nu=29,
         material=None, loc=(0, 0, 0), rot_z=0.0, ridge_mat=None,
         with_ridges=True, shiwei=True, top_rect=None):
    """反り屋根 (w=桁行全幅, d=梁間全奥行, h=軒から棟までの高さ)。w>=d 前提.

    style: 'wudian'=廡殿(寄棟) / 'xieshan'=歇山(入母屋)
    lift/reach: 翼角の持ち上げ/突き出し量(m)。zone: 反りが効く隅からの距離(m)
    xr: 歇山の収山位置 (水平進行の割合)
    top_rect: (sx_half, sy_half) を与えると腰屋根(裳階)になる —
      頂点まで閉じずに上端がこの矩形(=上層の壁面)で止まり、博脊が回る。
      重檐の下層は必ずこれを使う (独立屋根で閉じると上層が浮いて見える)
    """
    zone = zone if zone is not None else min(w, d) * 0.32
    rows = _profile(d / 2, h, ratios, sub)
    nv = len(rows)

    def extents(s):
        if top_rect:
            sxh, syh = top_rect
            hx = w / 2 - (w / 2 - sxh) * s
            hy = d / 2 - (d / 2 - syh) * s
            return hx, hy
        hy = d / 2 * (1 - s)
        if style == "xieshan" and s > xr:
            hx = w / 2 - d / 2 * xr
        else:
            hx = w / 2 - d / 2 * s
        return hx, hy

    def corner_mod(x, y, s, z):
        """翼角: 隅からの平面距離で持ち上げ+突き出し."""
        hx, hy = extents(s)
        dist = math.hypot(hx - abs(x), hy - abs(y))
        t = max(0.0, 1.0 - dist / zone)
        fade = (1.0 - s) ** 2
        k = (t ** 3) * fade
        sx = 1 if x >= 0 else -1
        sy = 1 if y >= 0 else -1
        return (x + sx * reach * k * 0.7, y + sy * reach * k, z + lift * k)

    verts, faces = [], []

    def add_grid(pts_grid):
        """pts_grid[iv][iu] を面に張る (縮退四角は remove_doubles で潰れる)."""
        base = len(verts)
        nvv = len(pts_grid)
        nuu = len(pts_grid[0])
        for row in pts_grid:
            verts.extend(row)
        for iv in range(nvv - 1):
            for iu in range(nuu - 1):
                a = base + iv * nuu + iu
                faces.append((a, a + 1, a + nuu + 1, a + nuu))

    # 前後スロープ
    for sy in (-1, 1):
        grid = []
        for s, z in rows:
            hx, hy = extents(s)
            row = []
            for iu in range(nu):
                u = -1 + 2 * iu / (nu - 1)
                x = max(-hx, min(hx, u * w / 2))
                row.append(corner_mod(x, sy * hy, s, z))
            grid.append(row)
        add_grid(grid)

    # 妻側スロープ (歇山は xr まで、腰屋根は全行)
    side_rows = [(s, z) for s, z in rows
                 if top_rect or style == "wudian" or s <= xr + 1e-6]
    nus = max(9, nu // 2)
    for sx in (-1, 1):
        grid = []
        for s, z in side_rows:
            hx, hy = extents(s)
            row = []
            for iu in range(nus):
                u = -1 + 2 * iu / (nus - 1)
                y = max(-hy, min(hy, u * d / 2))
                row.append(corner_mod(sx * hx, y, s, z))
            grid.append(row)
        add_grid(grid)

    # 歇山の山花 (三角板)。下端を0.35下げ・面をほぼ外面に置いて隙間を塞ぐ
    if style == "xieshan" and not top_rect:
        s_x = side_rows[-1][0]
        z_x = side_rows[-1][1]
        hx_f, hy_x = extents(s_x)
        for sx in (-1, 1):
            base = len(verts)
            gx = sx * (hx_f - 0.02)
            verts.extend([(gx, -hy_x - 0.2, z_x - 0.35), (gx, hy_x + 0.2, z_x - 0.35),
                          (gx, 0, h)])
            faces.append((base, base + 1, base + 2))

    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.02)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    o = bpy.data.objects.new(name, me)
    o.location = loc
    o.rotation_euler = (0, 0, rot_z)
    if material:
        o.data.materials.append(material)
    bpy.context.collection.objects.link(o)

    if top_rect:
        # 博脊: 腰屋根の上端(壁との取り合い)を一周する水平の見切り棟
        sxh, syh = top_rect
        ring = [(-sxh, -syh, h), (sxh, -syh, h), (sxh, syh, h),
                (-sxh, syh, h), (-sxh, -syh, h)]
        _poly_tube(f"{name}_boseki", [(px, py, pz + 0.08) for px, py, pz in ring],
                   0.18, ridge_mat or material, o)
    elif with_ridges:
        _ridges(name, w, d, h, style, rows, extents, corner_mod,
                ridge_mat or material, o, shiwei)
    return o


def _poly_tube(name, pts, r, material, parent):
    cu = bpy.data.curves.new(name, type="CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = r
    cu.bevel_resolution = 2
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (*p, 1)
    o = bpy.data.objects.new(name, cu)
    if material:
        o.data.materials.append(material)
    bpy.context.collection.objects.link(o)
    o.parent = parent
    return o


def _ridges(name, w, d, h, style, rows, extents, corner_mod, material, parent,
            shiwei):
    """正脊・垂脊(戗脊)・鴟尾。カーブ+ベベルの略式."""
    if style == "xieshan":
        ridge_half = extents(1.0)[0]
    else:
        ridge_half = max(w / 2 - d / 2, 0.3)
    # 正脊
    _poly_tube(f"{name}_seiki", [(-ridge_half, 0, h + 0.12), (ridge_half, 0, h + 0.12)],
               0.28, material, parent)
    # 垂脊/戗脊: 隅の頂点列に沿う
    for sx in (-1, 1):
        for sy in (-1, 1):
            pts = []
            for s, z in rows:
                hx, hy = extents(s)
                if style == "xieshan" and s > 0.45:
                    break
                pts.append(corner_mod(sx * hx, sy * hy, s, z))
            if style == "xieshan":  # 垂脊: 山花の縁を棟端まで
                pts.append((sx * ridge_half, 0, h + 0.05))
            else:
                pts.append((sx * ridge_half, 0, h + 0.05))
            _poly_tube(f"{name}_sui_{sx}{sy}", [(px, py, pz + 0.1) for px, py, pz in pts],
                       0.2, material, parent)
    # 鴟尾 (南朝風に大ぶり)。屋根の規模に追従してスケール
    if shiwei:
        sc = max(0.45, min(1.2, w / 30.0))
        for sx in (-1, 1):
            fin = bpy.data.meshes.new(f"{name}_shiwei{sx}")
            x0 = sx * ridge_half
            ww = 0.35 * sc
            pts = [
                (x0 - ww, -0.0, h - 0.4 * sc), (x0 + ww * 1.6, 0, h - 0.4 * sc),
                (x0 + ww * 1.6, 0, h + 1.3 * sc), (x0 + ww * 0.9, 0, h + 1.55 * sc),
                (x0 - ww * 0.4, 0, h + 1.45 * sc), (x0 - ww, 0, h + 0.9 * sc),
            ]
            verts = [(px, -ww / 2, pz) for px, py, pz in pts] + \
                    [(px, ww / 2, pz) for px, py, pz in pts]
            n = len(pts)
            faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
            for i in range(n):
                j = (i + 1) % n
                faces.append((i, j, n + j, n + i))
            fin.from_pydata(verts, [], faces)
            fin.update()
            o = bpy.data.objects.new(f"{name}_shiwei{sx}", fin)
            if material:
                o.data.materials.append(material)
            bpy.context.collection.objects.link(o)
            o.parent = parent
