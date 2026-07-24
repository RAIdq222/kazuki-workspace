# 宮殿レイアウトの空間整合チェック (bpy不要・常時実行)
# massing.py / build.py の先頭で run() を呼ぶ。python3 palace/lint_scene.py 単独でも実行可。
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout as _default_layout

# 舗装・砂利・池・塀・香炉は重なり判定から除外 (面や点景のため)
_FLAT = {"plaza", "gravel", "pond", "censer", "wall"}
# 意図的な重なりの許可ペア (渡り廊下は池の上を渡る 等)。現状なし
_ALLOW = set()


def _aabb(b):
    w, d = b.get("w", 2.0), b.get("d", 2.0)
    if b.get("face") in ("E", "W"):
        w, d = d, w
    t = b.get("terrace")
    if t:  # 基壇の張り出しも占有面積に含める
        w, d = max(w, t["w"]), max(d, t["d"])
    return (b["x"] - w / 2, b["y"] - d / 2, b["x"] + w / 2, b["y"] + d / 2)


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def run(mod=None, verbose=True):
    mod = mod or _default_layout
    BUILDINGS, WALLS, SITE, expand = mod.BUILDINGS, mod.WALLS, mod.SITE, mod.expand
    errors, warns = [], []
    bs = [b for b in expand() if b["kind"] not in _FLAT]

    # 1) 建物同士の footprint 重なり
    for i in range(len(bs)):
        for j in range(i + 1, len(bs)):
            a, b = bs[i], bs[j]
            key = tuple(sorted((a["id"], b["id"])))
            if tuple(key) in _ALLOW or (key[0], key[1]) in _ALLOW or (key[1], key[0]) in _ALLOW:
                continue
            if _overlap(_aabb(a), _aabb(b)):
                errors.append(f"重なり: {a['id']} × {b['id']}")

    # 2) 中軸建物は x=0 に載っているか / 対称ペアの生成確認
    for b in BUILDINGS:
        if not b.get("mirror") and b["kind"] not in _FLAT and abs(b["x"]) < 30 \
                and b.get("axis", True):
            if abs(b["x"]) > 0.01:
                errors.append(f"中軸ずれ: {b['id']} x={b['x']}")

    # 3) 敷地内に収まっているか (塀含む)
    for b in expand():
        if b["kind"] in ("plaza", "gravel", "censer"):
            continue
        x0, y0, x1, y1 = _aabb(b)
        if x0 < -SITE["x_half"] - 0.5 or x1 > SITE["x_half"] + 0.5 \
                or y0 < SITE["y0"] - 10 or y1 > SITE["y1"] + 2:
            errors.append(f"敷地外: {b['id']} ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f})")

    # 4) 塀の開口と門の位置整合 (門幅の半分より塀端が内側に来ていないか)
    gates = {b["id"]: b for b in expand() if b["kind"].startswith("gate") or b["id"] == "rear_gate"}
    for g in gates.values():
        for w in WALLS:
            if abs(w["p1"][1] - g["y"]) < 1.0 and w["p1"][1] == w["p2"][1]:  # 同じ横ライン
                xs = sorted((w["p1"][0], w["p2"][0]))
                if xs[0] < g["x"] < xs[1]:
                    errors.append(f"塀が門を貫通: {w['id']} × {g['id']}")

    if verbose:
        for e in errors:
            print("[LINT ERROR]", e)
        for w in warns:
            print("[LINT WARN]", w)
        if not errors:
            print(f"[LINT OK] buildings={len(bs)} walls={len(WALLS)}")
    return errors


if __name__ == "__main__":
    # 引数で対象を選択: python3 lint_scene.py [mansion|kogu]
    tgt = sys.argv[1] if len(sys.argv) > 1 else "mansion"
    import importlib
    m = importlib.import_module({"mansion": "layout", "kogu": "layout_kogu"}[tgt])
    sys.exit(1 if run(m) else 0)
