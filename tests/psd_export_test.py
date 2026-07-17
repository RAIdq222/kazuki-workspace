"""psd_export.export_background_layer のレイヤー選択規則テスト（合成PSD・実データ不要）。

SP2#10 の実調査（runs/sp2_10_layers.txt）で確認した3構造＋尚善回帰を固定する:
  - 007型: _BG_Book(統合レイヤー) + セル → _BG_Book をBG本体として採用（Book除外しない）
  - 006型: _BG_Book0 + _PAN + Book_n + セル → BG+PAN を採用、Book_n/セルは除外
  - 005型: BG[group](中身が空) + LO[group](_BG+セル) → 空を検知して LO内の _BG へ落ちる
  - 尚善型: _BG + セル / LOピクセル / 「背景」 / include_book

実行: PYTHONPATH=src python tests/psd_export_test.py
※ レイヤー名はASCIIのみ（psd-tools が日本語レガシー名を書けないため）。「背景」規則は
  実PSD由来のため合成テストでは扱わない。
"""
from __future__ import annotations
import os, sys, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from PIL import Image
from psd_tools import PSDImage
from psd_tools.api.layers import Group, PixelLayer

from genzu_fix import psd_export

SIZE = (64, 48)
GREEN = (60, 200, 90, 255)   # 背景（正解）
BLUE = (60, 80, 220, 255)    # PAN背景（正解に含まれてよい）
RED = (220, 60, 60, 255)     # セル/Book（写ってはいけない）


def _solid(color):
    # 完全単色は _is_blank が「絵なし」と判定するため、描線に相当する黒線を1本入れる
    im = Image.new("RGBA", SIZE, color)
    for x in range(SIZE[0]):
        im.putpixel((x, SIZE[1] // 2), (0, 0, 0, 255))
    return im


def _empty():
    return Image.new("RGBA", SIZE, (0, 0, 0, 0))


def _build(tmp, name, spec):
    """spec: [(名前, 色 or None(空) or dict(グループ)), ...] からPSDを作る。"""
    psd = PSDImage.new("RGB", SIZE)

    def add(parent, items):
        for nm, val in items:
            if isinstance(val, list):
                g = Group.new(parent, name=nm)
                add(g, val)
            else:
                PixelLayer.frompil(_solid(val) if val else _empty(), parent, name=nm)

    add(psd, spec)
    path = os.path.join(tmp, name + ".psd")
    psd.save(path)
    return path


def _colors(png):
    im = Image.open(png).convert("RGB")
    return set(im.getdata())


def main():
    tmp = tempfile.mkdtemp(prefix="psdexp_")
    out = os.path.join(tmp, "o.png")
    failures = []

    def check(name, cond, extra=""):
        print(("ok  " if cond else "FAIL") + " " + name + (f"  ({extra})" if extra and not cond else ""))
        if not cond:
            failures.append(name)

    # 007型: _BG_Book + セル → BG採用（統合レイヤーをBookとして捨てない）
    p = _build(tmp, "t007", [("_BG_Book", GREEN[:3]), ("A0002", RED[:3])])
    w, h, info = psd_export.export_background_layer(p, out)
    c = _colors(out)
    check("007型: strategy=BG", info["strategy"] == "BG", str(info))
    check("007型: _BG_Bookが写る", GREEN[:3] in c)
    check("007型: セルは写らない", RED[:3] not in c)

    # 006型: _BG_Book0 + _PAN + Book_1 + セル → BG+PAN、Book/セル除外
    p = _build(tmp, "t006", [("_BG_Book0", GREEN[:3]), ("_PAN", BLUE[:3]),
                             ("Book_1", RED[:3]), ("A1", RED[:3])])
    w, h, info = psd_export.export_background_layer(p, out)
    c = _colors(out)
    check("006型: strategy=BG", info["strategy"] == "BG", str(info))
    check("006型: Book_1/セルは写らない", RED[:3] not in c)
    check("006型: layersにBG+PAN", set(info["layers"]) == {"_BG_Book0", "_PAN"}, str(info))

    # 005型: BG[group]の中身が空 → 空白検知で LO[group]内の _BG へ
    p = _build(tmp, "t005", [("BG", [("0", None)]),
                             ("LO", [("_BG", GREEN[:3]), ("A1", RED[:3])]),
                             ("fr", RED[:3])])
    w, h, info = psd_export.export_background_layer(p, out)
    c = _colors(out)
    check("005型: strategy=BG(nested)", info["strategy"] == "BG(nested)", str(info))
    check("005型: LO内_BGが写る", GREEN[:3] in c)
    check("005型: セル/frは写らない", RED[:3] not in c)

    # 尚善回帰: _BG + セル
    p = _build(tmp, "tshz", [("_BG", GREEN[:3]), ("A1", RED[:3])])
    w, h, info = psd_export.export_background_layer(p, out)
    c = _colors(out)
    check("尚善型: strategy=BG", info["strategy"] == "BG", str(info))
    check("尚善型: _BGのみ", GREEN[:3] in c and RED[:3] not in c)

    # LO(ピクセル)フォールバック: BG無し
    p = _build(tmp, "tlo", [("LO_bg", GREEN[:3]), ("A1", RED[:3])])
    w, h, info = psd_export.export_background_layer(p, out)
    c = _colors(out)
    check("LO型: strategy=LO", info["strategy"] == "LO", str(info))
    check("LO型: LOのみ写る", GREEN[:3] in c and RED[:3] not in c)

    # include_book: Book_1 を合成に含める
    p = _build(tmp, "tbook", [("_BG", GREEN[:3]), ("Book_1", BLUE[:3]), ("A1", RED[:3])])
    w, h, info = psd_export.export_background_layer(p, out, include_book=True)
    c = _colors(out)
    check("include_book: Bookが写る", BLUE[:3] in c, str(info))
    check("include_book: セルは写らない", RED[:3] not in c)

    # BGもLOも無し → fallback（可視レイヤーそのまま）
    p = _build(tmp, "tfb", [("Z1", GREEN[:3])])
    w, h, info = psd_export.export_background_layer(p, out)
    check("fallback: strategy=fallback", info["strategy"] == "fallback", str(info))

    if failures:
        print(f"\n{len(failures)} 件失敗: {failures}")
        return 1
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
