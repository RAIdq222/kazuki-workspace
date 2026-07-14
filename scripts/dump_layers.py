"""原図PSD群のレイヤー構成を一括ダンプ（新作品のレイヤー規則を決めるための調査用）。

やること:
  1. --genzu-dir 配下の全PSDのレイヤーツリー（名前/種別/可視/階層）をテキストに書き出し
  2. レイヤー名の頻度サマリ（どの命名規則がどれだけあるか一目で分かる）
  3. 現行の自動抽出（export_background_layer=Base）が各PSDで何を選ぶかを記録
  4. --samples N で先頭NカットのBase/visibleプレビューPNG（縮小版）も書き出し
     → git に push すれば、PSDが無いセッションでも抽出結果の絵を確認できる

使い方（SP2 #10）:
  python scripts/dump_layers.py --genzu-dir "C:\\...\\00.原図" ^
      --out runs/sp2_10_layers.txt --samples 6 --samples-out handoff/SP2_10/genzu_sample
  git add runs/sp2_10_layers.txt handoff/SP2_10 && git commit -m "data: SP2#10 レイヤー調査" && git push

PYTHONPATH 不要。
"""
from __future__ import annotations
import argparse
import os
import sys
from collections import Counter

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from genzu_fix import psd_export


def _downscale_save(src_png: str, maxside: int = 1200):
    from PIL import Image
    im = Image.open(src_png)
    if max(im.size) > maxside:
        s = maxside / max(im.size)
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    im.convert("RGB").save(src_png[:-4] + ".jpg", quality=85)
    os.remove(src_png)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="dump_layers", description="PSDレイヤー構成の一括ダンプ")
    p.add_argument("--genzu-dir", required=True)
    p.add_argument("--out", default="runs/layers_dump.txt")
    p.add_argument("--samples", type=int, default=0, help="先頭Nカットの抽出プレビューも書き出す")
    p.add_argument("--samples-out", default="handoff/genzu_sample")
    a = p.parse_args(argv)

    psds = []
    for root, _, files in os.walk(a.genzu_dir):
        for fn in sorted(files):
            if fn.lower().endswith(".psd"):
                psds.append(os.path.join(root, fn))
    psds.sort(key=lambda x: os.path.basename(x))
    if not psds:
        print(f"[!] PSDが見つかりません: {a.genzu_dir}")
        return 1

    name_freq = Counter()
    top_freq = Counter()
    strategies = Counter()
    lines = []
    for i, path in enumerate(psds, 1):
        rel = os.path.relpath(path, a.genzu_dir)
        lines.append(f"\n=== [{i}/{len(psds)}] {rel} ===")
        try:
            infos = psd_export.list_layers(path)
        except Exception as e:  # noqa
            lines.append(f"  !! 読み取り失敗: {str(e)[:150]}")
            continue
        for li in infos:
            mark = "*" if li.visible else "."
            lines.append(f"  {'  ' * li.depth}{mark} {li.name} [{li.kind}]")
            name_freq[li.name] += 1
            if li.depth == 0:
                top_freq[li.name] += 1
        # 現行Base抽出が何を選ぶか（画像は書かずレイヤー選択だけ確認）
        try:
            import tempfile
            tmp = os.path.join(tempfile.gettempdir(), "_probe.png")
            w, h, sel = psd_export.export_background_layer(path, tmp)
            strategies[sel["strategy"]] += 1
            lines.append(f"  -> Base抽出: strategy={sel['strategy']} layers={sel['layers']} ({w}x{h})")
        except Exception as e:  # noqa
            lines.append(f"  -> Base抽出失敗: {str(e)[:120]}")

    head = [f"# レイヤー構成ダンプ: {os.path.abspath(a.genzu_dir)}  PSD {len(psds)}本",
            "\n## Base抽出 strategy 内訳（BG/LO/背景/fallback の比率＝規則が合っているかの目安）"]
    head += [f"  {k}: {v}" for k, v in strategies.most_common()]
    head.append("\n## トップレベルのレイヤー名 頻度（上位40）")
    head += [f"  {v:>4}x  {k}" for k, v in top_freq.most_common(40)]
    head.append("\n## 全レイヤー名 頻度（上位60）")
    head += [f"  {v:>4}x  {k}" for k, v in name_freq.most_common(60)]

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(head) + "\n" + "\n".join(lines) + "\n")
    print(f"書き出し: {os.path.abspath(a.out)}  (PSD {len(psds)}本)")
    print("strategy内訳:", dict(strategies))

    if a.samples > 0:
        os.makedirs(a.samples_out, exist_ok=True)
        for path in psds[: a.samples]:
            stem = os.path.splitext(os.path.basename(path))[0]
            for kind in ("base", "visible"):
                outp = os.path.join(a.samples_out, f"{stem}_{kind}.png")
                try:
                    if kind == "base":
                        psd_export.export_background_layer(path, outp)
                    else:
                        psd_export.export_visible_to_png(path, outp, drop_text=False)
                    _downscale_save(outp)
                except Exception as e:  # noqa
                    print(f"  [warn] {stem} {kind}: {str(e)[:100]}")
        print(f"サンプル書き出し: {os.path.abspath(a.samples_out)}（縮小jpg・git push 可）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
