"""生成の幾何デバッグ — 「構図のずれ」がどの段で入ったかを1枚で見えるようにする。

疑いの段は3つ:
  A) 前処理（本体→出力グリッドへのパディング）… input.png と prep.json で検証
  B) 生成（モデルが枠・パディング・アイレベルを守ったか）… input と gen_raw の重ね合わせで検証
  C) 復元（クロップ→元寸）… visible と restored_full の重ね合わせで検証
出力（各カットの出力フォルダ内 / --handoff 指定でgit共有用縮小jpgも）:
  debug_B_input_vs_gen.png   … 入力と生成RAWの50%ブレンド＋パディング境界(青)＋EYE線(赤)
  debug_C_src_vs_restored.png… 元絵と復元結果の50%ブレンド
  ＋ 数値レポート（キャンバス寸・パディング・生成実寸の一致/不一致）

使い方:
  python scripts/debug_geometry.py "<出力先>\\SP2_10_290" [--handoff handoff/SP2_10/geom]
"""
from __future__ import annotations
import argparse
import json
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def _blend(a, b):
    from PIL import Image
    if b.size != a.size:
        b = b.resize(a.size)
    return Image.blend(a.convert("RGB"), b.convert("RGB"), 0.5)


def _draw_guides(im, prep, eye_frac=None):
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    x0, y0 = prep["paste_x"], prep["paste_y"]
    x1, y1 = x0 + prep["scaled_w"], y0 + prep["scaled_h"]
    d.rectangle([x0, y0, x1 - 1, y1 - 1], outline=(0, 90, 255), width=4)  # 本体領域=青
    if eye_frac is not None:
        y = round(eye_frac * im.height)
        d.line([(0, y), (im.width, y)], fill=(255, 0, 0), width=4)        # 検出EYE=赤
    return im


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="debug_geometry", description=__doc__)
    p.add_argument("out_dir", help="カットの出力フォルダ（input.png/gen_raw.png がある場所）")
    p.add_argument("--handoff", default="", help="git共有用の縮小jpgも書き出すフォルダ")
    a = p.parse_args(argv)

    from PIL import Image
    from genzu_fix import image_aspect, batch

    d = a.out_dir
    paths = {k: os.path.join(d, f"{k}.png") for k in ("visible", "input", "gen_raw", "restored_full")}
    missing = [k for k, v in paths.items() if not os.path.exists(v)]
    if missing:
        print(f"[!] 不足: {missing}（生成済みのカットで実行してください）")
        return 1

    # prep: 保存済みがあれば使い、無ければ visible 寸から同じ計算で再現
    prep_path = os.path.join(d, "prep.json")
    if os.path.exists(prep_path):
        prep = json.load(open(prep_path, encoding="utf-8"))
        prep_src = "prep.json"
    else:
        im = Image.open(paths["visible"])
        pr = image_aspect.prepare_for_gpt_image(im.width, im.height, "2k")
        prep = {k: getattr(pr, k) for k in ("aspect_ratio", "canvas_w", "canvas_h",
                                            "paste_x", "paste_y", "src_w", "src_h",
                                            "scale", "scaled_w", "scaled_h")}
        prep_src = "visible寸から再計算（旧生成のため）"

    inp = Image.open(paths["input"])
    gen = Image.open(paths["gen_raw"])
    eye = batch._detect_eye_level(paths["input"])

    print(f"== 幾何レポート: {d}")
    print(f"  prep: {prep_src}")
    print(f"  本体(src): {prep['src_w']}x{prep['src_h']}  scale={prep['scale']:.4f}")
    print(f"  入力キャンバス: {prep['canvas_w']}x{prep['canvas_h']} ({prep['aspect_ratio']})  "
          f"実input: {inp.width}x{inp.height} {'OK' if inp.size==(prep['canvas_w'],prep['canvas_h']) else '!!不一致'}")
    pad_l, pad_t = prep["paste_x"], prep["paste_y"]
    pad_r = prep["canvas_w"] - pad_l - prep["scaled_w"]
    pad_b = prep["canvas_h"] - pad_t - prep["scaled_h"]
    print(f"  パディング: 左{pad_l} 右{pad_r} 上{pad_t} 下{pad_b} px")
    ok = gen.size == (prep["canvas_w"], prep["canvas_h"])
    print(f"  生成RAW実寸: {gen.width}x{gen.height} {'OK（グリッド一致）' if ok else '!!想定と不一致 → restoreで無言リサイズが入っている（系統ズレの有力候補）'}")
    if eye is not None:
        print(f"  検出EYE: 上から{eye*100:.1f}%")

    outs = []
    b = _draw_guides(_blend(inp, gen), prep, eye)
    pb = os.path.join(d, "debug_B_input_vs_gen.png")
    b.save(pb); outs.append(pb)
    src = Image.open(paths["visible"])
    res = Image.open(paths["restored_full"])
    c = _blend(src, res)
    pc = os.path.join(d, "debug_C_src_vs_restored.png")
    c.save(pc); outs.append(pc)
    print("  書き出し: " + " / ".join(os.path.basename(x) for x in outs))
    print("  見方: Bで生成(ゴースト)が青枠の外へ絵を描いていたら「パディング無視」、"
          "赤線と生成の地平線が合わなければ「アイレベル無視」。"
          "Bが一致してCだけズレるなら復元(C段)のバグ。")

    if a.handoff:
        os.makedirs(a.handoff, exist_ok=True)
        stem = os.path.basename(os.path.normpath(d))
        for pth in outs:
            im = Image.open(pth)
            if max(im.size) > 1400:
                s = 1400 / max(im.size)
                im = im.resize((round(im.width * s), round(im.height * s)))
            im.convert("RGB").save(os.path.join(a.handoff, f"{stem}_{os.path.basename(pth)[:-4]}.jpg"), quality=85)
        print(f"  共有用jpg: {os.path.abspath(a.handoff)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
