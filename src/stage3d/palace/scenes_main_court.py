# 皇宮・主殿区の統合シーン (主殿+別殿対+広場+香炉) — b08_17の完全な構図
# 実行: python src/stage3d/palace/scenes_main_court.py -- --views B,Q,E,S \
#          --samples 96 --res 1600x900 --out work/renders --tag court1 \
#          --blend work/palace_main_court.blend
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "buildings"))

import bpy  # noqa: E402
from stagelib import add_camera, sun_light, set_world, render_cli  # noqa: E402
from kit.materials import make_materials  # noqa: E402
from kit import props, textures  # noqa: E402
import main_hall  # noqa: E402
import bekkuden  # noqa: E402

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

M = make_materials()
main_hall.build(M, ongro_img=os.path.join(textures.OUT, "kw_ongro.png"))
bekkuden.build(M, 28, 110, facing="W", tag="e")   # layout_kyugu: x=±28, y=110
bekkuden.build(M, -28, 110, facing="E", tag="w")
props.court_context(M)

set_world((0.60, 0.72, 0.88), 0.68)
sun_light("sun", rot=(math.radians(48), 0, math.radians(135)), energy=3.2,
          angle_deg=2)

cams = {
    "B": add_camera("cam_B", (0, 30, 7.0), (0, 160, 17), lens=45),    # b08_17 再現
    "Q": add_camera("cam_Q", (72, 68, 17.0), (-10, 152, 10), lens=30),  # 斜め俯瞰
    "E": add_camera("cam_E", (-16, 116, 3.2), (28, 112, 5.2), lens=55),  # 別殿正対(b08_19)
    "S": add_camera("cam_S", (8.5, 89, 1.65), (-1, 148, 10), lens=30),  # 人目線
}
for c in cams.values():
    c.data.clip_end = 700.0

render_cli(cams, default_res="1600x900", exposure=0.85)
