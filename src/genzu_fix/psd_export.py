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


def export_visible_to_png(psd_path: str, out_path: str, bg=(255, 255, 255),
                          drop_text: bool = False):
    """PSD の可視レイヤーを合成して PNG 保存する。

    drop_text=False（既定）: PSD に保存された合成プレビューを使う（= 保存時の表示状態・高速）。
    drop_text=True: テキストレイヤー(kind=='type')を除いて再合成する
        （引継ぎメモ等の文字を入力PNGに含めない。再レンダリングのため少し遅い）。
    bg: 透過を塗り潰す背景色。None なら透過(RGBA)のまま保存。
    戻り値: (width, height)
    """
    psd = PSDImage.open(psd_path)
    if drop_text:
        dropped = 0
        for layer in psd.descendants():
            if str(layer.kind) == "type":
                layer.visible = False
                dropped += 1
        image = psd.composite(force=True)
    else:
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


# 背景作画でない＝常に除外するレイヤー名の手がかり（部分一致・小文字比較）
_EXCLUDE_HINTS = ("美監補足", "指示", "セル参考", "camera", "参考")


def _is_blank(image) -> bool:
    """合成結果が「絵なし」か＝全面透明 or 完全単色（描線が1本も無い）。
    空レイヤー/白紙レイヤーを選んでしまったことの検知に使う。"""
    if image is None:
        return True
    ex = image.getextrema()
    if not isinstance(ex[0], tuple):  # 単バンド
        ex = (ex,)
    if image.mode == "RGBA":
        if ex[3][0] == ex[3][1] == 0:
            return True  # 全面透明
        ex = ex[:3]
    return all(lo == hi for lo, hi in ex)


def export_background_layer(psd_path: str, out_path: str, bg=(255, 255, 255),
                            include_book: bool = False):
    """背景作画レイヤーだけを合成して PNG 保存する（指示/参考/セル/BOOK を除外）。

    選択ロジック（候補を優先順に試し、合成が空＝全面同一色なら次の候補へ落ちる）:
      1) [type](文字) と 美監補足/指示/セル参考/Camera/参考 を含む名前は常に非表示。
      2) 候補の優先順:
         BG …… トップレベルで名前が "BG" 始まり（_BG / BG[group] / _BG_Book◯ を含む。
                BGとBookの統合レイヤーは背景本体として採用する）＋ "PAN" 始まり（引き背景）
         LO …… トップレベルの pixel で "LO" 始まり
         BG(nested) …… グループ内にネストした "BG" 始まりの pixel
                （SP2の 005型: BG[group]の中身が空で、実背景が LO[group]>_BG にあるPSD向け）
         背景 …… トップレベルの「背景」
      3) 名前が "Book" 始まり（Book_1/_book_e 等の別ブック）は既定で除外。
         include_book=True で採用候補に合成する。
      4) どの候補も絵にならなければフォールバック（除外後の可視レイヤーをそのまま合成）。
    戻り値: (width, height, info)  info={"strategy","layers"}。
    """
    psd = PSDImage.open(psd_path)

    def excluded(name: str) -> bool:
        nl = (name or "").lower()
        return any(h.lower() in nl for h in _EXCLUDE_HINTS)

    def norm(l):
        # SP2等は "_BG" "_PAN" のように先頭 _ が付く。判定は _ を剥がして行う。
        return (l.name or "").lstrip("_").lower()

    def starts(l, p):
        return norm(l).startswith(p)

    def is_book(l) -> bool:
        # 「Bookで始まる名前」だけをブック扱いする。_BG_Book はBG本体（統合レイヤー）。
        return norm(l).startswith("book")

    def is_pixel(l):
        return str(l.kind) != "group"

    orig_visible = {id(l): bool(l.visible) for l in psd.descendants()}
    top = list(psd)

    bg_layers = [l for l in top if starts(l, "bg") and not excluded(l.name)]
    pan_layers = [l for l in top if starts(l, "pan") and not excluded(l.name)]
    lo_layers = [l for l in top if is_pixel(l) and starts(l, "lo") and not excluded(l.name)]
    nested_bg = [l for l in psd.descendants()
                 if is_pixel(l) and starts(l, "bg") and not excluded(l.name) and l not in top]
    haikei = [l for l in top if l.name == "背景"]
    book_layers = [l for l in top if is_book(l)]

    candidates = []
    if bg_layers or pan_layers:
        candidates.append(("BG" if bg_layers else "PAN", bg_layers + pan_layers))
    if lo_layers:
        candidates.append(("LO", lo_layers))
    if nested_bg:
        candidates.append(("BG(nested)", nested_bg))
    if haikei:
        candidates.append(("背景", haikei))

    def render(keep_layers):
        """keep_layers(+任意でBOOK)だけが写るように可視状態を組み、再合成する。"""
        keeps = list(keep_layers) + (book_layers if include_book else [])
        kept = {id(l) for l in keeps}
        inside = set()   # 採用したグループの中身＝保存時の可視状態のまま
        anc = set()      # ネスト採用時は先祖グループを表示にしないと写らない
        for x in keeps:
            if x.is_group():
                inside |= {id(d) for d in x.descendants()}
            p = getattr(x, "parent", None)
            while p is not None and p is not psd and getattr(p, "name", None) is not None:
                anc.add(id(p))
                p = getattr(p, "parent", None)
        for l in psd.descendants():
            if str(l.kind) == "type" or excluded(l.name):
                l.visible = False
            elif id(l) in kept or id(l) in anc:
                l.visible = True
            elif id(l) in inside:
                l.visible = orig_visible[id(l)]
            else:
                l.visible = False
        return psd.composite(force=True)

    image, strategy, used = None, "fallback", []
    for name, layers in candidates:
        img = render(layers)
        if not _is_blank(img):
            image, strategy, used = img, name, layers
            break

    if image is None:
        # フォールバック: 保存時の可視状態に戻し、文字/指示/BOOKだけ隠して合成
        for l in psd.descendants():
            l.visible = orig_visible[id(l)]
        for l in psd.descendants():
            if str(l.kind) == "type" or excluded(l.name):
                l.visible = False
        if not include_book:
            for l in book_layers:
                l.visible = False
        image = psd.composite(force=True)

    image = _flatten(image, bg)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    image.save(out_path)
    used_all = list(used) + (book_layers if (include_book and used) else [])
    info = {"strategy": strategy, "layers": [l.name for l in used_all]}
    return image.size[0], image.size[1], info


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
