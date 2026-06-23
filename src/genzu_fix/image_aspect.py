"""
原図 → GPT Image 2 入力用の比率/解像度調整モジュール。

設計方針（黒江さんの要件・2026-06-23 改訂）:
- **入力画像を GPT Image 2 の「出力解像度」ぴったりに作る**。
  入力 canvas 寸 == 生成出力寸（同一ピクセルグリッド）なら、本体は出力でも
  まったく同じ整数座標に居る。よって入力作成の逆処理（クロップ／余白除去）で
  原図画角へ戻すとき、**幾何的にズレようがない**。残るズレは生成の描き直し由来のみ。
- 原図の拡大縮小・比率は「出力グリッドに収めるための一様スケール」のみ許す
  （アスペクトは保存）。足りない分は余白(パディング)で補う。
- GPT Image 2 が受け付ける比率は固定リスト（1:1,4:3,3:4,16:9,9:16,3:2,2:3）だが、
  **実際の出力寸は公称比と一致しない**（例 3:2 要求 → 2048x1360=1.5059）。
  そこで公称比ではなく「実測出力寸」で最近傍比率を選び、その寸法で入力を作る。

使い方:
    prep = build_input_image(src_path, out_path, resolution="2k")
    # prep.aspect_ratio を生成APIの aspect_ratio、resolution を resolution に渡す
    # 生成結果(prep.canvas_w x prep.canvas_h と同寸のはず)を
    # restore_output_image(gen_path, out_path, prep) で元画角に切り戻す

GPT Image 2 の実測出力寸は GPT_OUTPUT_SIZES に蓄える（観測で更新）。未知の比率/tier は
probe_output_size() で1回生成して学習するか、転置(4:3↔3:4 等)から推定する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import log


# GPT Image 2 が受け付ける比率ラベル（API へ渡す値）
ALLOWED_RATIOS: list[str] = ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3"]

# GPT Image 2 の「実測」出力寸（resolution tier ごと, label -> (w, h)）。
# 観測で確定したものを入れる。未観測は _mirror で転置から推定（要検証）。
GPT_OUTPUT_SIZES: dict[str, dict[str, tuple[int, int]]] = {
    "2k": {
        # --- 実測（ep7 a1 ほか）---
        "4:3": (2336, 1744),
        "3:2": (2048, 1360),
        "16:9": (2688, 1520),
        # --- 転置からの推定（未観測。観測で上書きすること）---
        "3:4": (1744, 2336),
        "2:3": (1360, 2048),
        "9:16": (1520, 2688),
        # "1:1": (????, ????)  # 未観測
    },
}


@dataclass
class PrepResult:
    """前処理の結果。入力の作り方と、復元(逆処理)に必要な情報を保持する。"""

    aspect_ratio: str           # 生成APIに渡す比率ラベル (例 "3:2")
    canvas_w: int               # 入力キャンバス幅 = 生成出力幅（同一グリッド）
    canvas_h: int               # 入力キャンバス高さ = 生成出力高さ
    paste_x: int                # スケール済み本体を貼る左上X
    paste_y: int                # スケール済み本体を貼る左上Y
    src_w: int                  # 元(本体)の幅
    src_h: int                  # 元(本体)の高さ
    # 逆処理(切り戻し)用: 本体をキャンバスへ収めた一様スケールと、スケール後の寸法。
    # これらがあれば「貼り付け座標で厳密にクロップ→元寸へ戻す」が逆処理として成立。
    scale: float = 1.0          # 本体→入力 の一様縮尺 (canvas に収めるための min スケール)
    scaled_w: int = 0           # 入力内での本体幅 (= round(src_w*scale))
    scaled_h: int = 0           # 入力内での本体高さ
    resolution: str = "2k"
    # 後方互換: 旧 prep(割合方式)も読めるよう frac_* を保持（新規でも算出して入れる）
    frac_left: float = 0.0
    frac_top: float = 0.0
    frac_right: float = 1.0
    frac_bottom: float = 1.0


def output_size(label: str, resolution: str = "2k") -> tuple[int, int] | None:
    """指定 (比率, tier) の GPT Image 2 実測出力寸。未知なら None。"""
    return GPT_OUTPUT_SIZES.get(resolution, {}).get(label)


def choose_aspect_ratio(src_w: int, src_h: int, resolution: str = "2k") -> str:
    """本体比率に最も近い「実測出力寸の比率」を選ぶ（パディング量が最小の比率）。

    公称比(3:2=1.5)ではなく実出力寸の比(2048/1360=1.5059)で距離を測る。
    実測寸が判っている比率の中から選ぶ。
    """
    src_r = src_w / src_h
    sizes = GPT_OUTPUT_SIZES.get(resolution, {})
    if not sizes:
        raise ValueError(f"未知の resolution tier: {resolution}（GPT_OUTPUT_SIZES に実測寸が無い）")
    return min(sizes, key=lambda lab: abs(log((sizes[lab][0] / sizes[lab][1]) / src_r)))


def prepare_to_output(src_w: int, src_h: int, out_w: int, out_h: int,
                      label: str, resolution: str = "2k") -> PrepResult:
    """本体(src)を出力寸(out_w x out_h)のキャンバスに、アスペクト保存で収める前処理。

    一様スケール = min(out_w/src_w, out_h/src_h)（はみ出さず最大化）。
    余りは中央寄せの余白。canvas は出力寸そのもの＝生成出力と同一グリッド。
    """
    scale = min(out_w / src_w, out_h / src_h)
    sw = round(src_w * scale)
    sh = round(src_h * scale)
    # 丸めで出力寸を超えないようにクランプ
    sw = min(sw, out_w)
    sh = min(sh, out_h)
    px = (out_w - sw) // 2
    py = (out_h - sh) // 2
    return PrepResult(
        aspect_ratio=label,
        canvas_w=out_w, canvas_h=out_h,
        paste_x=px, paste_y=py,
        src_w=src_w, src_h=src_h,
        scale=scale, scaled_w=sw, scaled_h=sh,
        resolution=resolution,
        frac_left=px / out_w, frac_top=py / out_h,
        frac_right=(px + sw) / out_w, frac_bottom=(py + sh) / out_h,
    )


def prepare_for_gpt_image(src_w: int, src_h: int, resolution: str = "2k") -> PrepResult:
    """本体サイズから、出力寸ぴったりの入力キャンバスと逆処理情報を計算する。"""
    label = choose_aspect_ratio(src_w, src_h, resolution)
    out_w, out_h = output_size(label, resolution)
    return prepare_to_output(src_w, src_h, out_w, out_h, label, resolution)


def restore_crop_box(gen_w: int, gen_h: int, prep: PrepResult) -> tuple[int, int, int, int]:
    """生成結果から本体領域の crop box を返す（後方互換: 旧 prep の割合方式）。

    新方式（出力寸一致）では入力==出力グリッドなので、貼り付け座標 (paste_x/y) を
    そのまま使うのが厳密。比率がズレた出力に割合を当てる旧方式はズレ得る。
    """
    left = round(prep.frac_left * gen_w)
    top = round(prep.frac_top * gen_h)
    right = round(prep.frac_right * gen_w)
    bottom = round(prep.frac_bottom * gen_h)
    return left, top, right, bottom


# --- 実画像に対する処理（PIL）---

def build_input_image(src_path: str, out_path: str, pad_color=(255, 255, 255),
                      resolution: str = "2k") -> PrepResult:
    """本体を読み込み、GPT Image 2 の出力寸キャンバスに収めて入力画像を書き出す。"""
    from PIL import Image

    im = Image.open(src_path).convert("RGB")
    prep = prepare_for_gpt_image(im.width, im.height, resolution)
    scaled = im.resize((prep.scaled_w, prep.scaled_h), Image.LANCZOS)
    canvas = Image.new("RGB", (prep.canvas_w, prep.canvas_h), pad_color)
    canvas.paste(scaled, (prep.paste_x, prep.paste_y))
    canvas.save(out_path)
    return prep


def restore_output_image(gen_path: str, out_path: str, prep: PrepResult) -> None:
    """生成結果を入力作成の逆処理で元画角へ切り戻す。

    入力キャンバス(prep.canvas)＝生成出力 が同一グリッドである前提（新方式）。
    生成寸が canvas と違う場合のみ canvas 寸へリサイズして整合させてから、
    貼り付け座標で厳密にクロップ→元(本体)寸へ戻す。これで幾何のズレは生じない。
    """
    from PIL import Image

    gen = Image.open(gen_path).convert("RGB")
    if (gen.width, gen.height) != (prep.canvas_w, prep.canvas_h):
        # 出力寸が想定と違う＝GPT_OUTPUT_SIZES 未学習等。canvas へ合わせて整合をとる。
        gen = gen.resize((prep.canvas_w, prep.canvas_h), Image.LANCZOS)

    if prep.scaled_w and prep.scaled_h:
        # 新方式: 入力作成の厳密な逆（整数座標でクロップ → 一様スケールの逆で元寸へ）
        box = (prep.paste_x, prep.paste_y,
               prep.paste_x + prep.scaled_w, prep.paste_y + prep.scaled_h)
    else:
        # 後方互換: 旧 prep（割合方式）
        box = restore_crop_box(gen.width, gen.height, prep)

    cropped = gen.crop(box)
    restored = cropped.resize((prep.src_w, prep.src_h), Image.LANCZOS)
    restored.save(out_path)


def probe_output_size(gen_path: str, label: str, resolution: str = "2k") -> tuple[int, int]:
    """生成済み画像の寸法を観測して GPT_OUTPUT_SIZES を更新する（未知比率/tierの学習用）。"""
    from PIL import Image

    w, h = Image.open(gen_path).size
    GPT_OUTPUT_SIZES.setdefault(resolution, {})[label] = (w, h)
    return (w, h)
