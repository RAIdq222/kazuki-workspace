"""完成ショートのセルフチェック用レビューシートを生成する。

出力ショートに対して以下を1フォルダにまとめる:
  1. 各カットの中間フレーム + カット継ぎ目直後のフレーム (JPEG)
  2. 出力音声の文字起こし（タイムスタンプ付き）
  3. カット表: 映像時間帯 / note / その時間帯に鳴っている音声テキスト の対応表
  4. 機械チェック: 解像度・尺・音声有無・下帯の字幕残り疑い（エッジ密度）

これを Claude / 人が見て「音と映像の意味ズレ」「字幕残り」「フレーミング」を検品し、
問題があれば EDL を直して再ビルドする（改善ループ）。

使い方:
    python -m src.shorts.review_sheet OUT.mp4 EDL.json -o review/
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess

import numpy as np

from .probe import probe


def extract_frame(video: str, t: float, out_jpg: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{max(0.0, t):.3f}", "-i", video,
         "-frames:v", "1", "-loglevel", "error", out_jpg],
        check=True, capture_output=True,
    )


def bottom_band_edge_density(jpg_path: str) -> tuple[float, float]:
    """(下帯12%のエッジ密度, 最下端5%のエッジ密度)。字幕残りがあると高くなる。

    trim不足の字幕は「最下端に細い帯」として残ることが多いため、
    最下端ストリップは別枠で低めの閾値で見る。
    """
    import cv2

    img = cv2.imread(jpg_path)
    if img is None:
        return 0.0, 0.0
    h = img.shape[0]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    band = cv2.Canny(gray[int(h * 0.88):, :], 100, 200)
    strip = cv2.Canny(gray[int(h * 0.95):, :], 60, 150)
    return float(band.mean()), float(strip.mean())


def transcribe_out(video: str) -> list[dict]:
    from faster_whisper import WhisperModel

    model = WhisperModel("small", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(video, language="ja", vad_filter=False,
                               condition_on_previous_text=False)
    return [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
            for s in segs]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video", help="完成ショート mp4")
    ap.add_argument("edl", help="使用した EDL (segments.json)")
    ap.add_argument("-o", "--outdir", default="work/review")
    ap.add_argument("--segment-index", type=int, default=0, help="EDL内の対象 segment 番号")
    ap.add_argument("--no-whisper", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    info = probe(args.video)
    with open(args.edl, encoding="utf-8") as f:
        seg = json.load(f)["segments"][args.segment_index]
    cuts = seg.get("cuts") or [{"start": seg["start"], "end": seg["end"], "note": ""}]

    # 出力タイムライン上の各カット位置を再構成
    timeline = []
    t = 0.0
    for c in cuts:
        d = float(c["end"]) - float(c["start"])
        timeline.append({"video_from": round(t, 2), "video_to": round(t + d, 2),
                         "src_from": c["start"], "src_to": c["end"],
                         "note": c.get("note", "")})
        t += d

    speech = [] if args.no_whisper else transcribe_out(args.video)

    checks = {
        "resolution": f"{info.width}x{info.height}",
        "resolution_ok": (info.width, info.height) == (1080, 1920),
        "duration_sec": round(info.duration, 2),
        "duration_in_16_34": 16 <= info.duration <= 34,
        "has_audio": info.has_audio,
    }

    rows = []
    max_edge = 0.0
    max_strip = 0.0
    for i, tl in enumerate(timeline, 1):
        mid = (tl["video_from"] + tl["video_to"]) / 2
        mid_jpg = os.path.join(args.outdir, f"cut{i:02d}_mid.jpg")
        extract_frame(args.video, mid, mid_jpg)
        join_jpg = None
        if i < len(timeline):
            join_jpg = os.path.join(args.outdir, f"cut{i:02d}_join.jpg")
            extract_frame(args.video, tl["video_to"] + 0.12, join_jpg)
        edge, strip = bottom_band_edge_density(mid_jpg)
        max_edge = max(max_edge, edge)
        max_strip = max(max_strip, strip)
        overlap = " / ".join(
            s["text"] for s in speech
            if s["start"] < tl["video_to"] and s["end"] > tl["video_from"] and s["text"])
        rows.append({
            "cut": i, **tl,
            "audio_text_overlap": overlap,
            "mid_frame": os.path.basename(mid_jpg),
            "join_frame": os.path.basename(join_jpg) if join_jpg else None,
            "bottom_edge_density": round(edge, 2),
            "bottom_strip_density": round(strip, 2),
        })

    # 全編走査: カット中間だけでなく 0.5 秒刻みで字幕残りを見る（カット内で字幕が
    # 出たり消えたりするため、mid フレームだけでは見逃す）
    scan_hits = []
    t = 0.25
    scan_dir = os.path.join(args.outdir, "scan")
    os.makedirs(scan_dir, exist_ok=True)
    while t < info.duration:
        jpg = os.path.join(scan_dir, f"t{t:05.1f}.jpg")
        extract_frame(args.video, t, jpg)
        edge, strip = bottom_band_edge_density(jpg)
        max_edge = max(max_edge, edge)
        max_strip = max(max_strip, strip)
        if edge > 25.0 or strip > 15.0:
            scan_hits.append({"t": round(t, 2), "band": round(edge, 2),
                              "strip": round(strip, 2), "frame": os.path.basename(jpg)})
        else:
            os.remove(jpg)  # 問題フレームだけ残す
        t += 0.5

    checks["bottom_edge_density_max"] = round(max_edge, 2)
    checks["bottom_strip_density_max"] = round(max_strip, 2)
    # 実測: 字幕なしフレームはおおむね一桁〜十数。最下端ストリップは細い残り帯に敏感
    checks["subtitle_suspect"] = max_edge > 25.0 or max_strip > 15.0
    checks["scan_hits"] = scan_hits

    sheet = {"video": args.video, "checks": checks, "cuts": rows, "transcript": speech}
    out_json = os.path.join(args.outdir, "review.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(sheet, f, ensure_ascii=False, indent=1)

    print(json.dumps(checks, ensure_ascii=False, indent=1))
    print(f"\nレビューシート: {out_json}")
    for r in rows:
        print(f" cut{r['cut']:02d} {r['video_from']:>5}-{r['video_to']:>5}s  {r['note'][:24]:24s} "
              f"audio: {r['audio_text_overlap'][:40]}")


if __name__ == "__main__":
    main()
