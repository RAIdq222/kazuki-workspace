# 南景国「皇宮」(皇帝の宮殿) マスターレイアウト — Phase 0
# 座標系: 中軸線=Y軸(奥=北=+Y)、原点=皇宮正門中央、X=東が正、1単位=1m、地面z=0
# 一次資料: shz_b08_17 皇宮_主殿 (正面構図) を正とする
# 8話コンテの拘束: 別殿の縁側から主殿前広場がよく見える(c211) / 客間→主殿は長い屋内廊下(c205)
#                  祝殿は大広間+高天井で庭園と隣接(c242) / 庭は塀囲い+池+橋+回廊(c280)
# 様式: 橙琉璃瓦(amber)+赤壁(body="red")。主殿の屋根のみ濃灰(dark)

SITE = dict(x_half=110.0, y0=-2.0, y1=318.0)  # 敷地 220 × 320m

BUILDINGS = [
    # ---- 中軸 (南→北) ----
    dict(id="gate_s", label="皇宮正門(二階重檐)", kind="gate2", x=0, y=0,
         w=26, d=14, face="S", style="amber", body="red", terrace_h=2.5),
    dict(id="fore_court", label="前庭", kind="plaza", x=0, y=34, w=130, d=52),
    dict(id="main_plaza", label="主殿前広場(誕生祭の儀式=c206)", kind="plaza",
         x=0, y=112, w=100, d=88),
    dict(id="censer", label="大香炉(石高欄囲い)", kind="censer", x=0, y=104),
    dict(id="bekkuden", label="別殿(=b08_19、縁側から主殿が見える)", kind="wing",
         x=28, y=110, w=42, d=12, face="W", style="amber", body="red", mirror=True),
    dict(id="main_hall", label="主殿(重檐・濃灰瓦・高基壇+大階段=b08_17)", kind="hall2",
         x=0, y=160, w=34, d=20, face="S", style="dark", body="red",
         terrace=dict(w=64, d=44, h=7.0)),
    # ---- 祝殿と庭園 (北東区) ----
    dict(id="shukuden", label="祝殿(宴の大広間=b08_18)", kind="hall", x=0, y=252,
         w=38, d=24, face="S", style="amber", body="red"),
    dict(id="garden", label="庭園(夕/夜=b08_25)", kind="gravel", x=64, y=262, w=88, d=100),
    dict(id="pond", label="池(橋・c280)", kind="pond", x=60, y=248, w=36, d=20),
    dict(id="g_tower_w", label="庭の楼閣(西)", kind="tower2", x=40, y=298,
         w=13, d=11, face="S", style="amber", body="red", axis=False),
    dict(id="g_tower_e", label="庭の楼閣(東)", kind="tower2", x=90, y=298,
         w=13, d=11, face="S", style="amber", body="red", axis=False),
    dict(id="g_corridor", label="遊廊(楼閣間)", kind="corridor", x=65, y=298,
         w=34, d=3.5, face="S", style="amber", axis=False),
    # ---- 西区: 客間・寝室の院 (youkai_20: 皇帝/皇太后の寝室方向指示) ----
    dict(id="yard_guest", label="客間の院(黙清・尚善が滞在)", kind="yard", x=-75, y=40,
         w=44, d=52, style="amber"),
    dict(id="corridor_guest", label="客間→主殿の屋内廊下(c205)", kind="corridor",
         x=-49.5, y=105, w=90, d=3.5, face="E", style="amber", axis=False),
    dict(id="yard_emp", label="皇帝寝室の院", kind="yard", x=-72, y=210, w=46, d=54,
         style="amber"),
    dict(id="yard_dow", label="皇太后の院", kind="yard", x=-72, y=275, w=46, d=54,
         style="amber"),
    # ---- 隅楼 ----
    dict(id="tw_s", label="隅楼(南)", kind="tower2", x=102, y=8, w=11, d=11,
         face="S", style="amber", body="red", mirror=True),
    dict(id="tw_n", label="隅楼(北)", kind="tower2", x=102, y=307, w=11, d=11,
         face="N", style="amber", body="red", mirror=True),
]

WALLS = [
    # 外周 (正門の開口 ±9)
    dict(id="wall_s_w", p1=(-110, -1), p2=(-9, -1), h=5.0),
    dict(id="wall_s_e", p1=(9, -1), p2=(110, -1), h=5.0),
    dict(id="wall_n", p1=(-110, 317), p2=(110, 317), h=5.0),
    dict(id="wall_w", p1=(-110, -1), p2=(-110, 317), h=5.0),
    dict(id="wall_e", p1=(110, -1), p2=(110, 317), h=5.0),
    # 主殿基壇から左右に伸びる袖塀 (b08_17: 赤壁+橙瓦笠)
    dict(id="wall_main_w", p1=(-110, 160), p2=(-32, 160), h=5.0),
    dict(id="wall_main_e", p1=(32, 160), p2=(110, 160), h=5.0),
    # 前庭と主殿前広場の境 (低め)
    dict(id="wall_f_w", p1=(-110, 62), p2=(-13, 62), h=4.0),
    dict(id="wall_f_e", p1=(13, 62), p2=(110, 62), h=4.0),
]

TREES = [
    (-56, 112, 3.0), (56, 90, 2.8), (60, 140, 3.0), (-58, 150, 2.8),
    (28, 226, 2.8), (-28, 228, 3.0), (54, 282, 3.2), (86, 270, 2.8),
    (46, 240, 2.4), (-74, 42, 2.8), (-74, 212, 3.0), (-70, 278, 2.8),
    (24, 40, 2.6), (-26, 38, 2.6), (90, 226, 3.0),
]

# 人型スケール (1.65m)。サイズ感の検証用
FIGURES = [
    (0, 96), (3, 92), (-14, 66), (20, 108),   # 広場・別殿縁側前
    (8, 120), (5, 116),                        # 大階段の下
    (60, 240),                                 # 庭
]

# カメラ: B=ボードb08_17再現角 / T=俯瞰 / P=配置図 / G=庭(b08_25方向)
CAMS = {
    "B": dict(loc=(0, 30, 7.0), look=(0, 160, 17), lens=45),
    "T": dict(loc=(-150, -45, 115), look=(0, 168, 0), lens=32),
    "P": dict(loc=(0, 158, 330), look=(0, 158.5, 0), lens=20),
    "G": dict(loc=(28, 226, 2.2), look=(85, 292, 8), lens=28),
}


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
