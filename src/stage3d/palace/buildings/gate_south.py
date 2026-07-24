# 皇宮・正門 (二階重檐の門楼、中央に実開口)。build(M) で layout の gate_s 位置に生成
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PAL = os.path.dirname(_HERE)
sys.path.insert(0, os.path.dirname(_PAL))
sys.path.insert(0, _PAL)

from stagelib import box, plane  # noqa: E402
from kit.roofs import roof  # noqa: E402
from kit.generic import bands  # noqa: E402
from kit.structure import _link_copy  # noqa: E402

X, Y = 0.0, 0.0
W, D = 26.0, 9.0      # 門楼身舎
TH = 2.5              # 壇
OPEN_W, OPEN_H = 5.2, 4.4


def build(M):
    # 壇 (前後にスロープ状の階段)
    box("gate_terr", W + 8, D + 8, TH, (X, Y, TH / 2), M["stone"])
    box("gate_tc", W + 8.9, D + 8.9, 0.3, (X, Y, TH - 0.13), M["stone_w"])
    tpl = box("gate_tpl_step", 14, 0.3, 0.21, (0, 0, -66), M["stone"])
    for sy in (-1, 1):
        for st in range(int(TH / 0.21)):
            _link_copy(tpl, f"gate_st{sy}{st}",
                       (X, Y + sy * ((D + 8) / 2 + 0.15 + st * 0.3),
                        TH - 0.105 - st * 0.21))
    tpl.location = (0, 0, -500)
    # 中央開口を残した身舎 (左右ブロック+楣)
    side_w = (W - OPEN_W) / 2
    for sx in (-1, 1):
        bx = X + sx * (OPEN_W / 2 + side_w / 2)
        box(f"gate_blk{sx}", side_w, D, 5.4, (bx, Y, TH + 2.7), M["red"])
        plane(f"gate_bw{sx}", side_w, 5.4, (bx, Y - D / 2 - 0.01, TH + 2.7),
              M["redwall"], rot=(math.pi / 2, 0, 0))
        plane(f"gate_bwb{sx}", side_w, 5.4, (bx, Y + D / 2 + 0.01, TH + 2.7),
              M["redwall"], rot=(math.pi / 2, 0, math.pi))
        # 脇の飾り扉 (朱漆板門+門釘)
        plane(f"gate_door{sx}", 2.8, 3.8, (X + sx * (OPEN_W / 2 + side_w * 0.55),
                                           Y - D / 2 - 0.03, TH + 1.95),
              M["door"], rot=(math.pi / 2, 0, 0))
    box("gate_lintel", OPEN_W + 0.8, D, 1.0, (X, Y, TH + 4.9), M["red"])
    # 開口の内壁 (通り抜けの見え)
    for sx in (-1, 1):
        plane(f"gate_rev{sx}", D, 4.4, (X + sx * OPEN_W / 2, Y, TH + 2.2),
              M["redwall"], rot=(math.pi / 2, 0, math.pi / 2))
    plane("gate_ceil", OPEN_W, D, (X, Y, TH + OPEN_H), M["red"],
          rot=(0, 0, 0))
    # 帯→腰屋根→平座→上層→歇山
    z = bands("gate1", M, X, Y, W, D, TH + 5.4, frieze_key="frieze")
    roof("gate_skirt", W + 2.6, D + 2.6, 2.2, top_rect=(W * 0.37, D * 0.34),
         lift=0.35, reach=0.25, material=M["tile_amber"],
         ridge_mat=M["ridge_amber"], loc=(X, Y, z + 0.1))
    box("gate_balc", W * 0.76 + 1.6, D * 0.7 + 1.6, 0.4,
        (X, Y, z + 2.4), M["stone_w"])
    box("gate_b2", W * 0.72, D * 0.66, 3.4, (X, Y, z + 2.6 + 1.7), M["red"])
    plane("gate_b2w", W * 0.72, 3.4, (X, Y - D * 0.33 - 0.01, z + 4.3),
          M["redwall"], rot=(math.pi / 2, 0, 0))
    plane("gate_lat2", W * 0.6, 1.7, (X, Y - D * 0.33 - 0.03, z + 4.55),
          M["lattice"], rot=(math.pi / 2, 0, 0))
    z2 = bands("gate2", M, X, Y, W * 0.72, D * 0.66, z + 6.0, g_h=0.45, d_h=0.6,
               frieze_key="frieze")
    roof("gate_top", W * 0.76 + 2.4, D * 0.7 + 2.4, 4.4, style="xieshan", xr=0.45,
         lift=0.5, reach=0.35, material=M["tile_amber"],
         ridge_mat=M["ridge_amber"], loc=(X, Y, z2 + 0.15))
