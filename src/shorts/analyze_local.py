"""ローカル完結の動画解析（Higgsfield等の外部サービス不使用）。

ffmpeg のシーン検出 + 音量解析 + faster-whisper(ローカル文字起こし) を統合し、
Higgsfield video_analysis 互換の scenes JSON を出力する。
→ そのまま select_highlights.py / make_shorts.py に流せる。

使い方:
    python -m src.shorts.analyze_local INPUT.mp4 -o analysis.json [--no-whisper]

出力スキーマ（互換）:
    {"scenes": [{"scene_number", "timestamp_start", "timestamp_end",
                 "audio": "<文字起こし>", "visual": "<motion/loudnessタグ>",
                 "motion": 0-1, "loudness_db": float}]}
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess

from .probe import probe


def _ffmpeg_bin() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg が見つかりません")
    return exe


def detect_scene_cuts(path: str, threshold: float = 0.3) -> list[float]:
    """ffmpeg select=scene でカット境界の秒位置を検出する。"""
    proc = subprocess.run(
        [_ffmpeg_bin(), "-i", path, "-vf",
         f"select='gt(scene,{threshold})',metadata=print:file=-",
         "-an", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    cuts = []
    for line in proc.stdout.splitlines():
        m = re.match(r"frame:\d+\s+pts:\d+\s+pts_time:([\d.]+)", line)
        if m:
            cuts.append(float(m.group(1)))
    return cuts


def loudness_profile(path: str, window: float = 0.5) -> list[tuple[float, float]]:
    """(時刻, RMS dB) の列。ametadata 経由で astats の窓別RMSを得る。"""
    n_samples = int(48000 * window)
    proc = subprocess.run(
        [_ffmpeg_bin(), "-i", path, "-vn", "-af",
         f"aresample=48000,asetnsamples={n_samples},"
         "astats=metadata=1:reset=1,"
         "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    out = []
    t = None
    for line in proc.stdout.splitlines():
        m = re.match(r"frame:\d+\s+pts:\d+\s+pts_time:([\d.]+)", line)
        if m:
            t = float(m.group(1))
            continue
        m = re.match(r"lavfi\.astats\.Overall\.RMS_level=(-?[\d.]+|-inf)", line)
        if m and t is not None:
            db = -90.0 if m.group(1) == "-inf" else float(m.group(1))
            out.append((t, db))
            t = None
    return out


def transcribe(path: str, model_size: str = "small", language: str | None = "ja") -> list[dict]:
    """faster-whisper によるローカル文字起こし。[{start, end, text}]

    注意: BGM+ナレーション混在素材では VAD が発話を丸ごと落とすため vad_filter は使わない。
    """
    from faster_whisper import WhisperModel  # 遅延import（--no-whisper時に不要）

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(path, language=language, vad_filter=False)
    return [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments]


def _fmt_ts(sec: float) -> str:
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


def build_scenes(
    duration: float,
    cuts: list[float],
    loudness: list[tuple[float, float]],
    speech: list[dict],
    min_scene: float = 0.8,
) -> list[dict]:
    # カット境界 → シーン区間（短すぎる区間は結合）
    bounds = [0.0] + [c for c in cuts if min_scene < c < duration - min_scene] + [duration]
    merged = [bounds[0]]
    for b in bounds[1:]:
        if b - merged[-1] >= min_scene:
            merged.append(b)
    if merged[-1] < duration:
        merged[-1] = duration

    # 全体の音量分布（相対的な盛り上がり判定用）
    dbs = [db for _, db in loudness] or [-30.0]
    db_hi = sorted(dbs)[int(len(dbs) * 0.8)]  # 上位20%閾値

    scenes = []
    for i in range(len(merged) - 1):
        s, e = merged[i], merged[i + 1]
        texts = [sp["text"] for sp in speech if sp["start"] < e and sp["end"] > s]
        win = [db for t, db in loudness if s <= t < e]
        loud = (sum(win) / len(win)) if win else -90.0
        n_subcuts = sum(1 for c in cuts if s < c < e)
        motion = min(1.0, n_subcuts / max(e - s, 0.1) / 2.0)  # カット密度を運動量の代理に
        tags = []
        if loud >= db_hi:
            tags.append("loud peak / exciting audio")
        if motion > 0.4:
            tags.append("dynamic fast cuts / high motion")
        if not texts:
            tags.append("no dialogue (SFX/BGM only)")
        scenes.append({
            "scene_number": i + 1,
            "timestamp_start": _fmt_ts(s),
            "timestamp_end": _fmt_ts(e),
            "start_sec": round(s, 2),
            "end_sec": round(e, 2),
            "audio": " ".join(texts),
            "visual": ", ".join(tags) or "static scene",
            "motion": round(motion, 2),
            "loudness_db": round(loud, 1),
        })
    return scenes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input")
    ap.add_argument("-o", "--out", default="analysis_local.json")
    ap.add_argument("--scene-threshold", type=float, default=0.3)
    ap.add_argument("--whisper-model", default="small")
    ap.add_argument("--language", default="ja")
    ap.add_argument("--no-whisper", action="store_true", help="文字起こしを省略")
    args = ap.parse_args()

    info = probe(args.input)
    cuts = detect_scene_cuts(args.input, args.scene_threshold)
    loud = loudness_profile(args.input) if info.has_audio else []
    speech = [] if (args.no_whisper or not info.has_audio) else transcribe(
        args.input, args.whisper_model, args.language)
    scenes = build_scenes(info.duration, cuts, loud, speech)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"scenes": scenes, "source": args.input, "duration": info.duration,
                   "engine": "local(ffmpeg-scdet+astats+faster-whisper)"}, f,
                  ensure_ascii=False, indent=2)
    print(f"{len(scenes)} シーン → {args.out} (カット境界 {len(cuts)}, 発話 {len(speech)})")


if __name__ == "__main__":
    main()
