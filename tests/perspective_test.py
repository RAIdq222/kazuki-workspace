"""perspective モジュールの検証（API鍵不要：CV/幾何/描画/JSONのみ）。

合成画像に「既知の消失点へ収束する奥行き線＋鉛直線」を描き、
  - CV が消失点を真値の近くに当てられるか
  - 幾何ヘルパ（交点・最小二乗消失点）の正しさ
  - render が画像を生成できるか
  - JSON 往復で結果が保たれるか
を確認する。vision/hybrid は ANTHROPIC_API_KEY が無ければ SKIP。

実行: PYTHONPATH=src python tests/perspective_test.py
"""
from __future__ import annotations
import os
import sys
import math
import tempfile

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from PIL import Image, ImageDraw
from genzu_fix import perspective as P

W, H = 1200, 800
VP_TRUE = (600, 360)   # 既知の消失点（画面中央やや上）


def _make_synthetic(path: str) -> None:
    """白地に、VP_TRUE へ収束する奥行き線と、複数の鉛直線を描く。"""
    im = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(im)
    vx, vy = VP_TRUE
    # 奥行き線: VP から放射状に画面外へ（地面/壁/天井のパースを模す）
    for ang in (200, 215, 230, 250, 290, 310, 325, 340):
        far = (vx + math.cos(math.radians(ang)) * 1600,
               vy + math.sin(math.radians(ang)) * 1600)
        d.line([(vx, vy), far], fill=(0, 0, 0), width=2)
    # 鉛直線（キャラの立ち軸を模す）
    for x in (300, 600, 950):
        d.line([(x, 200), (x, 760)], fill=(0, 0, 0), width=3)
    im.save(path)


def check(name, cond):
    print(f"  [{'OK' if cond else 'NG'}] {name}")
    if not cond:
        check.failed += 1
check.failed = 0


def test_geometry():
    print("test_geometry")
    # 交点: y=x（45度） と y=-x+200 → (100,100)? 直線係数で確認
    l1 = (1.0, -1.0, 0.0)        # x - y = 0
    l2 = (1.0, 1.0, -200.0)      # x + y = 200
    p = P.intersect(l1, l2)
    check("intersect (100,100)", p is not None and abs(p[0]-100) < 1e-6 and abs(p[1]-100) < 1e-6)
    # 平行線は None
    check("parallel -> None", P.intersect((1.0, 0.0, 0.0), (1.0, 0.0, -5.0)) is None)
    # 最小二乗消失点: VP_TRUE を通る直線群 → VP_TRUE を復元
    lines = []
    vx, vy = VP_TRUE
    for ang in (10, 40, 80, 120, 160):
        a, b = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        c = -(a * vx + b * vy)
        lines.append((a, b, c))
    p = P.least_squares_vp(lines)
    check("least_squares_vp recovers VP",
          p is not None and math.hypot(p[0]-vx, p[1]-vy) < 1.0)
    # 点と直線の距離: x=0 の線から (5,0) は距離 5
    check("point_line_distance", abs(P.point_line_distance((5, 0), (1.0, 0.0, 0.0)) - 5) < 1e-6)


def test_cv(img):
    print("test_cv")
    res = P.detect_cv(img)
    check("method=cv", res.method == "cv")
    check("size", res.width == W and res.height == H)
    check("VP detected", len(res.vanishing_points) >= 1)
    if res.vanishing_points:
        vp = res.vanishing_points[0]
        px, py = vp.x * W, vp.y * H
        err = math.hypot(px - VP_TRUE[0], py - VP_TRUE[1])
        print(f"    VP誤差 = {err:.1f}px (true={VP_TRUE}, got=({px:.0f},{py:.0f}))")
        check("VP within 60px of truth", err < 60)
    check("eye_level set", res.eye_level is not None)
    check("vertical lines found", len(res.characters) >= 1)
    return res


def test_render(res, img):
    print("test_render")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "ov.png")
        P.render(res, img, out, title="CV")
        check("overlay exists", os.path.exists(out) and os.path.getsize(out) > 0)
        ov = Image.open(out)
        check("overlay same size", ov.size == (W, H))
        # 比較画像（同じ結果を2枚並べるだけでも経路を通す）
        cmp_out = os.path.join(td, "cmp.png")
        P.render_comparison([("cv", res), ("cv", res)], img, cmp_out, tmp_dir=td)
        check("compare exists", os.path.exists(cmp_out))


def test_json_roundtrip(res):
    print("test_json_roundtrip")
    obj = res.to_json()
    back = P.PerspectiveResult.from_json(obj)
    check("roundtrip method", back.method == res.method)
    check("roundtrip VP count", len(back.vanishing_points) == len(res.vanishing_points))
    check("roundtrip eye", (back.eye_level is None) == (res.eye_level is None))
    if res.vanishing_points:
        check("roundtrip VP coord",
              abs(back.vanishing_points[0].x - res.vanishing_points[0].x) < 1e-9)


def test_clip():
    print("test_clip")
    # 画面内→そのまま、完全に外→None
    seg = P._clip_line_to_box((-100, 400), (1300, 400), W, H)
    check("clip horizontal -> spans width",
          seg is not None and abs(seg[0][0]) < 1 and abs(seg[1][0]-W) < 1)
    check("clip outside -> None", P._clip_line_to_box((-50, -50), (-10, -10), W, H) is None)


def test_vision_parse(img):
    """Vision 応答の JSON 抽出と PerspectiveResult 化（ネット不要）。"""
    print("test_vision_parse")
    text = (
        "解析しました。\n```json\n"
        '{"eye_level": {"a": [0.0, 0.45], "b": [1.0, 0.47]},'
        ' "vanishing_points": [{"x": 1.3, "y": 0.46, "label": "VP1", "axis": "horizontal"}],'
        ' "characters": [{"name": "ピーちゃん", "head": [0.3, 0.2], "foot": [0.31, 0.9]}],'
        ' "notes": "右奥に収束"}\n```\n以上です。'
    )
    obj = P._parse_json_object(text)
    check("parse eye_level", obj.get("eye_level") is not None)
    res = P._result_from_vision_obj(obj, img, "vision")
    check("parsed VP off-frame x>1", len(res.vanishing_points) == 1 and res.vanishing_points[0].x > 1.0)
    check("parsed character name", res.characters and res.characters[0].name == "ピーちゃん")
    check("parsed eye tilt", res.eye_level is not None and res.eye_level.b[1] != res.eye_level.a[1])
    # 壊れた応答でも落ちない
    check("broken json -> {}", P._parse_json_object("ごめんJSON出せません") == {})


def test_vision_skip(img):
    print("test_vision (API)")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("  [SKIP] ANTHROPIC_API_KEY 未設定（vision/hybrid はスキップ）")
        return
    try:
        res = P.detect_vision(img)
        check("vision returns result", res.method == "vision")
    except Exception as e:
        print(f"  [WARN] vision 呼び出し失敗: {e}")


def main():
    with tempfile.TemporaryDirectory() as td:
        img = os.path.join(td, "synth.png")
        _make_synthetic(img)
        test_geometry()
        test_clip()
        res = test_cv(img)
        test_render(res, img)
        test_json_roundtrip(res)
        test_vision_parse(img)
        test_vision_skip(img)
    print()
    if check.failed:
        print(f"FAILED: {check.failed} 件")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
