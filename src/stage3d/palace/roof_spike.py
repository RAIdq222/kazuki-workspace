# Phase 0.5: 反り屋根スパイク — 屋根1枚の技術検証 (使い捨てシーン)
# 実行: python src/stage3d/palace/roof_spike.py -- --views F,Q,C,T --samples 48 \
#          --res 1600x900 --out work/renders --tag spike
# 検証観点: 挙架の凹カーブ / 中央軒線の水平 / 翼角の滑らかな反り / 45°隅棟 /
#           歇山の山花 / 重檐の整合 / --style line でのシルエット確認
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)

import bpy  # noqa: E402
from stagelib import mat, box, plane, add_camera, sun_light, set_world, render_cli  # noqa: E402
from kit.roofs import roof  # noqa: E402

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

M_roof = mat("roof_dark", (0.16, 0.17, 0.18), rough=0.75)
M_ridge = mat("ridge", (0.22, 0.24, 0.26), rough=0.7)
M_body = mat("body_red", (0.45, 0.16, 0.11), rough=0.85)
M_stone = mat("stone", (0.62, 0.60, 0.55), rough=0.95)
M_amber = mat("roof_amber", (0.66, 0.38, 0.10), rough=0.7)

plane("ground", 220, 160, (0, 0, 0), mat("ground", (0.5, 0.5, 0.44), rough=0.95))

# ---- 1) 主殿クラス: 重檐歇山 (身舎34×20、軒の出1.5) ----
box("terr", 44, 30, 2.0, (0, 0, 1.0), M_stone)
box("body1", 34, 20, 7.0, (0, 0, 2 + 3.5), M_body)
# 裳階(下層)は全周葺きの寄棟。上部は身舎に隠れるので棟飾りなし
roof("r_lower", 37, 23, 3.6, style="wudian", lift=0.4, reach=0.28,
     material=M_roof, ridge_mat=M_ridge, loc=(0, 0, 9.0), with_ridges=False,
     shiwei=False)
box("body2", 26, 14, 3.6, (0, 0, 12.6 + 1.8), M_body)
roof("r_upper", 29, 17, 5.4, style="xieshan", xr=0.45, lift=0.5, reach=0.35,
     material=M_roof, ridge_mat=M_ridge, loc=(0, 0, 16.2))

# ---- 2) 廡殿(寄棟)単檐: 門・脇殿クラス ----
box("body_w", 22, 12, 5.5, (-52, 0, 2.75), M_body)
roof("r_wudian", 25, 15, 4.2, style="wudian", lift=0.45, reach=0.3,
     material=M_amber, ridge_mat=M_ridge, loc=(-52, 0, 5.5))

# ---- 3) 強反りの小屋根: 亭・門ポーチクラス (lift大) ----
box("body_p", 8, 8, 3.2, (46, 0, 1.6), M_body)
roof("r_pav", 10.5, 10.0, 3.4, style="wudian", lift=0.95, reach=0.7, zone=3.2,
     material=M_amber, ridge_mat=M_ridge, loc=(46, 0, 3.2))

set_world((0.62, 0.70, 0.82), 0.55)
sun_light("sun", rot=(math.radians(50), 0, math.radians(140)), energy=3.0, angle_deg=3)

cams = {
    "F": add_camera("cam_F", (0, -95, 9), (0, 0, 12), lens=45),      # 正面 (軒線の水平と反り)
    "Q": add_camera("cam_Q", (60, -70, 18), (-6, 0, 10), lens=35),   # 3/4 (全体)
    "C": add_camera("cam_C", (24, -20, 10), (14, -8, 10), lens=35),  # 翼角の寄り
    "T": add_camera("cam_T", (-30, -70, 45), (0, 0, 6), lens=35),    # 見下ろし (45°隅棟)
}
for c in cams.values():
    c.data.clip_end = 700.0

render_cli(cams, default_res="1600x900", exposure=0.8)
