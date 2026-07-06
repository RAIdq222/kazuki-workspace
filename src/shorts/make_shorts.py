"""segments.json に従って横型動画からショート素材を切り出し、9:16 縦型に変換する。

使い方:
    python -m src.shorts.make_shorts INPUT.mp4 segments.json -o outdir --mode crop

モード:
    crop    — 中央(または focus_x 指定位置)を 9:16 でクロップ。被写体が中央にある映像向け。
    blurpad — 元映像を幅いっぱいに収め、上下を引き伸ばしぼかし背景で埋める。構図を欠けさせたくない映像向け。
    cut     — 切り出しのみ(横型のまま)。Higgsfield reframe (AI外挿) に渡す素材を作る時はこれ。

segments.json の書式（2形式対応）:
    連続区間:     {"segments": [{"start": 99.0, "end": 125.0, "focus_x": 0.5}]}
    モンタージュ: {"segments": [{"cuts": [{"start": 103.0, "end": 105.0, "focus_x": 0.4},
                                          {"start": 99.0, "end": 101.0}, ...]}]}
    モンタージュは cuts を記載順に結合する（並べ替え済みの EDL として扱う）。
    編集の型は docs/shorts-editing-style.md を参照。

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


def concat_clips(clip_paths: list[str], out_path: str) -> None:
    """同一設定でエンコード済みのクリップ群を再エンコードなしで結合する。"""
    list_path = out_path + ".txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")
    subprocess.run(
        [_ffmpeg_bin(), "-y", "-f", "concat", "-safe", "0", "-i", list_path,
         "-c", "copy", "-movflags", "+faststart", out_path],
        check=True, capture_output=True,
    )
    os.remove(list_path)


def make_montage(
    src: str,
    cuts: list[dict],
    out_path: str,
    mode: str,
    default_focus_x: float,
    has_audio: bool,
    duration: float,
) -> list[dict]:
    """マイクロカット群を記載順に切り出して結合する（docs/shorts-editing-style.md の型）。"""
    tmp_paths = []
    done = []
    for j, cut in enumerate(cuts):
        start = max(0.0, float(cut["start"]))
        end = min(duration, float(cut["end"]))
        tmp = f"{out_path}.part{j:02d}.mp4"
        focus_x = float(cut.get("focus_x", default_focus_x))
        cut_and_convert(src, start, end, tmp, mode, focus_x, has_audio)
        tmp_paths.append(tmp)
        done.append({"start": start, "end": end, "focus_x": focus_x, "note": cut.get("note", "")})
    concat_clips(tmp_paths, out_path)
    for p in tmp_paths:
        os.remove(p)
    return done


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="元の横型動画ファイル")
    ap.add_argument("segments", help="segments.json (select_highlights.py の出力/手動編集後)")
    ap.add_argument("-o", "--outdir", default="work/shorts_out")
    ap.add_argument("--mode", choices=["crop", "blurpad", "cut"], default="crop")
    ap.add_argument("--focus-x", type=float, default=0.5, help="crop 時の注視点 (0.0-1.0)")
    args = ap.parse_args()

    info = probe(args.input)
    with open(args.segments, encoding="utf-8") as f:
        segments = json.load(f)["segments"]

    os.makedirs(args.outdir, exist_ok=True)
    manifest = []
    for i, seg in enumerate(segments, 1):
        out_path = os.path.join(args.outdir, f"short_{i:02d}.mp4")
        if "cuts" in seg:  # モンタージュ形式
            done = make_montage(args.input, seg["cuts"], out_path, args.mode,
                                args.focus_x, info.has_audio, info.duration)
            total = sum(c["end"] - c["start"] for c in done)
            manifest.append({
                "file": out_path,
                "cuts": done,
                "mode": args.mode,
                "reason": seg.get("reason", ""),
            })
            print(f"{out_path}  (モンタージュ {len(done)}カット, 計{total:.1f}s, {args.mode})")
            continue
        start = max(0.0, float(seg["start"]))
        end = min(info.duration, float(seg["end"]))
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
