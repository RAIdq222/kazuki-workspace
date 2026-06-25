"""背景原図 修正パイプラインの CLI。

生成ステップだけ実行環境で認証経路が異なる（web セッションは MCP 経由、
本番環境は Higgsfield CLI/API）ため、生成を挟む 2 フェーズに分ける:

  prep   : PSD → 表示合成PNG → ヘッダー除去 → GPT出力寸ぴったりの入力 → manifest（ローカル完結）
  (生成) : padded.png（＝出力寸入力, ＋美術ボード）を GPT Image 2 に渡して結果PNGを得る
  finish : 結果PNG → 切り戻し → ヘッダー分を元座標へ復帰 → 元PSDへ「AI原図修正」差し込み → 台帳

レジストが合う理由: 入力を GPT 出力寸ぴったりで作る(入力==出力グリッド)ため、入力作成の
逆処理で戻せば幾何的にズレない（§20.6）。ヘッダー帯は撮影フレーム外の作画(余分)を切らずに落とす。

使用例:
  python -m genzu_fix.cli prep  genzu.psd --prompt-file p.txt --board board.png
  # → work/genzu/padded.png を生成・アップロードして生成、結果を result.png として取得
  python -m genzu_fix.cli finish work/genzu/manifest.json --result result.png \
         --out-psd genzu_AI.psd --job-id <id> --result-url <url> --cost 7
"""
from __future__ import annotations
import argparse
import json
import os
import time

from . import image_aspect, psd_export, ledger, frame


def _stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def cmd_prep(args) -> None:
    out_dir = args.out_dir or os.path.join("work", _stem(args.psd))
    os.makedirs(out_dir, exist_ok=True)

    visible_png = os.path.join(out_dir, "visible.png")
    body_png = os.path.join(out_dir, "body.png")
    padded_png = os.path.join(out_dir, "padded.png")

    bg = None if args.transparent else (255, 255, 255)
    vw, vh = psd_export.export_visible_to_png(
        args.psd, visible_png, bg=bg, drop_text=not args.keep_text)
    # 管理ヘッダー帯を落とす（撮影フレーム外の余分=作画は残す）。非標準シートは --header-top で明示。
    region = frame.strip_header(visible_png, body_png, top_override=args.header_top)
    # ヘッダー除去後の本体を GPT Image 2 の出力寸ぴったりへ収めて入力にする
    prep = image_aspect.build_input_image(body_png, padded_png,
                                          resolution=args.resolution)

    prompt = ""
    if args.prompt_file:
        with open(args.prompt_file, encoding="utf-8") as f:
            prompt = f.read().strip()
    elif args.prompt:
        prompt = args.prompt

    manifest = {
        "cut": _stem(args.psd),
        "psd": os.path.abspath(args.psd),
        "visible_png": os.path.abspath(visible_png),
        "body_png": os.path.abspath(body_png),
        "padded_png": os.path.abspath(padded_png),
        "canvas_size": [vw, vh],
        "region": list(region),
        "boards": [os.path.abspath(b) for b in (args.board or [])],
        "prompt": prompt,
        "aspect_ratio": prep.aspect_ratio,
        "prep": _prep_to_dict(prep),
        "created_at": time.time(),
    }
    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"visible : {visible_png}  ({vw}x{vh})")
    print(f"body    : {body_png}  (header除去 region={region})")
    print(f"padded  : {padded_png}  (aspect {prep.aspect_ratio}, "
          f"canvas {prep.canvas_w}x{prep.canvas_h} = GPT出力寸)")
    print(f"boards  : {manifest['boards'] or '(none)'}")
    print(f"manifest: {manifest_path}")
    print("\n次: padded.png（＋boards）を GPT Image 2 に渡して生成し、結果を保存してから finish を実行。")


def cmd_finish(args) -> None:
    with open(args.manifest, encoding="utf-8") as f:
        manifest = json.load(f)

    prep = _dict_to_prep(manifest["prep"])
    psd_path = args.psd or manifest["psd"]
    out_dir = os.path.dirname(args.manifest)
    restored_png = os.path.join(out_dir, "restored.png")
    full_png = os.path.join(out_dir, "restored_full.png")

    # 生成結果を本体画角へ切り戻し（入力作成の逆処理＝幾何は厳密）
    image_aspect.restore_output_image(args.result, restored_png, prep)
    # ヘッダーを落とした分を元のキャンバス座標へ戻す（region 外はヘッダー帯＝白）
    region = manifest.get("region")
    canvas = manifest.get("canvas_size")
    if region and canvas:
        frame.paste_into_region(tuple(canvas), tuple(region), restored_png, full_png)
        insert_src = full_png
    else:  # 旧 manifest 後方互換（ヘッダー除去なし）
        insert_src = restored_png

    out_psd = args.out_psd or os.path.join(
        out_dir, f"{manifest['cut']}_AI.psd")
    layer_name = psd_export.insert_result_layer(
        psd_path, insert_src, out_psd, base_name=args.base_name)

    rec = ledger.GenRecord(
        run_id=args.job_id or "",
        created_at=time.time(),
        cut=manifest["cut"],
        genzu_file=manifest["psd"],
        board_files=manifest.get("boards", []),
        params={"aspect_ratio": manifest["aspect_ratio"],
                "resolution": args.resolution, "quality": args.quality},
        prompt=manifest.get("prompt", ""),
        aspect_prep=manifest["prep"],
        result_url=args.result_url or "",
        output_file=out_psd,
        cost_credits=args.cost,
        notes=f"layer='{layer_name}' inserted; restored={restored_png}",
    )
    ledger.append(rec)

    print(f"restored: {restored_png}")
    print(f"out PSD : {out_psd}")
    print(f"layer   : {layer_name}")
    print(f"ledger  : {ledger.LEDGER_PATH} (+1 row)")


