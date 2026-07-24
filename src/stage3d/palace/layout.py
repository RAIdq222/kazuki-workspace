# 南景国「宮邸」(呂仁邸) マスターレイアウト — Phase 0
# 座標系: 中軸線=Y軸(奥=北=+Y)、原点=玄関門中央、X=東が正、1単位=1m、地面z=0
# 一次資料: shz_b08_01 宮邸(宮廷)_全景 を正とする (docs/palace-sources.md §2/§8)
#
# 8話コンテの確定事項:
#   ・「宮廷」ボード=宮邸(呂仁の私邸、灰瓦系)。「皇宮」(橙瓦系: 主殿/祝殿/別殿/庭)は
#     別複合体 → 皇宮は別フィールドとして後日設計 (このファイルは宮邸のみ)
#   ・宮邸の要素: 玄関(=b08_08、c72 門前見送り) / 書斎 / 尚善の部屋 /
#     庭の渡り廊下+池(c2 鯉) / 裏庭にも池+回廊(c141)
# style は宮邸=全棟 "grey"。正殿のみ "dark"(格の表現)

SITE = dict(x_half=95.0, y0=-2.0, y1=278.0)  # 敷地 190 × 280m (王府級の私邸)

BUILDINGS = [
    # ---- 中軸 (南→北) ----
    dict(id="entry_gate", label="玄関門(アーチ破風=b08_08)", kind="gate_arch", x=0, y=0,
         w=14, d=8, face="S", style="grey"),
    dict(id="fore_plaza", label="前庭(石畳)", kind="plaza", x=0, y=24, w=110, d=38),
    dict(id="mid_gate", label="中門楼(二階重檐=b08_01左奥)", kind="gate2", x=0, y=48,
         w=24, d=13, face="S", style="grey", terrace_h=2.2),
    dict(id="main_court", label="正殿前庭(庭木あり)", kind="plaza", x=0, y=84, w=104, d=56),
    dict(id="side_hall", label="配殿", kind="hall_s", x=36, y=82,
         w=22, d=11, face="W", style="grey", mirror=True),
    dict(id="main_hall", label="正殿(重檐+前面柱廊=b08_01中央奥)", kind="hall2",
         x=0, y=124, w=32, d=18, face="S", style="dark",
         terrace=dict(w=44, d=30, h=3.0)),
    dict(id="gallery_e", label="高架通路(白石高欄)", kind="gallery", x=54, y=124,
         w=62, d=4, face="S", style="grey"),
    dict(id="rear_gate", label="後門(掖門)", kind="hall_s", x=0, y=146,
         w=9, d=5, face="S", style="grey"),
    # ---- 裏庭 (c2/c141: 池+渡り廊下+飛び石) ----
    dict(id="rear_garden", label="裏庭(池の庭)", kind="gravel", x=0, y=180, w=104, d=60),
    dict(id="pond", label="池(鯉)", kind="pond", x=-12, y=182, w=46, d=26),
    dict(id="garden_corridor", label="渡り廊下", kind="corridor", x=6, y=180,
         w=70, d=3.5, face="S", style="grey", axis=False),  # 池を渡る意図的な非対称
    dict(id="pavilion", label="東屋", kind="pavilion", x=34, y=194,
         w=7, d=7, face="S", style="grey"),
    # ---- 奥の居住列 ----
    dict(id="rear_hall_c", label="奥殿(中央)", kind="hall_s", x=0, y=234,
         w=20, d=11, face="S", style="grey"),
    dict(id="rear_hall", label="奥小殿", kind="hall_s", x=48, y=232,
         w=15, d=10, face="S", style="grey", mirror=True),

    # ---- 左右対称/非対称の要素 ----
    dict(id="corner_tower_s", label="隅楼(南)二階楼閣", kind="tower2", x=86, y=8,
         w=11, d=11, face="S", style="grey", mirror=True),
    dict(id="corner_tower_n", label="隅楼(北)", kind="tower2", x=86, y=268,
         w=11, d=11, face="N", style="grey", mirror=True),
    dict(id="tower_w", label="西楼(b08_01左端の楼閣列)", kind="tower2", x=-87, y=126,
         w=11, d=11, face="E", style="grey"),
    # 白壁の小院 (宮邸の居住区: 書斎/寝室/尚善の部屋の候補地)
    dict(id="yard_w1", label="西小院1(書斎候補)", kind="yard", x=-62, y=88,
         w=38, d=46, style="grey"),
    dict(id="yard_w2", label="西小院2(黙清寝室候補)", kind="yard", x=-62, y=158,
         w=38, d=46, style="grey"),
    dict(id="yard_e1", label="東小院1(尚善の部屋候補)", kind="yard", x=62, y=88,
         w=38, d=46, style="grey"),
    dict(id="yard_e2", label="東小院2", kind="yard", x=62, y=176,
         w=38, d=48, style="grey"),
]

WALLS = [
    # 外周 (白漆喰+灰瓦笠 h4.5)。南辺は玄関門の開口を確保
    dict(id="wall_s_w", p1=(-95, -1), p2=(-8, -1), h=4.5),
    dict(id="wall_s_e", p1=(8, -1), p2=(95, -1), h=4.5),
    dict(id="wall_n", p1=(-95, 277), p2=(95, 277), h=4.5),
    dict(id="wall_w", p1=(-95, -1), p2=(-95, 277), h=4.5),
    dict(id="wall_e", p1=(95, -1), p2=(95, 277), h=4.5),
    # 中門ライン (前庭と正殿域の境)
    dict(id="wall_m_w", p1=(-95, 48), p2=(-13, 48), h=4.0),
    dict(id="wall_m_e", p1=(13, 48), p2=(95, 48), h=4.0),
    # 正殿域と裏庭の境 (後門の左右)
    dict(id="wall_r_w", p1=(-95, 146), p2=(-5.5, 146), h=4.0),
    dict(id="wall_r_e", p1=(5.5, 146), p2=(95, 146), h=4.0),
    # 裏庭と奥居住列の境
    dict(id="wall_b_w", p1=(-95, 214), p2=(-6, 214), h=3.5),
    dict(id="wall_b_e", p1=(6, 214), p2=(95, 214), h=3.5),
]

# 庭木 (x, y, 樹冠半径)。b08_01「中庭に樹木が多い」
TREES = [
    (-34, 76, 3.2), (34, 96, 2.8), (-38, 100, 3.0), (24, 70, 2.6),
    (-20, 196, 2.8), (18, 168, 2.4), (-34, 166, 3.0), (30, 206, 3.2),
    (-62, 90, 2.8), (-60, 162, 3.0), (62, 92, 2.8), (60, 180, 3.0),
    (-44, 26, 2.6), (44, 24, 2.6), (0, 250, 2.8), (-40, 240, 2.6),
]


def expand(buildings=None):
    """mirror=True のエントリを x 反転コピーで展開して返す."""
    out = []
    for b in (buildings if buildings is not None else BUILDINGS):
        out.append(b)
        if b.get("mirror"):
            m = dict(b)
            m["id"] = b["id"] + "_m"
            m["x"] = -b["x"]
            m["face"] = {"E": "W", "W": "E"}.get(b.get("face", "S"), b.get("face", "S"))
            m["mirror"] = False
            out.append(m)
    return out
