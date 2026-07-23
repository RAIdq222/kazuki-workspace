"""生成結果の位置ずれ計測 — 原図と restored_full の相似変換（拡大率＋平行移動）を推定する。

構図ずれの主要モード「モデルが作画フレーム内へズームして描き直す」（frame→canvas 再フレーミング。
c283 実測: 内容は良いのに全体が約1.3倍拡大＋上シフト）を数値化する。B段（生成）の幾何ズレは
A/C 段と違い決定的には防げないが、ズレが**一様な相似変換**で説明できる場合は逆変換で
原図グリッドへ戻せる（restored_aligned.png）＝「他は不満ない」生成を救済できる。

推定はローカルで完結・決定的（numpy/PILのみ・API不要）:
  両画像を縮小 → 赤指示を背景色で潰す（原図側）→ 輝度勾配（線画のエッジ）→
  スケール候補を粗→細の2段階で総当たり → FFT相互相関で平行移動と一致度（正規化相関）。

score は正規化相関のピーク値。0.05未満は線がほぼ噛み合っていない＝推定を信用しない
（low_confidence）。しきい値は c283 級のズレ（scale 1.2〜1.4）を拾う目的の実用値。
"""
from __future__ import annotations

import json
import os

import numpy as np

# 「位置整合OK」とみなす許容: 拡大率±2%・平行移動±1.5%（それ以上は mismatch）
SCALE_TOL = 0.02
SHIFT_TOL_PCT = 1.5
MIN_SCORE = 0.05


def _prep_edges(path: str, long_edge: int = 768, drop_red: bool = False):
    """画像→縮小→（赤指示除去）→勾配エッジ（平均0）。戻り: (edge配列, 原寸(W,H))。"""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    W, H = im.size
    s = long_edge / max(W, H)
    if s < 1:
        im = im.resize((max(1, round(W * s)), max(1, round(H * s))), Image.BILINEAR)
    a = np.asarray(im, dtype=np.float32)
    if drop_red:
        # 原図の赤ペン指示（EYE線・書き込み）は生成側に無い＝相関のノイズなので背景色で潰す
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        red = (r > 140) & (r - g > 60) & (r - b > 60)
        a = a.copy()
        a[red] = a.reshape(-1, 3).mean(axis=0)
    gray = a.mean(axis=2)
    gy, gx = np.gradient(gray)
    e = np.hypot(gx, gy).astype(np.float32)
    p = float(np.percentile(e, 99.0))
    if p > 0:
        e = np.clip(e / p, 0.0, 1.0)
    return e - e.mean(), (W, H)


def _resize_f(arr: np.ndarray, size_wh: tuple[int, int]) -> np.ndarray:
    from PIL import Image
    return np.asarray(Image.fromarray(arr, mode="F").resize(size_wh, Image.BILINEAR),
                      dtype=np.float32)


def _best_shift(fa, fb, shape) -> tuple[float, int, int]:
    """相互相関 c(d)=Σ a(x)·b(x+d) のピーク。戻り: (ピーク値(未正規化), dy, dx)。
    ピーク d は「a を +d 動かすと b に重なる」＝ b ≈ a を +d 平行移動。"""
    cc = np.fft.irfft2(np.conj(fa) * fb, s=shape)
    idx = np.unravel_index(int(np.argmax(cc)), cc.shape)
    dy, dx = int(idx[0]), int(idx[1])
    if dy > shape[0] // 2:
        dy -= shape[0]
    if dx > shape[1] // 2:
        dx -= shape[1]
    return float(cc[idx]), dy, dx


