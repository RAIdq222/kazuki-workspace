# -*- coding: utf-8 -*-
"""実写ボード「東中野の路地」の3Dステージ化。

写真の構成: 幅3m弱の住宅路地 (アスファルト+両側にコンクリ側溝)。
左: CBブロック塀 + 白スタッコ2階建てアパート「ハイツグリーン東中野」
    (焦げ茶ドア×2・庇・館銘板・入居者募集看板・電気メーター・縦ルーバー)。
右: ピンク吹付の塀 + 黒鉄骨の外階段がある茶色い木板2階建てアパート。
奥: クリーム3階建て(スリット窓)・緑サイディング3階建て・白い家並み。
上空: 電柱+大量の電線。曇り混じりの昼。

見えている範囲のみ作り込む (ユーザー指示)。空間の寸法整合を優先:
路地幅3.0m(側溝0.3×2含む)・ブロック塀6段1.15m・階高3m・アイレベル1.45m。

座標 (単位m): X=路地の幅方向(左=負), Y=奥行き(カメラは-Y側), Z=高さ
実行例:
    python3 src/stage3d/alley_higashinakano.py -- --views A,T --samples 48 \
        --res 1600x1200 --out work/renders --blend work/alley.blend
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from stagelib import (reset_scene, mat, mat_image,  # noqa: E402
                      box, cyl, sphere, plane,
                      add_camera, set_world, sun_light, render_cli)

R = random.Random(11)
SPR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                   "work", "sprites")

# 時間帯 (--time day|evening|night)
TIME = "day"
if "--time" in sys.argv:
    i = sys.argv.index("--time")
    TIME = sys.argv[i + 1]
    del sys.argv[i:i + 2]

ROAD_HALF = 1.5      # 路地の半幅 (側溝含む)
GUT_W = 0.30         # 側溝蓋の幅
ALLEY_LEN = 42.0

PAL = {
    "concrete":   (0.520, 0.520, 0.500),
    "cb_gray":    (0.480, 0.470, 0.440),
    "white_wall": (0.760, 0.750, 0.720),
    "cream":      (0.640, 0.600, 0.520),
    "pink_wall":  (0.430, 0.300, 0.270),
    "brown":      (0.180, 0.130, 0.095),
    "dk_metal":   (0.045, 0.045, 0.048),
    "glass":      (0.130, 0.155, 0.170),
    "sash":       (0.550, 0.560, 0.570),
    "green_dk":   (0.075, 0.135, 0.070),
    "pipe_gray":  (0.420, 0.430, 0.430),
    "pole_con":   (0.350, 0.350, 0.340),
    "iron":       (0.040, 0.040, 0.044),
}

# 向き付き縦板 (テクスチャが正立するオイラー):
ROT_FACE_PX = (math.pi / 2, 0, math.pi / 2)    # 法線+X (左側の面が路地を向く)
ROT_FACE_NX = (math.pi / 2, 0, -math.pi / 2)   # 法線-X (右側の面が路地を向く)
ROT_FACE_NY = (math.pi / 2, 0, 0)              # 法線-Y (正面がカメラを向く)


def timg(name, fname, rough=0.9, uv_scale=None, blend="OPAQUE", emit=0.0):
    return mat_image(name, os.path.join(SPR, fname), rough=rough,
                     uv_scale=uv_scale, blend=blend, emit=emit)


def wire(name, p1, p2, sag=0.35, r=0.013, segs=10, m=None):
    """電線: カテナリー近似のポリライン curve → メッシュ化."""
    cu = bpy.data.curves.new(name, type="CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = r
    cu.bevel_resolution = 2
    sp = cu.splines.new("POLY")
    sp.points.add(segs)
    for i in range(segs + 1):
        t = i / segs
        sp.points[i].co = (p1[0] + (p2[0] - p1[0]) * t,
                           p1[1] + (p2[1] - p1[1]) * t,
                           p1[2] + (p2[2] - p1[2]) * t - sag * 4 * t * (1 - t),
                           1.0)
    o = bpy.data.objects.new(name, cu)
    o.data.materials.append(m or mat("wire", PAL["dk_metal"], rough=0.6))
    bpy.context.collection.objects.link(o)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.convert(target="MESH")
    o.select_set(False)
    return o


def set_world_sky(strength=0.9):
    """曇り混じりの空テクスチャをワールドに (青みの環境光も兼ねる)."""
    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes["Background"]
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(os.path.abspath(os.path.join(SPR, "aly_sky.png")))
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = strength


def build_road():
    # 建物の下も含めた下地 (俯瞰で虚空が見えないように)
    plane("ground_base", 22, ALLEY_LEN + 16, (0, ALLEY_LEN / 2, -0.02),
          mat("ground_base", (0.300, 0.295, 0.285), rough=0.95))
    asp = timg("asphalt", "aly_asphalt.png", rough=0.95,
               uv_scale=(2.0, ALLEY_LEN / 1.5))
    plane("road", ROAD_HALF * 2, ALLEY_LEN + 6, (0, ALLEY_LEN / 2 - 3 + 1.5, 0), asp)
    gut = timg("gutter", "aly_gutter.png", rough=0.9,
               uv_scale=(1.0, ALLEY_LEN / 0.6))
    for sgn, nm in ((-1, "gutL"), (1, "gutR")):
        plane(nm, GUT_W, ALLEY_LEN + 6,
              (sgn * (ROAD_HALF - GUT_W / 2), ALLEY_LEN / 2 - 1.5, 0.008), gut)
    # マンホール
    iron = mat("manhole", (0.100, 0.100, 0.098), rough=0.75)
    cyl("manhole", 0.30, 0.014, (0.25, 7.5, 0.004), iron, verts=24)
    cyl("manhole2", 0.24, 0.014, (-0.30, 16.0, 0.004), iron, verts=20)


def win(name, side, x, y, z, w, h, glass_glow=False):
    """引き違い窓: サッシ枠+暗いガラス。side='L'(+X向き)/'R'(-X向き)/'F'(-Y向き)."""
    sash = mat("sash", PAL["sash"], rough=0.4)
    gm = mat("glow_win" if glass_glow else "glass", PAL["glass"],
             rough=0.15, emit=0.0)
    if side == "L":
        rot, d = ROT_FACE_PX, (0.03, 0, 0)
        box(f"{name}_f", 0.06, w + 0.10, h + 0.10, (x, y, z), sash)
        plane(f"{name}_g", w, h, (x + d[0], y, z), gm, rot=rot)
        plane(f"{name}_bar", 0.04, h, (x + d[0] + 0.005, y, z), sash, rot=rot)
    elif side == "R":
        box(f"{name}_f", 0.06, w + 0.10, h + 0.10, (x, y, z), sash)
        plane(f"{name}_g", w, h, (x - 0.03, y, z), gm, rot=ROT_FACE_NX)
        plane(f"{name}_bar", 0.04, h, (x - 0.035, y, z), sash, rot=ROT_FACE_NX)
    else:
        box(f"{name}_f", w + 0.10, 0.06, h + 0.10, (x, y, z), sash)
        plane(f"{name}_g", w, h, (x, y - 0.03, z), gm, rot=ROT_FACE_NY)


def build_left_apartment():
    """ハイツグリーン東中野 (白スタッコ2階建て) + ブロック塀."""
    stw = timg("stucco_w", "aly_stucco_w.png", rough=0.95, uv_scale=(6.0, 3.2))
    wm = mat("white_body", PAL["white_wall"], rough=0.9)
    # 本体 (手前はカメラ後方まで伸ばす)
    box("bldgL", 3.6, 13.4, 6.1, (-3.68, 3.6, 3.05), wm)
    plane("bldgL_face", 13.4, 6.1, (-1.87, 3.6, 3.05), stw, rot=ROT_FACE_PX)
    # 屋上パラペット笠木
    box("bldgL_cap", 3.8, 13.6, 0.12, (-3.68, 3.6, 6.16), mat("cap", PAL["brown"], 0.6))
    # 階間の霧除け庇 (ドア上を通しで)
    box("bldgL_eave", 0.35, 4.2, 0.07, (-1.72, 8.1, 3.02), wm)
    # ブロック塀 (6段=1.15m) + 笠木: 前面はブロックテクスチャの板
    cbm = mat("cb_body", PAL["cb_gray"], rough=0.95)
    cbt = timg("cb_face", "aly_block.png", rough=0.95, uv_scale=(5.4 / 0.8, 1.15 / 0.8))
    box("cbwall", 0.12, 5.4, 1.15, (-1.62, 3.9, 0.575), cbm)
    plane("cbwall_face", 5.4, 1.15, (-1.555, 3.9, 0.575), cbt, rot=ROT_FACE_PX)
    box("cbwall_cap", 0.16, 5.44, 0.05, (-1.62, 3.9, 1.175), cbm)
    # 錆びた郵便差入口
    box("mailslot", 0.05, 0.36, 0.26, (-1.545, 3.35, 0.70),
        mat("rust", (0.190, 0.110, 0.070), rough=0.8))
    # 玄関ステップ (2段) ×2戸分
    cm = mat("step_con", PAL["concrete"], rough=0.95)
    for i, dy in enumerate((7.15, 8.85)):
        box(f"stepA{i}", 0.35, 1.10, 0.30, (-1.68, dy, 0.15), cm)
        box(f"stepB{i}", 0.30, 0.90, 0.15, (-1.62, dy, 0.075), cm)
    # ドア×2 (焦げ茶) + 庇
    dm = timg("door", "aly_door.png", rough=0.55)
    br = mat("door_frame", PAL["brown"], rough=0.6)
    for i, dy in enumerate((7.15, 8.85)):
        box(f"doorf{i}", 0.06, 0.95, 2.05, (-1.86, dy, 1.33), br)
        plane(f"door{i}", 0.85, 1.95, (-1.82, dy, 1.31), dm, rot=ROT_FACE_PX)
        box(f"canopy{i}", 0.55, 1.15, 0.05, (-1.66, dy, 2.55),
            mat("canopy", (0.700, 0.690, 0.665), 0.7), rot=(0, math.radians(-12), 0))
    # ドア間の縦ルーバーパネル (白)
    lv = mat("louver", (0.740, 0.740, 0.720), rough=0.7)
    box("lv_frame", 0.05, 0.80, 1.85, (-1.84, 8.02, 1.25), lv)
    for k in range(6):
        box(f"lv_slat{k}", 0.09, 0.07, 1.75,
            (-1.80, 7.70 + k * 0.13, 1.25), lv, rot=(0, 0, math.radians(28)))
    # 館銘板 + 入居者募集看板 (ベランダ格子より奥側の壁面、y>2.6)
    plane("plate", 0.74, 0.52, (-1.845, 3.15, 3.55),
          timg("plate", "aly_plate.png", rough=0.5), rot=ROT_FACE_PX)
    plane("sign_bosyu", 0.48, 0.64, (-1.845, 3.20, 2.42),
          timg("sign_bosyu", "aly_sign_bosyu.png", rough=0.6), rot=ROT_FACE_PX)
    # 電気メーター+配管
    mb = mat("meterbox", (0.360, 0.370, 0.375), rough=0.5)
    box("meter1", 0.16, 0.30, 0.44, (-1.80, 1.15, 2.25), mb)
    box("meter2", 0.14, 0.22, 0.30, (-1.82, 1.52, 2.18), mb)
    cyl("conduit", 0.022, 2.2, (-1.83, 1.18, 1.05), mat("pipe", PAL["pipe_gray"], 0.6))
    # 雨樋 (焦げ茶)
    cyl("pipeL1", 0.045, 6.0, (-1.80, 0.12, 3.05),
        mat("pipe_brown", (0.240, 0.170, 0.120), rough=0.6))
    # 2F: ベランダ (縦格子の白手すり) + 窓
    box("balc_slab", 0.45, 2.6, 0.10, (-1.72, 1.3, 3.15), wm)
    for k in range(14):
        box(f"balc_v{k}", 0.03, 0.06, 1.05, (-1.53, 0.12 + k * 0.185, 3.75), lv)
    box("balc_rail", 0.05, 2.6, 0.05, (-1.53, 1.3, 4.30), lv)
    win("winL2", "L", -1.86, 1.3, 4.05, 1.5, 1.6, glass_glow=True)
    win("winL3", "L", -1.86, 6.4, 4.45, 1.2, 1.1)
    win("winL4", "L", -1.86, 9.2, 4.45, 1.2, 1.1, glass_glow=True)


def build_left_far():
    """左奥: クリーム3階建て(スリット窓)→白い家→遠景の家並み."""
    stc = timg("stucco_c", "aly_stucco_c.png", rough=0.95, uv_scale=(3.0, 4.0))
    cm = mat("cream_body", PAL["cream"], rough=0.9)
    box("bldgL2", 3.4, 5.4, 8.5, (-3.75, 12.9, 4.25), cm)
    plane("bldgL2_face", 5.4, 8.5, (-2.04, 12.9, 4.25), stc, rot=ROT_FACE_PX)
    plane("bldgL2_slit", 0.55, 5.6, (-2.03, 11.6, 4.6),
          mat("glass", PAL["glass"], 0.15), rot=ROT_FACE_PX)
    win("winL2a", "L", -2.05, 14.2, 6.8, 0.9, 0.9)
    box("bldgL2_cap", 3.5, 5.5, 0.1, (-3.75, 12.9, 8.55), mat("cap", PAL["brown"], 0.6))
    # 白い2階建て
    stw = timg("stucco_w", "aly_stucco_w.png")
    box("bldgL3", 3.0, 4.4, 5.8, (-4.2, 18.0, 2.9), mat("white_body", PAL["white_wall"]))
    plane("bldgL3_face", 4.4, 5.8, (-2.68, 18.0, 2.9), stw, rot=ROT_FACE_PX)
    win("winL3a", "L", -2.7, 17.0, 4.3, 1.3, 1.2)
    win("winL3b", "L", -2.7, 19.2, 4.3, 0.9, 1.2, glass_glow=True)
    # 生垣・植え込み
    gm = mat("hedge", PAL["green_dk"], rough=0.95)
    for k, (yy, s) in enumerate([(15.9, 0.75), (16.8, 0.9), (17.8, 0.8),
                                 (19.0, 0.95), (20.0, 0.7)]):
        sphere(f"hedgeL{k}", 0.55, (-1.85, yy, 0.55 * s),
               gm, scale=(0.8, 1.0, s))
    # 遠景の家並み (簡略ボリューム)
    for k, (yy, h, w, c) in enumerate([
            (22.5, 6.5, 4.0, PAL["white_wall"]),
            (26.5, 7.5, 3.6, (0.560, 0.545, 0.505)),
            (30.5, 5.5, 3.4, PAL["cream"]),
            (34.5, 8.0, 4.2, (0.480, 0.500, 0.480))]):
        box(f"farL{k}", 3.0, w, h, (-3.4 - (k % 2) * 0.7, yy, h / 2),
            mat(f"farL{k}", c, rough=0.9))
        win(f"farLw{k}", "L", -1.9 - (k % 2) * 0.7, yy, h * 0.62, 1.1, 1.0,
            glass_glow=(k == 1))


def build_right_apartment():
    """右: ピンク吹付の塀 + 黒鉄骨外階段の茶色2階建てアパート."""
    # ピンクの塀 (カメラ手前から奥まで右前景を占める)
    pk = mat("pink_body", PAL["pink_wall"], rough=0.95)
    pkt = timg("stucco_p", "aly_stucco_p.png", rough=0.95, uv_scale=(14.0 / 2, 1.85 / 2))
    box("pinkwall", 0.15, 14.0, 1.85, (1.60, 5.5, 0.925), pk)
    plane("pinkwall_face", 14.0, 1.85, (1.52, 5.5, 0.925), pkt, rot=ROT_FACE_NX)
    box("pinkwall_cap", 0.19, 14.04, 0.05, (1.60, 5.5, 1.875), pk)
    # 塀の開口 (ゴミ置き/通用口の暗がり) + 白い募集看板
    plane("pw_gap", 0.9, 1.7, (1.51, 10.3, 0.85),
          mat("dark_gap", (0.030, 0.030, 0.032), rough=0.95), rot=ROT_FACE_NX)
    plane("sign_small", 0.44, 0.60, (1.505, 5.1, 1.25),
          timg("sign_small", "aly_sign_small.png", rough=0.6), rot=ROT_FACE_NX)
    # 黒い鋼管ポール (標識柱) + 小さな標識板
    ir = mat("iron", PAL["iron"], rough=0.75)
    cyl("bpole", 0.042, 5.2, (1.34, 6.9, 2.6), ir, verts=12)
    plane("bpole_sign", 0.22, 0.32, (1.30, 6.88, 2.3),
          mat("sign_gray", (0.520, 0.530, 0.520), rough=0.6), rot=ROT_FACE_NX)
    # アパート本体: 1F 白モルタル / 2F 焦げ茶の木板
    wm = mat("white_body", PAL["white_wall"], rough=0.9)
    box("bldgR_1f", 3.4, 12.5, 3.1, (4.32, 4.0, 1.55), wm)
    wdt = timg("wood_r", "aly_wood.png", rough=0.85, uv_scale=(12.5 / 1.2, 3.2 / 1.2))
    box("bldgR_2f", 3.4, 12.5, 3.2, (4.32, 4.0, 4.70), mat("brown_body", PAL["brown"]))
    plane("bldgR_2f_face", 12.5, 3.2, (2.60, 4.0, 4.70), wdt, rot=ROT_FACE_NX)
    plane("bldgR_1f_face", 12.5, 3.1, (2.60, 4.0, 1.55),
          timg("stucco_w", "aly_stucco_w.png"), rot=ROT_FACE_NX)
    # 大きな下屋根 (階段上の黒い庇)
    box("bldgR_eave", 1.3, 6.0, 0.08, (2.15, 2.2, 6.35), ir,
        rot=(0, math.radians(14), 0))
    # 2Fの窓
    win("winR1", "R", 2.58, 5.6, 4.7, 1.3, 1.2, glass_glow=True)
    win("winR2", "R", 2.58, 8.4, 4.7, 1.3, 1.2)
    # 雨樋
    cyl("pipeR1", 0.05, 6.2, (2.50, 9.9, 3.1), mat("pipe", PAL["pipe_gray"], 0.6))
    cyl("pipeR2", 0.04, 3.0, (2.48, 3.0, 4.7), mat("pipe", PAL["pipe_gray"], 0.6))
    # 外階段 (黒鉄骨・手前が上=2F、奥へ降りる)
    build_stairs(ir)
    # 白い低層 (物置/離れ) + エアコン室外機
    box("bldgR2", 2.4, 3.0, 3.2, (3.3, 13.6, 1.6), wm)
    plane("bldgR2_face", 3.0, 3.2, (2.08, 13.6, 1.6),
          timg("siding_w", "aly_siding_w.png", uv_scale=(2.5, 2.6)), rot=ROT_FACE_NX)
    box("aircon", 0.30, 0.80, 0.65, (1.95, 12.9, 0.33),
        mat("aircon", (0.700, 0.700, 0.680), rough=0.6))


def build_stairs(ir):
    """右アパートの黒鉄骨外階段。手前(y小)が2F、奥へ13段降りる."""
    x0, x1 = 1.72, 2.48       # 階段の幅 (塀の内側)
    y_top, z_top = 1.3, 2.95  # 2F踊り場の先端
    rises, tread = 13, 0.30
    rise = z_top / rises
    # 踊り場
    box("st_land", x1 - x0, 1.5, 0.07, ((x0 + x1) / 2, 0.55, z_top), ir)
    for py in (0.0, 1.25):
        box(f"st_lpost{py}", 0.05, 0.05, 1.0, (x0 + 0.03, py, z_top + 0.5), ir)
        box(f"st_lpost2{py}", 0.05, 0.05, 1.0, (x1 - 0.03, py, z_top + 0.5), ir)
    box("st_lrail", 0.04, 1.5, 0.05, (x0 + 0.03, 0.55, z_top + 1.0), ir)
    box("st_lrail2", 0.04, 1.5, 0.05, (x1 - 0.03, 0.55, z_top + 1.0), ir)
    # 段板
    for k in range(rises):
        yy = y_top + (k + 0.5) * tread
        zz = z_top - (k + 1) * rise + rise / 2
        box(f"st_step{k}", x1 - x0, tread, 0.045, ((x0 + x1) / 2, yy, zz), ir)
    # ささら桁 (斜めの長材) ×2
    run = rises * tread
    ang = -math.atan2(z_top, run)
    length = math.hypot(run, z_top) + 0.3
    for xx, nm in ((x0 + 0.02, "st_str1"), (x1 - 0.02, "st_str2")):
        box(nm, 0.05, length, 0.24,
            (xx, y_top + run / 2, z_top / 2 - 0.06), ir, rot=(ang, 0, 0))
    # 手すり (外側=路地側)
    for k in range(0, rises + 1, 3):
        yy = y_top + k * tread
        zz = z_top - k * rise
        box(f"st_post{k}", 0.04, 0.04, 0.95, (x0 + 0.02, yy, zz + 0.42), ir)
    box("st_rail", 0.035, length, 0.045,
        (x0 + 0.02, y_top + run / 2, z_top / 2 + 0.85), ir, rot=(ang, 0, 0))


def build_right_far():
    """右奥: 緑サイディング3階建て + 遠景."""
    # 緑サイディング3階建て (茶アパートより路地側に面を出し、白い低層とy範囲を分ける)
    sg = timg("siding_g", "aly_siding_g.png", rough=0.85, uv_scale=(5.0, 7.0))
    box("bldgR3", 3.2, 6.0, 8.4, (3.75, 18.3, 4.2),
        mat("green_body", (0.420, 0.460, 0.410), rough=0.9))
    plane("bldgR3_face", 6.0, 8.4, (2.13, 18.3, 4.2), sg, rot=ROT_FACE_NX)
    wm = mat("white_body", PAL["white_wall"], rough=0.9)
    for k, zz in enumerate((3.1, 5.9)):
        box(f"bR3_balc{k}", 0.4, 4.0, 0.09, (2.00, 17.9, zz), wm)
        box(f"bR3_rail{k}", 0.05, 4.0, 0.75, (1.84, 17.9, zz + 0.42),
            mat("balc_panel", (0.620, 0.620, 0.600), rough=0.7))
    win("winR3a", "R", 2.11, 16.6, 4.4, 1.2, 1.3, glass_glow=True)
    win("winR3b", "R", 2.11, 19.5, 7.0, 1.2, 1.3)
    # 屋上の白い手すり (写真右上のペントハウス風)
    box("bR3_top", 0.06, 6.0, 0.7, (1.90, 18.3, 8.75),
        mat("balc_panel", (0.620, 0.620, 0.600), rough=0.7))
    # 植え込み
    gm = mat("hedge", PAL["green_dk"], rough=0.95)
    for k, (yy, s) in enumerate([(12.6, 0.8), (13.4, 1.0), (14.3, 0.85)]):
        sphere(f"hedgeR{k}", 0.5, (1.75, yy, 0.5 * s), gm, scale=(0.75, 1.0, s))
    # 遠景の家並み
    for k, (yy, h, w, c) in enumerate([
            (21.5, 6.0, 3.4, PAL["cream"]),
            (25.0, 7.0, 3.2, PAL["white_wall"]),
            (29.0, 5.0, 3.6, (0.520, 0.480, 0.440)),
            (33.0, 6.5, 3.6, (0.600, 0.600, 0.580))]):
        box(f"farR{k}", 3.0, w, h, (3.4 + (k % 2) * 0.6, yy, h / 2),
            mat(f"farR{k}", c, rough=0.9))
        win(f"farRw{k}", "R", 1.9 + (k % 2) * 0.6, yy, h * 0.6, 1.1, 1.0,
            glass_glow=(k == 2))
    # 突き当たり正面の白い家 (路地の消失点を受ける)
    box("far_end", 5.0, 3.0, 6.5, (0.8, 39.5, 3.25), wm)
    plane("far_end_face", 5.0, 6.5, (0.8, 37.9, 3.25),
          timg("stucco_w", "aly_stucco_w.png"), rot=ROT_FACE_NY)
    win("far_endw", "F", 0.2, 37.88, 4.2, 1.4, 1.2)


def build_poles_wires():
    """電柱3本 + 電線 (幹線・通信・引込線)."""
    pc = mat("pole", PAL["pole_con"], rough=0.85)
    ir = mat("iron", PAL["iron"], rough=0.75)
    poles = [(-1.30, 10.5, 9.8), (1.36, 23.0, 9.2), (-1.28, 34.0, 8.8)]
    for k, (px, py, ph) in enumerate(poles):
        cyl(f"pole{k}", 0.145, ph, (px, py, ph / 2), pc, verts=14, r2=0.10)
        # 腕金 + 碍子
        box(f"pole{k}_arm", 1.7, 0.07, 0.07, (px, py, ph - 0.9), ir)
        for dx in (-0.6, 0, 0.6):
            cyl(f"pole{k}_ins{dx}", 0.045, 0.14, (px + dx, py, ph - 0.78),
                mat("insul", (0.740, 0.740, 0.720), 0.4), verts=8)
        if k < 2:  # 変圧器・機器箱
            cyl(f"pole{k}_trans", 0.28, 0.75, (px + 0.32, py, ph - 1.9), ir, verts=12)
            box(f"pole{k}_box", 0.22, 0.30, 0.45, (px - 0.25, py, ph - 2.9), ir)
    # 防犯灯 (メイン電柱・路地側に張り出し)
    lam = mat("lamp_arm", PAL["pipe_gray"], rough=0.5)
    cyl("lamp_arm", 0.025, 0.9, (poles[0][0] + 0.45, poles[0][1], 4.85), lam,
        rot=(0, math.pi / 2, 0))
    box("lamp_body", 0.55, 0.14, 0.09, (poles[0][0] + 0.85, poles[0][1], 4.85),
        mat("lamp_case", (0.640, 0.650, 0.630), rough=0.5))
    plane("lamp_glow", 0.48, 0.11, (poles[0][0] + 0.85, poles[0][1], 4.79),
          mat("lamp", (0.900, 0.920, 0.860), rough=0.4,
              emit=(6.0 if TIME == "night" else 0.0)),
          rot=(math.pi, 0, 0))
    # ---- 電線 ----
    p0 = (-1.30, 10.5)
    p1 = (1.36, 23.0)
    p2 = (-1.28, 34.0)
    # 幹線 (電柱間・3条) — カメラ後方からP0へも
    for j, dx in enumerate((-0.55, 0.0, 0.55)):
        wire(f"w_main0{j}", (p0[0] + dx, p0[1], 8.9), (p1[0] + dx * 0.6, p1[1], 8.3),
             sag=0.55)
        wire(f"w_main1{j}", (p1[0] + dx * 0.6, p1[1], 8.3), (p2[0] + dx * 0.5, p2[1], 7.9),
             sag=0.45)
        wire(f"w_back{j}", (p0[0] + dx, p0[1], 8.9), (-1.1 + dx, -4.0, 9.4), sag=0.6)
    # 通信ケーブル束 (少し低い高さ)
    wire("w_com0", (p0[0], p0[1], 7.2), (p1[0], p1[1], 6.9), sag=0.7, r=0.020)
    wire("w_com1", (p1[0], p1[1], 6.9), (p2[0], p2[1], 6.7), sag=0.6, r=0.020)
    wire("w_comb", (p0[0], p0[1], 7.2), (-1.0, -4.0, 7.6), sag=0.8, r=0.020)
    # 引込線 (建物へ斜めに降りる)
    drops = [((p0[0], p0[1], 8.6), (-1.9, 5.5, 6.2)),
             ((p0[0], p0[1], 8.4), (2.6, 3.0, 6.4)),
             ((p0[0], p0[1], 7.9), (-2.0, 13.5, 8.0)),
             ((p0[0], p0[1], 8.2), (2.5, 15.5, 8.2)),
             ((p1[0], p1[1], 8.0), (2.4, 17.5, 8.5)),
             ((p1[0], p1[1], 7.6), (-2.3, 22.5, 6.3)),
             ((p1[0], p1[1], 7.8), (3.2, 26.0, 6.8)),
             ((p0[0], p0[1], 7.2), (-1.9, 8.0, 5.9))]
    for k, (a, b) in enumerate(drops):
        wire(f"w_drop{k}", a, b, sag=0.35, r=0.011)
    # 横断する斜めの束 (写真上部のごちゃっと感)
    wire("w_cross0", (-1.9, 6.0, 6.1), (2.55, 9.0, 6.3), sag=0.3, r=0.014)
    wire("w_cross1", (-2.0, 12.0, 7.9), (2.5, 16.0, 8.0), sag=0.4, r=0.014)
    wire("w_cross2", (-1.9, 4.2, 6.2), (p0[0], p0[1], 8.0), sag=0.25, r=0.012)
    wire("w_cross3", (2.6, 2.0, 6.5), (p0[0], p0[1], 8.5), sag=0.3, r=0.012)
    wire("w_cross4", (-1.9, 0.5, 6.3), (2.6, 6.5, 6.6), sag=0.35, r=0.014)
    wire("w_cross5", (p0[0], p0[1], 9.2), (2.2, 18.0, 8.9), sag=0.5, r=0.012)


def build_props():
    """小物: 鉢植え・室外機まわり."""
    pot = mat("pot", (0.140, 0.110, 0.100), rough=0.9)
    gm = mat("plant", (0.090, 0.160, 0.080), rough=0.9)
    for k, (xx, yy, s) in enumerate([(-1.38, 6.75, 0.9), (-1.36, 6.35, 0.65)]):
        cyl(f"pot{k}", 0.13 * s, 0.24 * s, (xx, yy, 0.12 * s), pot, verts=12, r2=0.10 * s)
        sphere(f"plant{k}", 0.17 * s, (xx, yy, 0.32 * s), gm, scale=(1, 1, 1.25))


def build_lights():
    if TIME == "evening":
        set_world((0.30, 0.20, 0.15), strength=1.0)
        sun_light("sun_ev", rot=(0, math.radians(80), math.radians(20)),
                  energy=2.8, color=(1.0, 0.50, 0.25), angle_deg=3.0)
    elif TIME == "night":
        set_world((0.012, 0.016, 0.026), strength=1.0)
        d = bpy.data.lights.new("lamp_pt", type="POINT")
        d.energy = 60.0
        d.color = (0.85, 0.90, 0.80)
        d.shadow_soft_size = 0.25
        o = bpy.data.objects.new("lamp_pt", d)
        o.location = (-0.45, 10.5, 4.7)
        bpy.context.collection.objects.link(o)
    else:  # 昼 (曇り混じり)
        set_world_sky(strength=1.15)
        sun_light("sun_day", rot=(math.radians(28), 0, math.radians(200)),
                  energy=3.2, color=(1.0, 0.97, 0.90), angle_deg=8.0)


def build_scene():
    reset_scene()
    build_road()
    build_left_apartment()
    build_left_far()
    build_right_apartment()
    build_right_far()
    build_poles_wires()
    build_props()
    build_lights()
    cams = {
        # ボード再現 (路地の入口・アイレベル1.45m)
        "A": add_camera("cam_A", (0.45, -1.6, 1.45), (-0.15, 12.0, 1.15), lens=21),
        # 逆方向 (奥から入口へ)
        "B": add_camera("cam_B", (-0.30, 13.5, 1.50), (0.40, -3.0, 1.30), lens=24),
        # 見上げ (電線と空)
        "C": add_camera("cam_C", (0.20, 5.5, 1.30), (0.00, 14.0, 7.5), lens=20),
        # 俯瞰
        "T": add_camera("cam_T", (-6.0, -3.0, 14.0), (1.0, 14.0, 0.0), lens=30),
    }
    return cams


if __name__ == "__main__":
    cams = build_scene()
    render_cli(cams, default_res="1600x1200", view_transform="AgX",
               exposure={"evening": 0.55, "night": 0.35}.get(TIME, 0.9))
