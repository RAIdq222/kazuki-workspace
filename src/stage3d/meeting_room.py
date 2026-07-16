# -*- coding: utf-8 -*-
"""美術ボード「夜の会議室」の3Dステージ化。

ボードの構成: 暗い木目パネルの会議室。左壁に縦ブラインドの窓×2(外光が透ける)、
正面に収納扉の列と両開きドア(欄間ガラス付き)、右壁に発光するスクリーン、
折り上げ天井+ダウンライト、中央に楕円の会議テーブル(配線スロット)とチェア、
タイルカーペット。夜の青緑トーン。

部屋 (単位m): X 0..6.6 (幅, 西=x小 が窓壁), Y 0..7.0 (奥行, 北=y大 がドア壁), 壁高 2.9
実行例:
    python3 src/stage3d/meeting_room.py -- --views A --samples 32 --res 1280x800
"""
import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from stagelib import (reset_scene, mat, mat_wood, mat_plaster,  # noqa: E402
                      box, cyl, sphere, plane,
                      add_camera, area_light, set_world, render_cli)

R = random.Random(7)

# 時間帯 (--time morning|evening|night)。render_cli の前に取り出す
TIME = "night"
if "--time" in sys.argv:
    i = sys.argv.index("--time")
    TIME = sys.argv[i + 1]
    del sys.argv[i:i + 2]

ROOM_X = 6.6
ROOM_Y = 7.0
WALL_H = 2.9

PAL = {
    "wood_wall":  (0.110, 0.085, 0.055),   # 暗い木目パネル
    "wood_trim":  (0.060, 0.048, 0.034),
    "wood_table": (0.285, 0.175, 0.095),   # テーブル天板
    "carpet":     (0.150, 0.160, 0.165),   # 青灰のタイルカーペット
    "chair":      (0.035, 0.055, 0.055),   # 青緑の黒レザー
    "metal":      (0.250, 0.260, 0.270),
    "ceiling":    (0.050, 0.058, 0.064),
    "blind":      (0.520, 0.560, 0.600),   # ブラインド(透過光で明るく見える)
    "glow_win":   (0.700, 0.760, 0.850),   # 窓の外光 (青白)
    "glow_scr":   (0.780, 0.850, 0.820),   # スクリーン (緑白)
}


