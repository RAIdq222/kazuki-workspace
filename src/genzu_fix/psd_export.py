"""PSD 原図 → 表示レイヤー合成 PNG。

これまで手動で Photoshop から「表示レイヤーを PNG 書き出し」していた入口工程を自動化する。
PSD に保存された各レイヤーの可視状態(visible flag)を尊重して合成し、PNG として保存する。

- `export_visible_to_png`: ファイルの可視レイヤーをそのまま合成（既定の挙動）。
- `list_layers`: レイヤー一覧（名前/可視/種別/bbox/階層）を取得。
  → 「絵そのもの」と「指示・補助線」レイヤーの当たりを付ける手がかりに使う。
- `export_with_overrides`: レイヤー名で可視状態を上書きしてから合成。
  → 例: 指示/補助線レイヤーを名前で hide して、絵だけの PNG を作る。
- `insert_result_layer`: 生成結果(PNG)を元PSDに新規レイヤーとして差し込んで保存。
  → 最終成果物。レイヤー名は既定「AI原図修正」、リテイクは枝番(_02, _03…)で積む。

合成は psd_tools の composite() を使い、現在の可視状態を反映する。
透過を残したくない場合は bg に背景色を渡すと、その色で塗り潰した RGB を返す。
"""
from __future__ import annotations
import os
from dataclasses import dataclass, asdict

from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer


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


def _next_retake_name(existing_names, base: str) -> str:
    """既存レイヤー名の集合から、次に使う名前を決める。
    base が無ければ base、あれば base_02, base_03 … と枝番を採番する。
    """
    if base not in existing_names:
        return base
    i = 2
    while f"{base}_{i:02d}" in existing_names:
        i += 1
    return f"{base}_{i:02d}"


def insert_result_layer(psd_path: str, image_path: str, out_psd_path: str,
                        base_name: str = "AI原図修正"):
    """生成結果(PNG)を元PSDの最上位に新規レイヤーとして差し込み、別PSDとして保存する。

    - 元のレイヤー構成はそのまま保持し、結果を一番上（最前面）に重ねる。
    - レイヤー名は base_name。既に同名があればリテイクとみなし _02, _03 … と採番。
    - 画像サイズがキャンバスと違う場合はキャンバスに合わせて拡縮する。
    - 日本語レイヤー名は psd-tools の name セッター経由で Unicode 名(luni)として保存する
      （PSD レガシー名は macroman 不可なら "?" になるが、Photoshop は luni を表示する）。
    戻り値: 実際に付けたレイヤー名。
    """
    from PIL import Image
    psd = PSDImage.open(psd_path)
    img = Image.open(image_path).convert("RGBA")
    if img.size != (psd.width, psd.height):
        img = img.resize((psd.width, psd.height), Image.LANCZOS)

    name = _next_retake_name({l.name for l in psd.descendants()}, base_name)
    # frompil は parent(psd) の末尾＝最前面に追加する。
    layer = PixelLayer.frompil(img, psd, name="_ai_result_tmp", top=0, left=0)
    layer.name = name  # 賢いセッターで Unicode 名を luni に格納
    psd.save(out_psd_path)
    return name


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) >= 2 and sys.argv[1] == "layers":
        for li in list_layers(sys.argv[2]):
            print(json.dumps(asdict(li), ensure_ascii=False))
    elif len(sys.argv) >= 3:
        print(export_visible_to_png(sys.argv[1], sys.argv[2]))
    else:
        print("usage: psd_export.py <in.psd> <out.png> | layers <in.psd>")
