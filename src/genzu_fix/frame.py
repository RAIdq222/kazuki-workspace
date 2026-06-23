"""撮影フレーム（絵の枠）の検出と、フレーム基準の切り出し/戻し。

背景原図シートは「上部の管理ヘッダー＋余白＋撮影フレーム＋絵＋タップ穴」で構成される。
シート全体を生成モデルに渡すと、モデルが絵をシート全面に描き直し、ヘッダー帯の分だけ
絵が上方へずれて原図とレジストが合わない（実測: 上端余白 ~19%）。

対策: 撮影フレーム矩形を検出して**フレーム内だけ**を生成入力にし、結果を**同じ矩形へ**戻す。
"""
from __future__ import annotations
import numpy as np
from PIL import Image


def detect_frame(image_path: str, search: float = 0.33, k: float = 2.0) -> tuple[int, int, int, int]:
    """撮影フレーム矩形 (left, top, right, bottom) を推定する。

    各辺の外側 `search` 割合の帯の中で、行/列方向の暗さ投影が突出する位置（＝枠の直線）を探す。
    見つからなければシート端にフォールバック。
    """
    im = Image.open(image_path).convert("L")
    a = 255.0 - np.asarray(im).astype(float)  # 暗い=線=大
    H, W = a.shape
    row = a.sum(1) / W
    col = a.sum(0) / H

    def first_peak(profile, lo, hi, from_start):
        th = profile.mean() + k * profile.std()
        idx = [i for i in range(lo, hi) if profile[i] > th]
        if not idx:
            return None
        return min(idx) if from_start else max(idx)

    top = first_peak(row, 0, int(H * search), True)
    bottom = first_peak(row, int(H * (1 - search)), H, False)
    left = first_peak(col, 0, int(W * search), True)
    right = first_peak(col, int(W * (1 - search)), W, False)

    top = 0 if top is None else top
    left = 0 if left is None else left
    bottom = H - 1 if bottom is None else bottom
    right = W - 1 if right is None else right
    return (left, top, right, bottom)


def crop_to_frame(image_path: str, out_path: str, frame=None):
    """フレームで切り出して保存。frame 未指定なら自動検出。戻り値: frame 矩形。"""
    if frame is None:
        frame = detect_frame(image_path)
    im = Image.open(image_path).convert("RGB")
    im.crop(frame).save(out_path)
    return frame


def paste_into_frame(canvas_size, frame, content_path: str, out_path: str,
                     bg=(255, 255, 255)):
    """生成結果をフレーム矩形に正確に戻し、フルキャンバスの画像として保存する。
    canvas_size=(W,H), frame=(l,t,r,b)。フレーム外（ヘッダー/余白）は bg で塗る。
    """
    l, t, r, b = frame
    content = Image.open(content_path).convert("RGB").resize((r - l, b - t), Image.LANCZOS)
    canvas = Image.new("RGB", canvas_size, bg)
    canvas.paste(content, (l, t))
    canvas.save(out_path)
    return out_path