def build_shell():
    # 床: タイルカーペット (チェッカー柄をプロシージャルで)
    key = "m_carpet"
    m = bpy.data.materials.new(key)
    m.use_nodes = True
    m["fallback"] = list(PAL["carpet"])
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 1.0
    tc = nt.nodes.new("ShaderNodeTexCoord")
    ck = nt.nodes.new("ShaderNodeTexChecker")
    ck.inputs["Scale"].default_value = 12.0  # 0.5mタイル相当
    c = PAL["carpet"]
    ck.inputs["Color1"].default_value = (*[v * 0.95 for v in c], 1)
    ck.inputs["Color2"].default_value = (*[v * 1.05 for v in c], 1)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 250.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.05
    nt.links.new(tc.outputs["Object"], ck.inputs["Vector"])
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(ck.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    plane("floor", ROOM_X, ROOM_Y, (ROOM_X / 2, ROOM_Y / 2, 0), m)

    # 壁: 暗い木目パネル (縦木目) + 幅木
    wm = mat_wood("wood_wall", PAL["wood_wall"], rough=0.5, scale=1.0, along="X",
                  strength=0.10)
    trim = mat_wood("wood_trim", PAL["wood_trim"], rough=0.55, scale=2.0)
    for nm, sx, sy, loc in [
        ("wall_W", 0.06, ROOM_Y, (-0.03, ROOM_Y / 2, 0)),
        ("wall_E", 0.06, ROOM_Y, (ROOM_X + 0.03, ROOM_Y / 2, 0)),
        ("wall_N", ROOM_X, 0.06, (ROOM_X / 2, ROOM_Y + 0.03, 0)),
        ("wall_S", ROOM_X, 0.06, (ROOM_X / 2, -0.03, 0)),
    ]:
        box(nm, sx, sy, WALL_H, (loc[0], loc[1], WALL_H / 2), wm)
        box(nm + "_base", sx + 0.03, sy + 0.03 if sy > 1 else sy, 0.10,
            (loc[0], loc[1], 0.05), trim)
    # パネルの目地 (西壁・東壁・北壁に細い縦トリム)
    for y in [0.9 + i * 0.75 for i in range(9)]:
        box(f"seamW_{y:.1f}", 0.02, 0.02, WALL_H, (0.055, y, WALL_H / 2), trim)
        box(f"seamE_{y:.1f}", 0.02, 0.02, WALL_H, (ROOM_X - 0.055, y, WALL_H / 2), trim)

    # 天井: 外周フラット + 中央の折り上げ(一段高い)
    cm = mat("ceiling", PAL["ceiling"], rough=0.9)
    plane("ceil_outer", ROOM_X, ROOM_Y, (ROOM_X / 2, ROOM_Y / 2, WALL_H), cm)
    # 折り上げ部分: 内側リング(壁)+上面
    ix0, ix1, iy0, iy1 = 1.3, ROOM_X - 1.3, 1.6, ROOM_Y - 1.6
    # 二段の折り上げ (設定資料メモ: 段差のある折り上げ天井)
    jx0, jx1, jy0, jy1 = ix0 + 0.55, ix1 - 0.55, iy0 + 0.55, iy1 - 0.55
    plane("ceil_mid", ix1 - ix0, iy1 - iy0,
          ((ix0 + ix1) / 2, (iy0 + iy1) / 2, WALL_H + 0.16), cm)
    plane("ceil_inner", jx1 - jx0, jy1 - jy0,
          ((jx0 + jx1) / 2, (jy0 + jy1) / 2, WALL_H + 0.30), cm)
    for nm2, sx2, sy2, loc2 in [
        ("coffer2S", jx1 - jx0, 0.04, ((jx0 + jx1) / 2, jy0, 0)),
        ("coffer2N", jx1 - jx0, 0.04, ((jx0 + jx1) / 2, jy1, 0)),
        ("coffer2W", 0.04, jy1 - jy0, (jx0, (jy0 + jy1) / 2, 0)),
        ("coffer2E", 0.04, jy1 - jy0, (jx1, (jy0 + jy1) / 2, 0)),
    ]:
        box(nm2, sx2, sy2, 0.14, (loc2[0], loc2[1], WALL_H + 0.23),
            mat("ceiling", PAL["ceiling"], rough=0.9))
    for nm, sx, sy, loc in [
        ("cofferS", ix1 - ix0, 0.04, ((ix0 + ix1) / 2, iy0, 0)),
        ("cofferN", ix1 - ix0, 0.04, ((ix0 + ix1) / 2, iy1, 0)),
        ("cofferW", 0.04, iy1 - iy0, (ix0, (iy0 + iy1) / 2, 0)),
        ("cofferE", 0.04, iy1 - iy0, (ix1, (iy0 + iy1) / 2, 0)),
    ]:
        box(nm, sx, sy, 0.28, (loc[0], loc[1], WALL_H + 0.14), trim)
    # ダウンライト (外周天井に発光ディスク)
    dl_emit = {"morning": 0.0, "evening": 3.0, "night": 6.0}.get(TIME, 6.0)
    dl = mat("downlight", (0.95, 0.93, 0.85), rough=0.4, emit=dl_emit)
    for x, y in [(0.65, 1.2), (0.65, 3.0), (0.65, 4.8), (0.65, 6.4),
                 (ROOM_X - 0.65, 1.2), (ROOM_X - 0.65, 3.0), (ROOM_X - 0.65, 4.8),
                 (ROOM_X - 0.65, 6.4), (2.5, 6.6), (4.3, 6.6), (2.5, 0.5), (4.3, 0.5)]:
        cyl(f"dl_{x:.1f}_{y:.1f}", 0.07, 0.02, (x, y, WALL_H - 0.005),
            mat("dl_rim", (0.05, 0.05, 0.05), rough=0.4), verts=12)
        cyl(f"dlg_{x:.1f}_{y:.1f}", 0.05, 0.015, (x, y, WALL_H - 0.012), dl, verts=12)


def window_with_blinds(idx, cy, w=1.7, z0=0.9, z1=2.5):
    """西壁の窓: 枠 + 縦ブラインド + 背後の外光."""
    trim = mat_wood("wood_trim", PAL["wood_trim"], rough=0.55, scale=2.0)
    glow_defs = {
        "morning": ((1.00, 0.92, 0.74), 5.5),
        "evening": ((1.00, 0.62, 0.38), 4.0),
        "night":   (PAL["glow_win"], 2.6),
    }
    gc, ge = glow_defs.get(TIME, glow_defs["night"])
    glow = mat("glow_win", gc, rough=0.9, emit=ge)
    bm = mat("blind", PAL["blind"], rough=0.8)
    h = z1 - z0
    zc = (z0 + z1) / 2
    # 窓枠 (壁より少し奥へ)
    box(f"win{idx}_frame_t", 0.10, w + 0.16, 0.07, (0.05, cy, z1 + 0.035), trim)
    box(f"win{idx}_frame_b", 0.10, w + 0.16, 0.07, (0.05, cy, z0 - 0.035), trim)
    for dy in (-w / 2 - 0.045, w / 2 + 0.045):
        box(f"win{idx}_frame_{dy:.2f}", 0.10, 0.07, h + 0.14, (0.05, cy + dy, zc), trim)
    # 外光面
    plane(f"win{idx}_glow", h - 0.08, w - 0.10, (0.02, cy, zc), glow, rot=(0, math.pi / 2, 0))
    # 縦ブラインド (少しずつ回転をばらす)
    n = int(w / 0.085)
    for i in range(n + 1):
        y = cy - w / 2 + 0.03 + i * (w - 0.06) / n
        box(f"win{idx}_slat_{i}", 0.012, 0.075, h - 0.03, (0.10, y, zc), bm,
            rot=(0, 0, R.uniform(-0.18, 0.18)))
    # 外光 (エリアライト)
    wl_defs = {
        "morning": (170, (1.00, 0.90, 0.72)),
        "evening": (120, (1.00, 0.55, 0.32)),
        "night":   (55, (0.66, 0.73, 0.86)),
    }
    we, wc = wl_defs.get(TIME, wl_defs["night"])
    area_light(f"win{idx}_light", (0.18, cy, zc), (0, math.radians(90), 0),
               w * 0.9, we, wc, size_y=h * 0.9)


def build_north_wall():
    """北壁: 収納扉の列 + 両開きドア(欄間付き)."""
    trim = mat_wood("wood_trim", PAL["wood_trim"], rough=0.55, scale=2.0)
    doorw = mat_wood("wood_door", (0.130, 0.100, 0.062), rough=0.5, scale=1.2, along="X", strength=0.10)
    metal = mat("metal", PAL["metal"], rough=0.3)
    # 収納扉 4枚 (x 0.5..3.9)
    for i in range(4):
        cx = 0.92 + i * 0.85
        box(f"cab_{i}", 0.83, 0.05, 2.35, (cx, ROOM_Y - 0.045, 1.175), doorw)
        box(f"cab_{i}_gap", 0.015, 0.06, 2.35, (cx + 0.42, ROOM_Y - 0.045, 1.175), trim)
        cyl(f"cab_{i}_knob", 0.008, 0.09, (cx + 0.35, ROOM_Y - 0.09, 1.15), metal,
            rot=(math.pi / 2, 0, 0), verts=8)
    # 両開きドア (x 4.4..5.9) + 欄間
    dx0, dx1 = 4.45, 5.95
    dc = (dx0 + dx1) / 2
    dh = 2.15
    for s, cx in ((0, dc - 0.375), (1, dc + 0.375)):
        box(f"door_{s}", 0.72, 0.06, dh, (cx, ROOM_Y - 0.05, dh / 2), doorw)
        # パネル溝 (面に細枠)
        box(f"door_{s}_p1", 0.46, 0.015, 1.10, (cx, ROOM_Y - 0.085, 1.35), trim)
        box(f"door_{s}_p2", 0.46, 0.015, 0.45, (cx, ROOM_Y - 0.085, 0.42), trim)
    box("door_lever", 0.16, 0.03, 0.03, (dc - 0.06, ROOM_Y - 0.10, 1.02), metal)
    # 枠と欄間
    for dxx in (dx0 - 0.06, dx1 + 0.06):
        box(f"door_jamb_{dxx:.1f}", 0.10, 0.09, 2.75, (dxx, ROOM_Y - 0.045, 1.375), trim)
    box("door_head", dx1 - dx0 + 0.24, 0.09, 0.08, (dc, ROOM_Y - 0.045, dh + 0.04), trim)
    box("door_top", dx1 - dx0 + 0.24, 0.09, 0.10, (dc, ROOM_Y - 0.045, 2.70), trim)
    # 欄間ガラス (ほんのり明るい)
    plane("transom", dx1 - dx0 - 0.1, 0.38, (dc, ROOM_Y - 0.055, 2.43),
          mat("transom_glass", (0.30, 0.28, 0.24), rough=0.3, emit=0.15),
          rot=(math.pi / 2, 0, 0))


def build_screen():
    """東壁の発光スクリーン."""
    box("scr_frame", 0.06, 2.55, 1.50, (ROOM_X - 0.03, 3.5, 1.85),
        mat("scr_frame", (0.03, 0.03, 0.03), rough=0.4))
    plane("scr_face", 2.4, 1.35, (ROOM_X - 0.075, 3.5, 1.85),
          mat("glow_scr", PAL["glow_scr"], rough=0.6, emit=1.5),
          rot=(math.pi / 2, 0, -math.pi / 2))
    area_light("scr_light", (ROOM_X - 0.25, 3.5, 1.85), (0, math.radians(-90), 0),
               2.0, 16, (0.75, 0.85, 0.80), size_y=1.4)


def build_table_chairs():
    """楕円会議テーブル (配線スロット付き) + オフィスチェア."""
    tm = mat_wood("wood_table", PAL["wood_table"], rough=0.35, scale=2.0, along="Y", strength=0.14)
    dark = mat("slot_dark", (0.030, 0.028, 0.026), rough=0.5)
    metal = mat("metal", PAL["metal"], rough=0.3)
    cx, cy = 3.0, 3.3
    # 天板: 8角形を丸めた楕円。長軸は奥行き(Y)方向 = ボードの向き
    cyl("table_top", 1.0, 0.05, (cx, cy, 0.725), tm, verts=8)
    o = bpy.data.objects["table_top"]
    o.scale = (1.00, 1.70, 1.0)  # 長軸=奥行き。回転なし(スロット・脚と軸を揃える)
    # 中央の配線スロット (長軸に沿ってY方向)
    box("slot", 0.24, 1.5, 0.02, (cx, cy, 0.755), dark)
    # 脚 (X方向に渡す門型 ×3。天板短径±1.0の内側に収める)
    for dy in (-1.05, 0, 1.05):
        for dx in (-0.42, 0.42):
            box(f"leg_{dy:.1f}_{dx:.1f}", 0.06, 0.06, 0.70,
                (cx + dx, cy + dy, 0.35), metal)
        box(f"leg_{dy:.1f}_t", 0.90, 0.06, 0.05, (cx, cy + dy, 0.675), metal)
    # チェア (テンプレート + 複製)
    def chair(name, px, py, ang):
        lm = mat("chair", PAL["chair"], rough=0.55)
        mm = mat("metal", PAL["metal"], rough=0.3)
        ca, sa = math.cos(ang), math.sin(ang)
        def rot_off(dx, dy):
            return (px + dx * ca - dy * sa, py + dx * sa + dy * ca)
        # 座面・背もたれ・肘掛け
        x, y = rot_off(0, 0)
        box(f"{name}_seat", 0.50, 0.48, 0.10, (x, y, 0.47), lm, rot=(0, 0, ang))
        bx, by = rot_off(0, -0.235)
        box(f"{name}_back", 0.50, 0.09, 0.62, (bx, by, 0.85), lm,
            rot=(math.radians(-7) * 0, 0, ang))
        hx, hy = rot_off(0, -0.24)
        box(f"{name}_hrest", 0.30, 0.09, 0.12, (hx, hy, 1.18), lm, rot=(0, 0, ang))
        for s in (-1, 1):
            ax, ay = rot_off(s * 0.29, 0.02)
            box(f"{name}_arm{s}", 0.06, 0.30, 0.05, (ax, ay, 0.66), lm, rot=(0, 0, ang))
            box(f"{name}_armp{s}", 0.05, 0.05, 0.16, (ax, ay + 0.1 * 0, 0.56), mm,
                rot=(0, 0, ang))
        # 支柱と5本脚
        cyl(f"{name}_post", 0.03, 0.36, (x, y, 0.24), mm, verts=10)
        for k in range(5):
            a2 = ang + k * 2 * math.pi / 5
            lx = x + math.cos(a2) * 0.16
            ly = y + math.sin(a2) * 0.16
            box(f"{name}_cast{k}", 0.30, 0.05, 0.04,
                (lx, ly, 0.045), mm, rot=(0, 0, a2))
    # 配置: 左側2脚(窓側)・右手前1脚・右奥1脚・奥1脚
    # 平面図どおり8脚: 長辺3+3 + 両端1+1
    for i, yy in enumerate((2.15, 3.3, 4.45)):
        chair(f"chW{i}", 1.52, yy, math.radians(-90 + R.uniform(-8, 8)))
        chair(f"chE{i}", 4.48, yy, math.radians(90 + R.uniform(-8, 8)))
    chair("chN", 3.0, 5.5, math.radians(0 + 3))
    chair("chS", 3.0, 1.1, math.radians(180 - 4))


def build_lights():
    from stagelib import sun_light
    if TIME == "morning":
        set_world((0.35, 0.38, 0.42), strength=1.0)  # 朝の明るい環境光
        # 低い朝日がブラインド越しに差し込む (スラット影が床に落ちる)
        sun_light("sun_morning", rot=(0, math.radians(78), math.radians(8)),
                  energy=6.0, color=(1.0, 0.88, 0.68), angle_deg=1.5)
    elif TIME == "evening":
        set_world((0.10, 0.075, 0.065), strength=1.0)  # 夕方の沈んだ暖色
        sun_light("sun_evening", rot=(0, math.radians(83), math.radians(-5)),
                  energy=3.5, color=(1.0, 0.45, 0.22), angle_deg=2.5)
    else:
        set_world((0.012, 0.016, 0.020), strength=1.0)  # 夜の青い闇
    # ダウンライトの実光源 (朝は消灯)
    if TIME == "morning":
        return
    for x, y in [(0.65, 3.0), (0.65, 4.8), (ROOM_X - 0.65, 3.0), (ROOM_X - 0.65, 4.8),
                 (2.5, 6.6), (4.3, 6.6)]:
        d = bpy.data.lights.new(f"pl_{x:.0f}_{y:.0f}", type="POINT")
        d.energy = 2.6
        d.color = (0.72, 0.75, 0.72)
        d.shadow_soft_size = 0.1
        o = bpy.data.objects.new(f"pl_{x:.0f}_{y:.0f}", d)
        o.location = (x, y, WALL_H - 0.15)
        bpy.context.collection.objects.link(o)
    # 全体をほんの少し持ち上げる青緑のフィル
    area_light("fill", (3.3, 3.5, WALL_H - 0.1), (0, 0, 0), 3.0, 9, (0.50, 0.63, 0.62))


def build_scene():
    reset_scene()
    build_shell()
    window_with_blinds(0, 2.2)
    window_with_blinds(1, 4.6)
    build_north_wall()
    build_screen()
    build_table_chairs()
    build_lights()
    cams = {
        # ボード再現 (南西寄りから北東へ)
        "A": add_camera("cam_A", (4.7, 0.5, 1.5), (2.5, 6.8, 0.95), lens=19),
        # 逆 (ドア側から)
        "B": add_camera("cam_B", (5.2, 6.5, 1.5), (1.2, 0.6, 1.0), lens=23),
        # スクリーン側から窓へ
        "C": add_camera("cam_C", (6.1, 3.2, 1.4), (0.3, 3.0, 1.3), lens=24),
        # 俯瞰
        "T": add_camera("cam_T", (1.0, 0.8, 2.7), (4.6, 4.6, 0.3), lens=26),
    }
    return cams


if __name__ == "__main__":
    cams = build_scene()
    render_cli(cams, default_res="1280x800", view_transform="AgX",
               exposure={"morning": 0.3, "evening": 0.55}.get(TIME, 0.75))
