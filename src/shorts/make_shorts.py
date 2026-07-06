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
    trim_bottom: float = 0.0,
) -> None:
    dur = end - start
    cmd = [_ffmpeg_bin(), "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", src]
    # 焼き込み字幕などの下帯を先に切り落とす（trim_bottom は高さに対する割合）
    pre = f"crop=iw:ih*{1.0 - trim_bottom}:0:0," if trim_bottom > 0 else ""
    if mode == "crop":
        cmd += ["-filter_complex", pre + _vf_crop(focus_x)]
    elif mode == "blurpad":
        cmd += ["-filter_complex", pre + _vf_blurpad()]
    elif mode == "cut":
        if pre:
            cmd += ["-filter_complex", pre.rstrip(",")]
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
    trim_bottom: float = 0.0,
) -> list[dict]:
    """マイクロカット群を記載順に切り出して結合する（docs/shorts-editing-style.md の型）。"""
    tmp_paths = []
    done = []
    for j, cut in enumerate(cuts):
        start = max(0.0, float(cut["start"]))
        end = min(duration, float(cut["end"]))
        tmp = f"{out_path}.part{j:02d}.mp4"
        focus_x = float(cut.get("focus_x", default_focus_x))
        tb = float(cut.get("trim_bottom", trim_bottom))  # カット単位で上書き可（字幕行数差対応）
        cut_and_convert(src, start, end, tmp, mode, focus_x, has_audio, tb)
        tmp_paths.append(tmp)
        done.append({"start": start, "end": end, "focus_x": focus_x, "note": cut.get("note", "")})
    concat_clips(tmp_paths, out_path)
    for p in tmp_paths:
        os.remove(p)
    return done


def apply_audio_bed(src: str, video_path: str, bed: dict) -> None:
    """モンタージュ映像に「連続した元音声」を敷き直す（音声ベッド方式）。

    カット毎に音声を切り貼りすると BGM・セリフの繋ぎ目が破綻するため、
    参照ショートと同じく音声は元音声の連続区間をそのまま使い、映像だけをモンタージュにする。

    bed の書式:
      {"start": 秒}                                  … 単一の連続区間（従来）
      {"parts": [{"start": s, "end": e}, ...],
       "crossfade": 0.3}                             … 複数区間をクロスフェードで接続。
                                                        フレーズ単位で音声パートを削る時に使う。
                                                        接続点は映像のカット替わりに合わせること。
    いずれも末尾 0.4 秒をフェードアウトし、長さは映像に合わせて切る。
    """
    vdur = probe(video_path).duration
    tmp = video_path + ".bed.mp4"
    end_fade = f"afade=t=out:st={max(0.0, vdur - 0.4):.3f}:d=0.4"

    if "parts" in bed:
        parts = bed["parts"]
        xf = float(bed.get("crossfade", 0.3))
        n = len(parts)
        fc = f"[1:a]asplit={n}" + "".join(f"[s{i}]" for i in range(n)) + ";"
        for i, p in enumerate(parts):
            fc += (f"[s{i}]atrim={float(p['start']):.3f}:{float(p['end']):.3f},"
                   f"asetpts=PTS-STARTPTS[p{i}];")
        cur = "[p0]"
        for i in range(1, n):
            out = f"[x{i}]" if i < n - 1 else "[xa]"
            fc += f"{cur}[p{i}]acrossfade=d={xf:.3f}{out};"
            cur = out
        if n == 1:
            fc += "[p0]anull[xa];"
        fc += f"[xa]{end_fade}[aout]"
        cmd = [_ffmpeg_bin(), "-y", "-i", video_path, "-i", src,
               "-filter_complex", fc,
               "-map", "0:v", "-map", "[aout]",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
               "-shortest", "-movflags", "+faststart", tmp]
    else:
        cmd = [_ffmpeg_bin(), "-y",
               "-i", video_path,
               "-ss", f"{float(bed.get('start', 0.0)):.3f}", "-i", src,
               "-map", "0:v", "-map", "1:a",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
               "-af", end_fade,
               "-shortest", "-movflags", "+faststart", tmp]
    subprocess.run(cmd, check=True, capture_output=True)
    os.replace(tmp, video_path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="元の横型動画ファイル")
    ap.add_argument("segments", help="segments.json (select_highlights.py の出力/手動編集後)")
    ap.add_argument("-o", "--outdir", default="work/shorts_out")
    ap.add_argument("--mode", choices=["crop", "blurpad", "cut"], default="crop")
    ap.add_argument("--focus-x", type=float, default=0.5, help="crop 時の注視点 (0.0-1.0)")
    ap.add_argument("--auto-focus", action="store_true",
                    help="focus_x 未指定のカットをアニメ顔検出/動き重心で自動推定 (要 opencv)")
    ap.add_argument("--trim-bottom", type=float, default=0.0,
                    help="下帯(焼き込み字幕など)を切り落とす高さ割合 (例 0.12)")
    args = ap.parse_args()

    estimate = None
    if args.auto_focus:
        from .focus import estimate_focus_x  # 遅延import（cv2 はオプション依存）
        estimate = estimate_focus_x

    info = probe(args.input)
    with open(args.segments, encoding="utf-8") as f:
        segments = json.load(f)["segments"]

    os.makedirs(args.outdir, exist_ok=True)
    manifest = []
    for i, seg in enumerate(segments, 1):
        out_path = os.path.join(args.outdir, f"short_{i:02d}.mp4")
        if "cuts" in seg:  # モンタージュ形式
            cuts = seg["cuts"]
            if estimate:
                for cut in cuts:
                    if "focus_x" not in cut:
                        fx, method = estimate(args.input, float(cut["start"]), float(cut["end"]))
                        cut["focus_x"] = round(fx, 3)
                        cut["focus_method"] = method
            done = make_montage(args.input, cuts, out_path, args.mode,
                                args.focus_x, info.has_audio, info.duration,
                                args.trim_bottom)
            # 音声ベッド: {"audio_bed": {...}} 指定時、連続音声を敷き直す
            bed = seg.get("audio_bed")
            if bed is not None and info.has_audio:
                apply_audio_bed(args.input, out_path, bed)
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
        cut_and_convert(args.input, start, end, out_path, args.mode, focus_x, info.has_audio, args.trim_bottom)
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