def measure(genzu_png: str, restored_png: str, out_dir: str | None = None) -> dict:
    """restored ≈ genzu を scale 倍して (dx,dy) 動かした絵、と仮定して最良の相似変換を推定。

    戻り dict: scale / dx_pct / dy_pct（restored 原寸幅・高さ比%）/ score / verdict
    （ok | mismatch | low_confidence）。out_dir 指定時は align.json を常に書き、
    mismatch の時は逆変換版 restored_aligned.png と重ね図 align_overlay_{before,after}.jpg も書く。
    """
    eg, g_full = _prep_edges(genzu_png, drop_red=True)
    er, r_full = _prep_edges(restored_png)
    # FFT キャンバス（巻き込み対策に1.5倍パッド）。restored 側は固定なので前計算。
    PH = int(max(eg.shape[0], er.shape[0]) * 1.5)
    PW = int(max(eg.shape[1], er.shape[1]) * 1.5)

    def embed(a):
        c = np.zeros((PH, PW), np.float32)
        c[:a.shape[0], :a.shape[1]] = a
        return c

    fb = np.fft.rfft2(embed(er))
    nb = float(np.linalg.norm(er)) or 1.0

    def try_scale(s: float):
        w, h = max(1, round(eg.shape[1] * s)), max(1, round(eg.shape[0] * s))
        if w > PW or h > PH:
            return None
        a = _resize_f(eg, (w, h))
        peak, dy, dx = _best_shift(np.fft.rfft2(embed(a)), fb, (PH, PW))
        na = float(np.linalg.norm(a)) or 1.0
        return (peak / (na * nb), float(s), dx, dy)

    best = None
    for s in np.round(np.arange(0.70, 1.4001, 0.02), 3):          # 粗
        r = try_scale(float(s))
        if r and (best is None or r[0] > best[0]):
            best = r
    for s in np.round(np.arange(best[1] - 0.02, best[1] + 0.0201, 0.005), 3):  # 細
        r = try_scale(float(s))
        if r and r[0] > best[0]:
            best = r
    score, scale, dx, dy = best

    k = r_full[0] / er.shape[1]  # 縮小→原寸の係数（restored 基準）
    dx_full, dy_full = dx * k, dy * k
    dx_pct = 100.0 * dx_full / r_full[0]
    dy_pct = 100.0 * dy_full / r_full[1]
    if score < MIN_SCORE:
        verdict = "low_confidence"
    elif abs(scale - 1.0) <= SCALE_TOL and max(abs(dx_pct), abs(dy_pct)) <= SHIFT_TOL_PCT:
        verdict = "ok"
    else:
        verdict = "mismatch"
    result = {"scale": round(scale, 3), "dx_pct": round(dx_pct, 2), "dy_pct": round(dy_pct, 2),
              "score": round(score, 3), "verdict": verdict}

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "align.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        if verdict == "mismatch":
            _write_aligned(genzu_png, restored_png, out_dir, scale, dx_full, dy_full)
    return result


def _write_aligned(genzu_png: str, restored_png: str, out_dir: str,
                   scale: float, dx_full: float, dy_full: float) -> None:
    """逆変換版と重ね図を書く。重ね図: 原図の線=シアン / 生成の線=赤 / 一致=黒。"""
    from PIL import Image
    im = Image.open(restored_png).convert("RGB")
    Wf, Hf = im.size
    # restored(y) ≈ genzu_scaled(y - d) なので aligned(y) = restored(scale·y + d)
    aligned = im.transform((Wf, Hf), Image.AFFINE, (scale, 0.0, dx_full, 0.0, scale, dy_full),
                           resample=Image.BICUBIC, fillcolor=(255, 255, 255))
    aligned.save(os.path.join(out_dir, "restored_aligned.png"))
    gz = np.asarray(Image.open(genzu_png).convert("L").resize((Wf, Hf)), np.uint8)
    for name, img in (("align_overlay_before.jpg", im), ("align_overlay_after.jpg", aligned)):
        rl = np.asarray(img.convert("L"), np.uint8)
        ov = np.stack([gz, rl, rl], axis=-1)  # R=原図(→原図だけの線はシアン), G/B=生成(→生成だけは赤)
        Image.fromarray(ov).save(os.path.join(out_dir, name), quality=88)
