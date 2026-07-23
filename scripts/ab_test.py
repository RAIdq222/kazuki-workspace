"""生成条件のA/B比較ハーネス — 品質向上の打ち手をデータで選ぶ。

同じカットを条件別×N回生成し、検品レポート(trust)・比較シートで並べる。
単発の試行錯誤ではどの部品（staging/ボード/消失点注入）が効いているか分からないため、
条件を1つずつ抜いた比較で寄与を測る。歩留まり（同条件での分散）も同時に取れる。

条件（--conditions のカンマ区切り）:
  full      … 現行フル装備（staging＋ボード意匠辞書＋EYE＋[PERSPECTIVE]）
  nopersp   … [PERSPECTIVE]なし（消失点注入の効果測定）
  noboard   … ボード参照なし（構図汚染 vs 画風の綱引き測定）
  nostaging … 画角記述なし（言語チャンネルの寄与測定）

使い方（ローカル・要 higgsfield auth login と ANTHROPIC_API_KEY）:
  set PYTHONPATH=src
  python scripts/ab_test.py --psd "C:\\...\\00.原図\\GKV\\優先順位高\\SP2_10_290.psd" ^
      --cut 290 --out work\\ab_c290 --conditions full,nopersp --runs 2 ^
      --board "C:\\...\\00_資料_#10\\03【現実世界】...\\00_ボード\\SP2_現実世界_隔離空間_夜.psd" ^
      --handoff handoff\\SP2_10\\ab_c290
  → <out>\\summary.csv ＋ contact_sheet.jpg（原図と全結果を1枚に・trust入りラベル）

生成コスト注意: 条件数×runs 回のHiggsfield生成が走る（既定 full,nopersp × 1回 = 2生成）。
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import sys
import tempfile

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from genzu_fix import batch, psd_export
from genzu_fix import prompt as promptlib


def _board_png(path: str) -> str | None:
    """ボードがPSDならPNG化して返す（PILはPSDを読めないため）。png/jpgはそのまま。"""
    if not path:
        return None
    if path.lower().endswith((".psd", ".psb")):
        out = os.path.join(tempfile.gettempdir(), "_ab_board.png")
        psd_export.export_visible_to_png(path, out, bg=(255, 255, 255))
        return out
    return path


def _staging_for(cut: str, csv_path: str) -> str:
    if not (csv_path and os.path.exists(csv_path)):
        return ""
    text = ""
    with open(csv_path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if (r.get("cut") or "").strip() == str(int(cut)):
                text = (r.get("staging") or "").strip()  # 重複行は後勝ち（loaderと同じ）
    return text


def _contact_sheet(tiles: list[tuple[str, str]], out_path: str, tile_w: int = 640):
    """(ラベル, 画像path) を横グリッドに並べた比較シートを作る。"""
    from PIL import Image, ImageDraw
    ims = []
    for label, p in tiles:
        im = Image.open(p).convert("RGB")
        s = tile_w / im.width
        ims.append((label, im.resize((tile_w, round(im.height * s)))))
    th = max(im.height for _, im in ims) + 34
    sheet = Image.new("RGB", (tile_w * len(ims) + 8 * (len(ims) + 1), th + 8), (30, 30, 34))
    d = ImageDraw.Draw(sheet)
    x = 8
    for label, im in ims:
        sheet.paste(im, (x, 38))
        d.text((x + 4, 10), label, fill=(255, 255, 255))
        x += tile_w + 8
    sheet.save(out_path)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ab_test", description="生成条件のA/B比較")
    p.add_argument("--psd", required=True)
    p.add_argument("--cut", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--conditions", default="full,nopersp")
    p.add_argument("--runs", type=int, default=1, help="条件ごとの生成回数（分散測定は2以上）")
    p.add_argument("--board", default="", help="ボード画像（psd/png/jpg）。省略時はボード無し")
    p.add_argument("--staging-csv", default="runs/staging_sp2_10.csv")
    p.add_argument("--staging", default="", help="画角記述を直接指定（CSVより優先）")
    p.add_argument("--cut-info", default="runs/cut_scene_info_sp2_10.csv")
    p.add_argument("--handoff", default="", help="git共有用の縮小シートも書き出す")
    a = p.parse_args(argv)

    conds = [c.strip() for c in a.conditions.split(",") if c.strip()]
    staging = a.staging or _staging_for(a.cut, a.staging_csv)
    board_png = _board_png(a.board)
    cim = promptlib.load_cut_info(a.cut_info)
    print(f"条件: {conds} × {a.runs}回 = 生成{len(conds) * a.runs}回"
          f"（staging={'あり' if staging else '無し'} / board={'あり' if board_png else '無し'}）")

    rows = []
    tiles: list[tuple[str, str]] = []
    for cond in conds:
        for r in range(1, a.runs + 1):
            od = os.path.join(a.out, f"{cond}_r{r}")
            print(f"== {cond} run{r} → {od}")
            try:
                batch.process_cut(
                    a.psd, board="", scene="", out_dir=od, prompt_override=None,
                    resolution="2k", quality="high", model="gpt_image_2",
                    image_flag="--image", dry=False, include_book=True,
                    board_path=(None if cond == "noboard" else board_png),
                    staging=(None if cond == "nostaging" else (staging or None)),
                    genzu_trust="high", inject_persp=(cond != "nopersp"),
                    cut_num=str(a.cut), cut_info_map=cim, qc_vision=True)
            except Exception as e:  # noqa 1条件の失敗で全体を止めない
                print(f"  [warn] {cond} run{r} 失敗: {str(e)[:150]}")
                rows.append({"cond": cond, "run": r, "trust": "", "verdict": "error",
                             "errors": str(e)[:120]})
                continue
            q = {}
            qp = os.path.join(od, "qc.json")
            if os.path.exists(qp):
                q = json.load(open(qp, encoding="utf-8"))
            rows.append({"cond": cond, "run": r, "trust": q.get("trust", ""),
                         "verdict": q.get("verdict", ""),
                         "errors": " / ".join(q.get("reasons", []))[:200]})
            rp = os.path.join(od, "restored_full.png")
            if os.path.exists(rp):
                tiles.append((f"{cond} r{r}  trust={q.get('trust', '—')}", rp))
            if not any(t[0] == "原図" for t in tiles):
                vp = os.path.join(od, "visible.png")
                if os.path.exists(vp):
                    tiles.insert(0, ("原図", vp))

    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "summary.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["cond", "run", "trust", "verdict", "errors"])
        w.writeheader()
        w.writerows(rows)
    print("\n== summary ==")
    for r in rows:
        print(f"  {r['cond']:>10} r{r['run']}  trust={r['trust'] or '—':>3}  {r['verdict']}  {r['errors'][:60]}")
    if tiles:
        sheet = os.path.join(a.out, "contact_sheet.jpg")
        _contact_sheet(tiles, sheet)
        print(f"比較シート: {sheet}")
        if a.handoff:
            os.makedirs(a.handoff, exist_ok=True)
            from PIL import Image
            im = Image.open(sheet)
            if im.width > 2600:
                s = 2600 / im.width
                im = im.resize((2600, round(im.height * s)))
            hp = os.path.join(a.handoff, f"ab_c{a.cut}_sheet.jpg")
            im.save(hp, quality=85)
            print(f"共有用: {hp}（summary.csvと一緒にpush推奨）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
