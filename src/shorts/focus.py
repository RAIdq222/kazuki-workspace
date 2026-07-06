"""クロップ注視点 (focus_x) の自動推定。完全ローカル。

アニメ顔検出 (lbpcascade_animeface, OpenCV) で区間中のキャラ位置を推定し、
検出できなければ「動きの重心」（フレーム差分の水平分布）へフォールバックする。
どちらも失敗したら 0.5（中央）。

使い方:
    python -m src.shorts.focus INPUT.mp4 --start 99.0 --end 101.0
"""
from __future__ import annotations

import os
import subprocess
import tempfile

import cv2
import numpy as np

_CASCADE_PATH = os.path.join(os.path.dirname(__file__), "data", "lbpcascade_animeface.xml")


def _sample_frames(path: str, start: float, end: float, n: int = 5) -> list[np.ndarray]:
    frames = []
    with tempfile.TemporaryDirectory() as td:
        for i in range(n):
            t = start + (end - start) * (i + 0.5) / n
            out = os.path.join(td, f"f{i}.png")
            subprocess.run(
                ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", path,
                 "-frames:v", "1", "-loglevel", "error", out],
                check=True, capture_output=True,
            )
            img = cv2.imread(out)
            if img is not None:
                frames.append(img)
    return frames


def estimate_focus_x(path: str, start: float, end: float, n_frames: int = 5) -> tuple[float, str]:
    """(focus_x, method) を返す。focus_x はフレーム幅に対する 0.0-1.0。"""
    frames = _sample_frames(path, start, end, n_frames)
    if not frames:
        return 0.5, "fallback:no-frames"

    # 1) アニメ顔検出（区間中の顔中心の中央値）
    if os.path.exists(_CASCADE_PATH):
        cascade = cv2.CascadeClassifier(_CASCADE_PATH)
        centers = []
        for img in frames:
            gray = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                             minSize=(48, 48))
            if len(faces):
                # 最大の顔を採用
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                centers.append((x + w / 2) / img.shape[1])
        if centers:
            return float(np.median(centers)), f"anime-face({len(centers)}/{len(frames)})"

    # 2) フレーム差分の水平重心（動いているものが主役、という仮定）
    if len(frames) >= 2:
        acc = np.zeros(frames[0].shape[1], dtype=np.float64)
        for a, b in zip(frames, frames[1:]):
            diff = cv2.absdiff(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY),
                               cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)).astype(np.float64)
            acc += diff.sum(axis=0)
        total = acc.sum()
        if total > 1e3:
            xs = np.arange(len(acc))
            cx = float((acc * xs).sum() / total) / len(acc)
            # 極端な端寄りはノイズの可能性が高いので中央へ緩める
            return 0.5 + (cx - 0.5) * 0.7, "motion-centroid"

    return 0.5, "fallback:center"


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input")
    ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--end", type=float, required=True)
    args = ap.parse_args()
    fx, method = estimate_focus_x(args.input, args.start, args.end)
    print(f"focus_x={fx:.3f} ({method})")


if __name__ == "__main__":
    main()
