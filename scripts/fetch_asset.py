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

COPY_EXT = (".png", ".jpg", ".jpeg")
RASTER_EXT = (".tif", ".tiff", ".bmp", ".webp", ".gif")  # PILでPNG化
PSD_EXT = (".psd", ".psb")


def _pdf_ingest(path: str, out_dir: str, base: str, min_text: int = 80) -> list[str]:
    """PDFはまずテキスト抽出（打ち込み＝シナリオ等）。テキストが乏しいスキャンPDFは画像化。"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("PyMuPDF が必要です: pip install pymupdf")
    doc = fitz.open(path)
    texts = [(i + 1, doc.load_page(i).get_text("text")) for i in range(doc.page_count)]
    total = sum(len(t) for _, t in texts)
    os.makedirs(out_dir, exist_ok=True)
    if total >= min_text:  # 打ち込みPDF → テキスト
        out = os.path.join(out_dir, base + ".txt")
        with open(out, "w", encoding="utf-8") as f:
            for n, t in texts:
                f.write(f"\n===== page {n} =====\n{t}")
        print(f"  PDF→テキスト: {out}  ({doc.page_count}ページ, {total}文字)")
        return [out]
    # スキャンPDF（文字なし）→ ページ画像
    from genzu_fix import conte
    print(f"  PDF→画像（テキスト乏しい＝スキャン, {doc.page_count}ページ）")
    return conte.render(path, os.path.join(out_dir, base), dpi=200)


def _convert_one(path: str, out_dir: str) -> list[str]:
    base = os.path.splitext(os.path.basename(path))[0]
    ext = os.path.splitext(path)[1].lower()
    os.makedirs(out_dir, exist_ok=True)
    made: list[str] = []
    try:
        if ext in PSD_EXT:
            from genzu_fix import psd_export
            out = os.path.join(out_dir, base + ".png")
            w, h = psd_export.export_visible_to_png(path, out, drop_text=False)
            print(f"  PSD→PNG: {out}  {w}x{h}")
            made.append(out)
        elif ext == ".pdf":
            made.extend(_pdf_ingest(path, out_dir, base))
        elif ext in COPY_EXT:
            out = os.path.join(out_dir, os.path.basename(path))
            shutil.copy2(path, out)
            print(f"  画像コピー: {out}")
            made.append(out)
        elif ext in RASTER_EXT:
            from PIL import Image
            out = os.path.join(out_dir, base + ".png")
            Image.open(path).convert("RGB").save(out)
            print(f"  画像→PNG: {out}")
            made.append(out)
        else:
            print(f"  スキップ（未対応形式 {ext or '?'}）: {path}")
    except Exception as e:
        print(f"  変換失敗 {path}: {e}")
    return made


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="fetch_asset",
                                description="ローカル資産(PSD/PDF/画像)→読めるPNGに変換してrepoへ")
    p.add_argument("src", help="ファイル or フォルダのローカルパス")
    p.add_argument("--out", default=os.path.join("handoff", "ep7", "assets"),
                   help="出力先（既定 handoff/ep7/assets。git対象に置くこと）")
    p.add_argument("--recursive", action="store_true", help="フォルダを再帰的に処理")
    p.add_argument("--list", action="store_true", dest="list_only",
                   help="変換せず中身(ファイル/サブフォルダ)を一覧表示するだけ")
    a = p.parse_args(argv)

    if not os.path.exists(a.src):
        print(f"見つかりません: {a.src}")
        return 1

    targets: list[str] = []
    subdirs: list[str] = []
    if os.path.isfile(a.src):
        targets = [a.src]
    else:
        for root, dirs, files in os.walk(a.src):
            for f in files:
                targets.append(os.path.join(root, f))
            if not a.recursive:
                subdirs = [os.path.join(root, d) for d in dirs]
                break

    # 中身が見えるよう、見つけたファイルを常に列挙（拡張子別）
    if not targets:
        print(f"直下にファイルなし: {a.src}")
        if subdirs:
            print("サブフォルダがあります（--recursive で潜れます）:")
            for d in subdirs:
                print(f"  [dir] {d}")
        return 1
    if a.list_only:
        print(f"{a.src} の中身（{len(targets)}件）:")
        for t in sorted(targets):
            print(f"  {os.path.splitext(t)[1].lower() or '(無)':6} {t}")
        return 0

    made: list[str] = []
    for t in sorted(targets):
        print(f"- {t}")
        made.extend(_convert_one(t, a.out))

    print(f"\n変換 {len(made)} 件 → {a.out}")
    if made:
        print(f"次: git add -f {a.out} && git commit -m \"data: ローカル資産取り込み\" && "
              "git push origin HEAD:claude/great-edison-bk5g8c")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
