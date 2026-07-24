# 皇宮キット共通マテリアル (全棟で共有し、mat()の名前キャッシュで一意に保つ)
from stagelib import mat, mat_image

from . import textures


def make_materials():
    tex = textures.build_all()
    return dict(
        stone=mat("stone", (0.60, 0.58, 0.53), rough=0.95),
        stone_w=mat("stone_w", (0.78, 0.76, 0.71), rough=0.9),
        red=mat("red_body", (0.40, 0.13, 0.09), rough=0.85),
        redwall=mat_image("kw_redwall", tex["redwall"], rough=0.9, blend="OPAQUE"),
        col=mat("col_red", (0.52, 0.16, 0.10), rough=0.7),
        gold=mat("gold", (0.62, 0.47, 0.20), rough=0.4),
        tile=mat_image("kw_tile", tex["tile_grey"], rough=0.8, blend="OPAQUE",
                       uv_scale=(1 / 0.35, 1 / 2.0)),
        tile_amber=mat_image("kw_tile_a", tex["tile_amber"], rough=0.75,
                             blend="OPAQUE", uv_scale=(1 / 0.35, 1 / 2.0)),
        ridge=mat("ridge_dark", (0.13, 0.14, 0.15), rough=0.7),
        ridge_amber=mat("ridge_amber", (0.55, 0.30, 0.10), rough=0.6),
        frieze=mat_image("kw_frieze", tex["frieze"], rough=0.7, blend="OPAQUE"),
        frieze_o=mat_image("kw_frieze_o", tex["frieze_o"], rough=0.7, blend="OPAQUE"),
        dougong=mat_image("kw_dougong", tex["dougong"], rough=0.8, blend="OPAQUE"),
        lattice=mat_image("kw_lattice", tex["lattice"], rough=0.65, blend="OPAQUE"),
        sudare=mat_image("kw_sudare", tex["sudare"], rough=0.8, blend="OPAQUE"),
        rough_stone=mat_image("kw_rough", tex["rough_stone"], rough=0.95,
                              blend="OPAQUE"),
        wood_floor=mat("wood_floor", (0.35, 0.24, 0.15), rough=0.6),
        wood_red=mat("wood_red", (0.48, 0.17, 0.11), rough=0.65),
        paving=mat_image("kw_paving", tex["paving"], rough=0.95, blend="OPAQUE",
                         uv_scale=(24, 21)),
        bronze=mat("bronze", (0.16, 0.15, 0.11), rough=0.45),
        fig=mat("fig", (0.15, 0.30, 0.75), rough=0.6),
        tree=mat("tree", (0.23, 0.36, 0.19), rough=0.9),
        ongro=mat_image("kw_ongro_m", tex["ongro"], rough=0.85, blend="OPAQUE"),
    )
