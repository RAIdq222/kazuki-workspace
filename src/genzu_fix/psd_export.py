"""PSD 原図 → 表示レイヤー合成 PNG。

これまで手動で Photoshop から「表示レイヤーを PNG 書き出し」していた入口工程を自動化する。
PSD に保存された各レイヤーの可視状態(visible flag)を尊重して合成し、PNG として保存する。

- `export_visible_to_png`: ファイルの可視レイヤーをそのまま合成（既定の挙動）。
- `list_layers`: レイヤー一覧（名前/可視/種別/bbox/階層）を取得。
  → 「絵そのもの」と「指示・補助線」レイヤーの当たりを付ける手がかりに使う。
- `export_with_overrides`: レイヤー名で可視状態を上書きしてから合成。
  → 例: 指示/補助線レイヤーを名前で hide して、絵だけの PNG を作る。

合成は psd_tools の composite() を使い、現在の可視状態を反映する。
透過を残したくない場合は bg に背景色を渡すと、その色で塗り潰した RGB を返す。
"""
from __future__ import annotations
import os
from dataclasses import dataclass, asdict

from psd_tools import PSDImage


@dataclass
class LayerInfo:
    name: str
    visible: bool
    kind: str            # 'pixel' / 'type' / 'group' / 'shape' ...
    bbox: tuple          # (left, top, right, bottom)
    depth: int           # ネストの深さ (0 = トップレベル)


def list_layers(psd_path: str) -> list[LayerInfo]:
    """レイヤーツリーを平坦化して一覧で返す（上から順）。"""
    psd = PSDImage.open(psd_path)
    out: list[LayerInfo] = []

    def walk(layers, depth):
        for layer in layers:
            out.append(LayerInfo(
                name=layer.name,
                visible=bool(layer.visible),
                kind=str(layer.kind),
                bbox=tuple(layer.bbox),
                depth=depth,
            ))
            if layer.is_group():
                walk(layer, depth + 1)

    walk(psd, 0)
    return out


def _flatten(image, bg):
    """RGBA を背景色で合成して RGB にする。bg=None ならそのまま返す。"""
    if bg is None:
        return image
    from PIL import Image
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    canvas = Image.new("RGB", image.size, bg)
    canvas.paste(image, mask=image.split()[-1])
    return canvas


def export_visible_to_png(psd_path: str, out_path: str, bg=(255, 255, 255)):
    """PSD の可視レイヤーを合成して PNG 保存する。

    既定は PSD に保存された合成プレビューを使う（= 保存時の表示状態そのもの・高速）。
    bg: 透過を塗り潰す背景色。None なら透過(RGBA)のまま保存。
    戻り値: (width, height)
    """
    psd = PSDImage.open(psd_path)
    image = psd.composite()  # 保存済みプレビュー = 表示レイヤーの WYSIWYG
    image = _flatten(image, bg)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    image.save(out_path)
    return image.size


def export_with_overrides(psd_path: str, out_path: str,
                          show=None, hide=None, bg=(255, 255, 255)):
    """レイヤー名で可視状態を上書きしてから合成・保存する。

    show: 表示にするレイヤー名の集合 / hide: 非表示にするレイヤー名の集合（完全一致）。
    プレビューには上書きが反映されないため、レイヤーから再レンダリングする
    （composite(ignore_preview=True, layer_filter=...)）。
    戻り値: (width, height)
    """
    show = set(show or [])
    hide = set(hide or [])
    psd = PSDImage.open(psd_path)

    # 全階層（ネスト含む）の可視状態を名前一致で上書きする。
    # layer_filter はトップレベルにしか効かないため使わない。
    for layer in psd.descendants():
        if layer.name in show:
            layer.visible = True
        if layer.name in hide:
            layer.visible = False

    # force=True で保存プレビューを使わず、上書き後の可視状態から再合成する。
    image = _flatten(psd.composite(force=True), bg)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    image.save(out_path)
    return image.size


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) >= 2 and sys.argv[1] == "layers":
        for li in list_layers(sys.argv[2]):
            print(json.dumps(asdict(li), ensure_ascii=False))
    elif len(sys.argv) >= 3:
        print(export_visible_to_png(sys.argv[1], sys.argv[2]))
    else:
        print("usage: psd_export.py <in.psd> <out.png> | layers <in.psd>")