def _prep_to_dict(prep) -> dict:
    return {k: getattr(prep, k) for k in (
        "aspect_ratio", "canvas_w", "canvas_h", "paste_x", "paste_y",
        "src_w", "src_h", "scale", "scaled_w", "scaled_h", "resolution",
        "frac_left", "frac_top", "frac_right", "frac_bottom")}


def _dict_to_prep(d: dict):
    # 旧 manifest（新フィールドなし）も読めるよう、既知フィールドだけ渡す
    import dataclasses
    keys = {f.name for f in dataclasses.fields(image_aspect.PrepResult)}
    return image_aspect.PrepResult(**{k: v for k, v in d.items() if k in keys})


def cmd_layers(args) -> None:
    """フォルダ内（または指定）の PSD のレイヤー一覧を1つの CSV に書き出す。
    テキスト除外の可否（文字が別レイヤーか焼き込みか）を判断する材料にする。
    """
    import csv
    import glob as _glob

    targets = []
    for p in args.paths:
        if os.path.isdir(p):
            targets += sorted(_glob.glob(os.path.join(p, "*.psd")))
        else:
            targets.append(p)

    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["psd", "layer", "kind", "visible", "depth", "bbox"])
        for psd_path in targets:
            try:
                for li in psd_export.list_layers(psd_path):
                    w.writerow([os.path.basename(psd_path), li.name, li.kind,
                                int(li.visible), li.depth, "%d,%d,%d,%d" % li.bbox])
            except Exception as e:  # 壊れたPSD等はスキップして続行
                w.writerow([os.path.basename(psd_path), f"<ERROR: {e}>", "", "", "", ""])
    print(f"{len(targets)} PSD → {args.out}")
    print("テキストレイヤーは kind='type' の行。これを見れば文字が別レイヤーか焼き込みか分かります。")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="genzu_fix", description="背景原図 修正パイプライン")
    sub = p.add_subparsers(dest="command", required=True)

    pp = sub.add_parser("prep", help="PSD → 合成PNG → 比率パディング → manifest")
    pp.add_argument("psd")
    pp.add_argument("--out-dir", default=None)
    pp.add_argument("--prompt", default=None)
    pp.add_argument("--prompt-file", default=None)
    pp.add_argument("--board", action="append", help="美術ボード画像（複数可）")
    pp.add_argument("--transparent", action="store_true",
                    help="合成PNGの余白を透過にする（既定は白）")
    pp.add_argument("--keep-text", action="store_true",
                    help="テキストレイヤーを残す（既定は除外）")
    pp.add_argument("--resolution", default="2k",
                    help="生成解像度tier。入力をこのtierの出力寸ぴったりで作る")
    pp.add_argument("--header-top", type=int, default=None,
                    help="ヘッダー帯の下端yを明示指定（非標準シート用。既定は自動検出）")
    pp.set_defaults(func=cmd_prep)

    pf = sub.add_parser("finish", help="結果PNG → 切り戻し → PSD差し込み → 台帳")
    pf.add_argument("manifest")
    pf.add_argument("--result", required=True, help="生成結果PNG（padded比率）")
    pf.add_argument("--psd", default=None, help="差し込み先PSD（既定: manifestのpsd）")
    pf.add_argument("--out-psd", default=None)
    pf.add_argument("--base-name", default="AI原図修正")
    pf.add_argument("--job-id", default=None)
    pf.add_argument("--result-url", default=None)
    pf.add_argument("--cost", type=float, default=None)
    pf.add_argument("--resolution", default="2k")
    pf.add_argument("--quality", default="high")
    pf.set_defaults(func=cmd_finish)

    pl = sub.add_parser("layers", help="PSD群のレイヤー一覧をCSVに書き出す（テキスト除外の判断材料）")
    pl.add_argument("paths", nargs="+", help="PSDファイル or フォルダ")
    pl.add_argument("--out", default="layers.csv")
    pl.set_defaults(func=cmd_layers)
    return p


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
