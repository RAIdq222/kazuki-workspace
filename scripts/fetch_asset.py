"""ローカル資産（PSD/PDF/画像）を「読める形」に変換して repo に取り込む汎用CLI。

なぜ要るか:
  リモートのセッションは使い捨てコンテナで、黒江さんPCのローカル（C:\\…\\06. 色見本 等）も
  Drive(10MB超)も直接読めない。ローカルにファイルがある側で本CLIを走らせ、PNG/テキストへ変換して
  git に乗せれば、リモート側は Read でそれを読める。read-genzu（原図PSD→PNG）の対象を全資産へ一般化したもの。

使い方:
  # 1ファイル or フォルダを指定。出力は handoff/ep7/assets/ 配下（git対象）。
  python scripts/fetch_asset.py "..\\06. 色見本"                      # フォルダ直下を変換
  python scripts/fetch_asset.py "..\\06. 色見本\\キャラ表.psd"         # 単一ファイル
  python scripts/fetch_asset.py "..\\03.設定資料" --recursive          # 再帰
  → 変換結果のパスを表示。git add -f handoff/ep7/assets && commit && push すれば受け手が読める。

変換ルール:
  .psd            → 見たまま全レイヤー合成PNG（psd_export.export_visible_to_png）
  .pdf            → ページPNG群（PyMuPDF。要 pip install pymupdf）
  .png/.jpg/.jpeg → そのままコピー
  その他(.xlsx等) → スキップ（CLIで読めないものは別途）。

PYTHONPATH 不要（src/ を自動で通す）。
"""
from __future__ import annotations
import argparse
import os
import shutil
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

IMG_EXT = (".png", ".jpg", ".jpeg")


def _convert_one(path: str, out_dir: str) -> list[str]:
    base = os.path.splitext(os.path.basename(path))[0]
    ext = os.path.splitext(path)[1].lower()
    os.makedirs(out_dir, exist_ok=True)
    made: list[str] = []
    if ext == ".psd":
        from genzu_fix import psd_export
        out = os.path.join(out_dir, base + ".png")
        w, h = psd_export.export_visible_to_png(path, out, drop_text=False)
        print(f"  PSD→PNG: {out}  {w}x{h}")
        made.append(out)
    elif ext == ".pdf":
        from genzu_fix import conte
        sub = os.path.join(out_dir, base)
        pages = conte.render(path, sub, dpi=200)
        made.extend(pages)
    elif ext in IMG_EXT:
        out = os.path.join(out_dir, os.path.basename(path))
        shutil.copy2(path, out)
        print(f"  画像コピー: {out}")
        made.append(out)
    else:
        print(f"  スキップ（CLIで変換不可）: {path}")
    return made


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="fetch_asset",
                                description="ローカル資産(PSD/PDF/画像)→読めるPNGに変換してrepoへ")
    p.add_argument("src", help="ファイル or フォルダのローカルパス")
    p.add_argument("--out", default=os.path.join("handoff", "ep7", "assets"),
                   help="出力先（既定 handoff/ep7/assets。git対象に置くこと）")
    p.add_argument("--recursive", action="store_true", help="フォルダを再帰的に処理")
    a = p.parse_args(argv)

    if not os.path.exists(a.src):
        print(f"見つかりません: {a.src}")
        return 1

    targets: list[str] = []
    if os.path.isfile(a.src):
        targets = [a.src]
    else:
        for root, _, files in os.walk(a.src):
            for f in files:
                targets.append(os.path.join(root, f))
            if not a.recursive:
                break

    made: list[str] = []
    for t in sorted(targets):
        print(f"- {t}")
        made.extend(_convert_one(t, a.out))

    print(f"\n変換 {len(made)} 件 → {a.out}")
    if made:
        print("次: git add -f " + a.out + " && git commit -m \"data: ローカル資産取り込み\" && git push")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
