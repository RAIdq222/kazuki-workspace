"""
原図 → GPT Image 2 入力用の比率/解像度調整モジュール。

設計方針（黒江さんの要件）:
- 原図の拡大縮小・比率は変えない。足りない分は「余白(パディング)」で補う。
- GPT Image 2 が受け付ける比率は整数比の固定リストのみ:
    1:1, 4:3, 3:4, 16:9, 9:16, 3:2, 2:3
- 解像度ティアは 1k / 2k / 4k の3種類のみ。
- 出力は要求した比率と厳密には一致しないことがある
  → 復元(crop back)は「絶対座標」ではなく「相対座標(割合)」で行い、ズレに強くする。

使い方:
    prep = prepare_for_gpt_image(src_w, src_h)
    # prep.aspect_ratio を生成APIの aspect_ratio に渡す
    # 原図を prep.canvas_w x prep.canvas_h のキャンバス中央に貼って入力画像にする
    # 生成結果を restore_to_original(gen_w, gen_h, prep) で元画角に切り戻す
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log


# GPT Image 2 が受け付ける比率（分子, 分母, ラベル）
ALLOWED_RATIOS: list[tuple[int, int, str]] = [
    (1, 1, "1:1"),
    (4, 3, "4:3"),
    (3, 4, "3:4"),
    (16, 9, "16:9"),
    (9, 16, "9:16"),
    (3, 2, "3:2"),
    (2, 3, "2:3"),
]


@dataclass
class PrepResult:
    """前処理の結果。入力画像の作り方と、復元に必要な情報を保持する。"""

    aspect_ratio: str           # 生成APIに渡す比率ラベル (例 "3:2")
    canvas_w: int               # パディング後キャンバス幅
    canvas_h: int               # パディング後キャンバス高さ
    paste_x: int                # 原図を貼る左上X
    paste_y: int                # 原図を貼る左上Y
    src_w: int                  # 元の幅
    src_h: int                  # 元の高さ
    # 復元用: 原図がキャンバス内で占める領域を「割合」で持つ（出力比のズレに強い）
    frac_left: float
    frac_top: float
    frac_right: float
    frac_bottom: float


def choose_aspect_ratio(src_w: int, src_h: int) -> tuple[int, int, str]:
    """原図の比率に最も近い許容比率を選ぶ（パディング量が最小になる比率）。"""
    src_r = src_w / src_h
    # log空間での距離が最小 = 縦横どちらに足す場合でも余白が最小
    best = min(ALLOWED_RATIOS, key=lambda r: abs(log((r[0] / r[1]) / src_r)))
    return best


def prepare_for_gpt_image(src_w: int, src_h: int) -> PrepResult:
    """原図サイズから、パディング後キャンバスと復元情報を計算する。"""
    rw, rh, label = choose_aspect_ratio(src_w, src_h)
    target_r = rw / rh
    src_r = src_w / src_h

    if target_r >= src_r:
        # 目標が原図より横長 → 左右に余白(ピラーボックス)
        canvas_h = src_h
        canvas_w = round(src_h * target_r)
    else:
        # 目標が原図より縦長 → 上下に余白(レターボックス)
        canvas_w = src_w
        canvas_h = round(src_w / target_r)

    paste_x = (canvas_w - src_w) // 2
    paste_y = (canvas_h - src_h) // 2

    return PrepResult(
        aspect_ratio=label,
        canvas_w=canvas_w,
        canvas_h=canvas_h,
        paste_x=paste_x,
        paste_y=paste_y,
        src_w=src_w,
        src_h=src_h,
        frac_left=paste_x / canvas_w,
        frac_top=paste_y / canvas_h,
        frac_right=(paste_x + src_w) / canvas_w,
        frac_bottom=(paste_y + src_h) / canvas_h,
    )


def restore_crop_box(gen_w: int, gen_h: int, prep: PrepResult) -> tuple[int, int, int, int]:
    """生成結果(gen_w x gen_h)から、原図に対応する領域の crop box を返す。

    出力比が要求比と厳密一致しなくても、相対座標で切るのでズレに強い。
    返り値は (left, top, right, bottom) のピクセル座標。
    """
    left = round(prep.frac_left * gen_w)
    top = round(prep.frac_top * gen_h)
    right = round(prep.frac_right * gen_w)
    bottom = round(prep.frac_bottom * gen_h)
    return left, top, right, bottom


# --- 実画像に対する処理（PIL）。設計検証用の薄いラッパ。---

def build_input_image(src_path: str, out_path: str, pad_color=(255, 255, 255)) -> PrepResult:
    """原図を読み込み、パディングして入力画像を書き出す。PrepResult を返す。"""
    from PIL import Image

    im = Image.open(src_path).convert("RGB")
    prep = prepare_for_gpt_image(im.width, im.height)
    canvas = Image.new("RGB", (prep.canvas_w, prep.canvas_h), pad_color)
    canvas.paste(im, (prep.paste_x, prep.paste_y))
    canvas.save(out_path)
    return prep


def restore_output_image(gen_path: str, out_path: str, prep: PrepResult) -> None:
    """生成結果から余白を切り戻し、元の画角・解像度に合わせて保存する。"""
    from PIL import Image

    gen = Image.open(gen_path).convert("RGB")
    box = restore_crop_box(gen.width, gen.height, prep)
    cropped = gen.crop(box)
    # 元の原図と同じ画素数に戻す（比較・PSD格納用）
    restored = cropped.resize((prep.src_w, prep.src_h), Image.LANCZOS)
    restored.save(out_path)
