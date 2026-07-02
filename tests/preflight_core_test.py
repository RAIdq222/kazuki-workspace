"""LoRA Preflight 画像整形コア(preflight_core)の不変条件テスト。

合成画像（白背景＋濃色の矩形=人物ダミー）だけで検証する。実画像・モデル不要。
実行: python tests/preflight_core_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lora_preflight_app"))

from PIL import Image

import preflight_core as pfc


FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok: {name}")
    else:
        FAILURES.append(name)
        print(f"  NG: {name} {detail}")


def synth(width: int, height: int, box: tuple, color=(40, 40, 40)) -> Image.Image:
    img = Image.new("RGB", (width, height), (255, 255, 255))
    img.paste(Image.new("RGB", (box[2] - box[0], box[3] - box[1]), color), (box[0], box[1]))
    return img


def test_exact_output_size():
    print("[サイズ正確性] どの入力でも出力寸法が規定サイズに一致する")
    cfg = pfc.PreflightConfig()
    for w, h, box in [(1200, 1000, (300, 200, 900, 800)), (500, 1500, (100, 50, 400, 1450)), (997, 613, (10, 10, 900, 600))]:
        img = synth(w, h, box)
        info = pfc.analyze(img)
        plan = pfc.plan_normal(info, cfg)
        out = pfc.apply_plan(img, plan)
        check(f"{w}x{h} -> {plan.scale_to}", (out.width, out.height) == tuple(plan.scale_to))
        check(f"{w}x{h} 規定サイズ内", tuple(plan.scale_to) in pfc.candidate_sizes(cfg))


def test_wysiwyg():
    print("[WYSIWYG] サムネ = apply_plan結果の縮小（同一経路）")
    img = synth(1200, 900, (200, 100, 1000, 800))
    cfg = pfc.PreflightConfig()
    plan = pfc.plan_normal(pfc.analyze(img), cfg)
    thumb = pfc.thumbnail(img, plan, 320)
    ref = pfc.apply_plan(img, plan)
    ref.thumbnail((320, 320), Image.Resampling.LANCZOS)
    check("ピクセル一致", thumb.tobytes() == ref.tobytes())


def test_slider():
    print("[xスライダー] 0=余白優先 / 1=切り取り優先 で単調に切り替わる")
    img = synth(1200, 1000, (100, 100, 1100, 900))  # r=1.2, 最近比率 1152x896=1.286
    info = pfc.analyze(img)
    modes = []
    for x in (0.0, 0.25, 0.5, 0.75, 1.0):
        plan = pfc.plan_normal(info, pfc.PreflightConfig(pad_crop_x=x))
        modes.append("pad" if plan.params["usePad"] else "crop")
    check("x=0 は余白", modes[0] == "pad", str(modes))
    check("x=1 は切り取り", modes[-1] == "crop", str(modes))
    check("単調（pad→cropへ一度だけ切替）", "".join(m[0] for m in modes).rstrip("c").lstrip("p") == "", str(modes))


def test_overcrop_fallback():
    print("[削りすぎ] 切除率が閾値超なら余白側へ倒し fallback が記録される")
    img = synth(600, 1200, (50, 20, 550, 1180))  # r=0.5, 最近比率 768x1344 で切除率0.125
    info = pfc.analyze(img)
    tight = pfc.plan_normal(info, pfc.PreflightConfig(pad_crop_x=1.0, max_crop_frac=0.05))
    loose = pfc.plan_normal(info, pfc.PreflightConfig(pad_crop_x=1.0, max_crop_frac=0.5))
    check("閾値超で fallback あり", tight.fallback is not None, str(tight.fallback))
    check("閾値超では余白側へ倒れる", tight.params["usePad"] is True)
    check("画像全体を残す（クロップなし）", tight.crop_box == (0, 0, 600, 1200), str(tight.crop_box))
    check("閾値内なら fallback なし", loose.fallback is None, str(loose.fallback))
    check("閾値内なら切り取りのまま", loose.params["usePad"] is False)


def test_landscape_cuts_top_first():
    print("[横長の縦詰め] 上の余白から削り、下端の内容を守る")
    img = synth(1600, 1000, (100, 400, 1500, 980))  # 内容は下寄り, r=1.6 < 最近比率1.75
    info = pfc.analyze(img)
    plan = pfc.plan_normal(info, pfc.PreflightConfig(pad_crop_x=1.0))
    if plan.params["usePad"]:
        check("crop計画が選ばれる前提", False, "usePad=True")
        return
    _, top, _, bottom = plan.crop_box
    check("上から削られている", top > 0, f"crop_box={plan.crop_box}")
    check("下端は保持", bottom == 1000, f"crop_box={plan.crop_box}")
    check("内容の下端を含む", bottom >= info.content_box[3], f"content={info.content_box}")


def test_fullbody_four_tiles():
    print("[全身絵] 4枚生成・頭足が切れない・首下に頭頂が入らない・命名順")
    img = synth(1000, 2200, (350, 50, 650, 2150))
    info = pfc.analyze(img)
    cfg = pfc.PreflightConfig()
    plans = pfc.plan_fullbody(info, cfg)
    check("4枚", len(plans) == 4, str(len(plans)))
    check("種別順", [p.kind for p in plans] == list(pfc.FULLBODY_KINDS), str([p.kind for p in plans]))
    upper, body, feet, full = plans
    y0, y1 = info.content_box[1], info.content_box[3]
    check("上半身に頭頂を含む", upper.crop_box[1] <= y0, f"{upper.crop_box} y0={y0}")
    check("足元に足先を含む", feet.crop_box[3] >= y1, f"{feet.crop_box} y1={y1}")
    check("首から下に頭頂が入らない", body.crop_box[1] > y0, f"{body.crop_box} y0={y0}")
    for p in (upper, body, feet):
        out = pfc.apply_plan(img, p)
        check(f"{p.kind} は {cfg.fullbody_tile}px 正方形", out.size == (cfg.fullbody_tile, cfg.fullbody_tile), str(out.size))
    check("全身は縦向き規定サイズ", full.scale_to[1] >= full.scale_to[0] and tuple(full.scale_to) in pfc.candidate_sizes(cfg), str(full.scale_to))
    check("全身は縦を全て残す", full.crop_box[1] == 0 and full.crop_box[3] == 2200, str(full.crop_box))
    out = pfc.apply_plan(img, full)
    check("全身の出力寸法", out.size == tuple(full.scale_to), str(out.size))


def test_fullbody_narrow_pads_not_crops():
    print("[全身絵・幅不足] 高さ正規化後に幅が足りない場合は余白で補い人物を切らない")
    img = synth(800, 2200, (250, 100, 550, 2100))
    info = pfc.analyze(img)
    plans = pfc.plan_fullbody(info, pfc.PreflightConfig())
    for p in plans[:3]:
        check(f"{p.kind} は水平クロップなし", p.crop_box[0] == 0 and p.crop_box[2] == 800, str(p.crop_box))
        check(f"{p.kind} は左右に余白", p.pad[0] > 0 and p.pad[2] > 0, str(p.pad))
        out = pfc.apply_plan(img, p)
        check(f"{p.kind} 出力は正方形", out.size == (1024, 1024), str(out.size))


def test_fullbody_wide_keeps_person():
    print("[全身絵・幅超過] 幅を1024相当へ削っても人物は窓内に残る")
    img = synth(2400, 2200, (1000, 60, 1400, 2140))
    info = pfc.analyze(img)
    plans = pfc.plan_fullbody(info, pfc.PreflightConfig())
    x0, x1 = info.content_box[0], info.content_box[2]
    for p in plans[:3]:
        check(
            f"{p.kind} 窓が人物を含む",
            p.crop_box[0] <= x0 and p.crop_box[2] >= x1,
            f"crop={p.crop_box} content_x=({x0},{x1})",
        )


def test_neck_ratio_adjustable():
    print("[首位置] neck_ratio の変更が首から下の開始位置に反映される")
    img = synth(1000, 2200, (350, 50, 650, 2150))
    info = pfc.analyze(img)
    lo = pfc.plan_fullbody(info, pfc.PreflightConfig(), neck_ratio=0.10)[1]
    hi = pfc.plan_fullbody(info, pfc.PreflightConfig(), neck_ratio=0.25)[1]
    check("比率が大きいほど開始が下がる", hi.crop_box[1] > lo.crop_box[1], f"{lo.crop_box[1]} vs {hi.crop_box[1]}")


def main() -> int:
    for test in [
        test_exact_output_size,
        test_wysiwyg,
        test_slider,
        test_overcrop_fallback,
        test_landscape_cuts_top_first,
        test_fullbody_four_tiles,
        test_fullbody_narrow_pads_not_crops,
        test_fullbody_wide_keeps_person,
        test_neck_ratio_adjustable,
    ]:
        test()
    if FAILURES:
        print(f"\nFAILED: {len(FAILURES)}件 -> {FAILURES}")
        return 1
    print("\nALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
