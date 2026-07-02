"""LoRA Preflight 整形の実画像確認用CLI（アプリ起動不要）。

使い方:
  python scripts/preflight_plan.py <画像...> [--mode normal|fullbody] [--x 0.5] [--neck 0.14] [--out work/_preflight]

出力: <out>/<画像名>/ に plan.json・出力PNG（通常1枚 / 全身4枚）・サムネ。
画面サムネと同じ apply_plan() を通るので、アプリの出力と1:1で一致する。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "lora_preflight_app"))

from PIL import Image  # noqa: E402

import preflight_core as pfc  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", help="入力画像")
    parser.add_argument("--mode", choices=["normal", "fullbody"], default="normal")
    parser.add_argument("--x", type=float, default=0.5, help="余白⇔切り取りバランス (0=余白優先)")
    parser.add_argument("--neck", type=float, default=0.14, help="首位置（人物高に対する割合）")
    parser.add_argument("--out", default=str(REPO / "work" / "_preflight"))
    args = parser.parse_args()

    cfg = pfc.PreflightConfig(pad_crop_x=args.x, neck_ratio=args.neck)
    for image_path in args.images:
        source = Path(image_path)
        out_dir = Path(args.out) / source.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as img:
            img = img.convert("RGB")
            info = pfc.analyze(img, cfg.trim_threshold)
            plans = pfc.plan_for_mode(info, cfg, args.mode)
            for index, plan in enumerate(plans, start=1):
                suffix = f"_{index}" if len(plans) > 1 else ""
                pfc.apply_plan(img, plan).save(out_dir / f"{source.stem}{suffix}.png", "PNG")
                pfc.thumbnail(img, plan).save(out_dir / f"{source.stem}{suffix}_thumb.jpg", "JPEG", quality=88)
                if plan.fallback:
                    print(f"  [自動調整] {source.name}{suffix}: {plan.fallback}")
        (out_dir / "plan.json").write_text(
            json.dumps(
                {"source": str(source), "mode": args.mode, "contentBox": info.content_box,
                 "plans": [p.to_dict() for p in plans]},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        print(f"{source.name}: {len(plans)}枚 -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
