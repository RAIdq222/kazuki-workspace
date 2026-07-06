"""segments.json に従って横型動画からショート素材を切り出し、9:16 縦型に変換する。

使い方:
    python -m src.shorts.make_shorts INPUT.mp4 segments.json -o outdir --mode blurpad

モード:
    crop    — 中央(または --focus-x 指定位置)を 9:16 でクロップ。被写体が中央にある映像向け。
    blurpad — 元映像を幅いっぱいに収め、上下を引き伸ばしぼかし背景で埋める。構図を欠けさせたくない映像向け。
    cut     — 切り出しのみ(横型のまま)。Higgsfield reframe (AI外挿) に渡す素材を作る時はこれ。

出力: outdir/short_01.mp4, short_02.mp4, ... と outdir/manifest.json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess

from .probe import probe

OUT_W, OUT_H = 1080, 1920


def _ffmpeg_bin() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg が見つかりません。`apt-get install ffmpeg` を実行してください。")
    return exe


def _vf_crop(focus_x: float) -> str:
    # 入力高さ基準で 9:16 幅を切り出し、focus_x(0=左端,1=右端)を中心に寄せる
    return (
        f"crop=w='min(iw,ih*9/16)':h=ih:"
        f"x='clip(iw*{focus_x}-ow/2,0,iw-ow)':y=0,"
        f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,"
        f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2"
    )


def _vf_blurpad() -> str:
    return (
        f"split=2[bg][fg];"
        f"[bg]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
        f"crop={OUT_W}:{OUT_H},boxblur=luma_radius=40:luma_power=2[bgb];"
        f"[fg]scale={OUT_W}:-2[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2"
    )


def cut_and_convert(
    src: str,
    start: float,
    end: float,
    out_path: str,
    mode: str,
    focus_x: float = 0.5,
    has_audio: bool = True,
) -> None:
    dur = end - start
    cmd = [_ffmpeg_bin(), "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", src]
    if mode == "crop":
        cmd += ["-filter_complex", _vf_crop(focus_x)]
    elif mode == "blurpad":
        cmd += ["-filter_complex", _vf_blurpad()]
    elif mode == "cut":
        pass  # 画角そのまま
    else:
        raise ValueError(f"未知のモード: {mode}")
    cmd += ["-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", "aac", "-b:a", "192k"] if has_audio else ["-an"]
    cmd += ["-movflags", "+faststart", out_path]
    subprocess.run(cmd, check=True, capture_output=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="元の横型動画ファイル")
    ap.add_argument("segments", help="segments.json (select_highlights.py の出力/手動編集後)")
    ap.add_argument("-o", "--outdir", default="work/shorts_out")
    ap.add_argument("--mode", choices=["crop", "blurpad", "cut"], default="blurpad")
    ap.add_argument("--focus-x", type=float, default=0.5, help="crop 時の注視点 (0.0-1.0)")
    args = ap.parse_args()

    info = probe(args.input)
    with open(args.segments, encoding="utf-8") as f:
        segments = json.load(f)["segments"]

    os.makedirs(args.outdir, exist_ok=True)
    manifest = []
    for i, seg in enumerate(segments, 1):
        start = max(0.0, float(seg["start"]))
        end = min(info.duration, float(seg["end"]))
        out_path = os.path.join(args.outdir, f"short_{i:02d}.mp4")
        focus_x = float(seg.get("focus_x", args.focus_x))
        cut_and_convert(args.input, start, end, out_path, args.mode, focus_x, info.has_audio)
        manifest.append({
            "file": out_path,
            "start": start,
            "end": end,
            "mode": args.mode,
            "reason": seg.get("reason", ""),
        })
        print(f"{out_path}  ({start:.1f}s-{end:.1f}s, {end - start:.1f}s, {args.mode})")

    with open(os.path.join(args.outdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"source": args.input, "shorts": manifest}, f, ensure_ascii=False, indent=2)
    print(f"完了: {len(manifest)} 本 → {args.outdir}/")


if __name__ == "__main__":
    main()
