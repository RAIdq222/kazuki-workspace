"""Higgsfield video_analysis のシーン解析結果から、ショート向けハイライト区間の候補を作る。

入力: video_analysis_status の結果 JSON（scenes 配列）を保存したファイル。
出力: segments.json — [{start, end, score, reason, scenes:[...]}] を score 降順で並べたもの。

シーン JSON のスキーマ差異に耐えるよう、start/end/description はキー名のゆらぎを吸収する。
最終的な採否は人（または Claude セッション）が segments.json を編集して決める前提の叩き台。
"""
from __future__ import annotations

import argparse
import json
import re
from typing import Any

# 「見どころ」らしさのスコアリング用キーワード（AI動画は台詞が無いことも多いので視覚語彙中心）
KEYWORDS = {
    3.0: ["explod", "collide", "crash", "transform", "reveal", "jump", "fight", "chase",
          "爆発", "変身", "衝突", "激突", "決壊", "崩壊", "疾走", "戦闘"],
    2.0: ["fast", "dynamic", "dramatic", "intense", "climax", "sudden", "close-up", "closeup",
          "迫力", "急", "クライマックス", "接写", "アップ", "疾走感", "劇的"],
    1.0: ["action", "motion", "moving", "run", "fly", "dance", "spin", "glow", "light",
          "動き", "走", "飛", "踊", "回転", "光", "輝"],
    -1.0: ["static", "still", "slow", "calm", "idle", "empty",
           "静止", "停止", "ゆっくり", "静か", "無人"],
}


def _get(scene: dict[str, Any], *names: str, default: Any = None) -> Any:
    for n in names:
        if n in scene and scene[n] is not None:
            return scene[n]
    return default


def _to_seconds(v: Any) -> float:
    """秒数 float / "MM:SS" / "HH:MM:SS(.ms)" のいずれも受け付ける。"""
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if re.fullmatch(r"[\d.]+", s):
        return float(s)
    parts = [float(p) for p in s.split(":")]
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


def normalize_scenes(payload: Any) -> list[dict[str, Any]]:
    """解析結果ペイロードを [{start, end, description}] に正規化する。"""
    scenes = payload
    if isinstance(payload, dict):
        scenes = payload.get("scenes") or payload.get("result", {}).get("scenes") or []
    norm = []
    for i, sc in enumerate(scenes):
        start = _get(sc, "start", "start_time", "timestamp_start", "start_sec", "from", "begin", default=None)
        end = _get(sc, "end", "end_time", "timestamp_end", "end_sec", "to", "finish", default=None)
        # Higgsfield video_analysis は label/visual/audio に分かれている
        desc = _get(sc, "description", "summary", "caption", "text", "content", default=None)
        if desc is None:
            desc = " / ".join(str(sc[k]) for k in ("label", "visual", "audio") if sc.get(k))
        if start is None or end is None:
            continue
        norm.append({
            "index": i,
            "start": _to_seconds(start),
            "end": _to_seconds(end),
            "description": str(desc),
        })
    return norm


def score_scene(desc: str) -> float:
    d = desc.lower()
    score = 0.0
    for weight, words in KEYWORDS.items():
        for w in words:
            if w.lower() in d:
                score += weight
    return score


def build_segments(
    scenes: list[dict[str, Any]],
    min_len: float,
    max_len: float,
    count: int,
) -> list[dict[str, Any]]:
    """スコアの高いシーンを核に、隣接シーンを繋げて min_len〜max_len の区間を作る。"""
    for sc in scenes:
        sc["score"] = score_scene(sc["description"])

    ranked = sorted(scenes, key=lambda s: s["score"], reverse=True)
    used: set[int] = set()
    segments = []
    for core in ranked:
        if len(segments) >= count:
            break
        if core["index"] in used:
            continue
        # 核シーンから前後に伸ばして目標尺に近づける
        chunk = [core]
        while (chunk[-1]["end"] - chunk[0]["start"]) < min_len:
            prev_i = chunk[0]["index"] - 1
            next_i = chunk[-1]["index"] + 1
            prev_sc = next((s for s in scenes if s["index"] == prev_i and s["index"] not in used), None)
            next_sc = next((s for s in scenes if s["index"] == next_i and s["index"] not in used), None)
            # スコアの高い方向へ伸ばす（同点なら後ろへ）
            if next_sc and (not prev_sc or next_sc["score"] >= prev_sc["score"]):
                chunk.append(next_sc)
            elif prev_sc:
                chunk.insert(0, prev_sc)
            else:
                break
        start = chunk[0]["start"]
        end = min(chunk[-1]["end"], start + max_len)
        if end - start < min(min_len, 4.0):
            continue
        used.update(s["index"] for s in chunk)
        segments.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "score": round(sum(s["score"] for s in chunk), 2),
            "reason": " / ".join(s["description"][:60] for s in chunk),
            "scene_indexes": [s["index"] for s in chunk],
        })
    return sorted(segments, key=lambda s: s["score"], reverse=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("analysis_json", help="video_analysis_status の結果を保存した JSON ファイル")
    ap.add_argument("-o", "--out", default="segments.json")
    ap.add_argument("--min-len", type=float, default=20.0, help="1本あたりの最短尺(秒)")
    ap.add_argument("--max-len", type=float, default=45.0, help="1本あたりの最長尺(秒)")
    ap.add_argument("--count", type=int, default=3, help="候補本数")
    args = ap.parse_args()

    with open(args.analysis_json, encoding="utf-8") as f:
        payload = json.load(f)
    scenes = normalize_scenes(payload)
    if not scenes:
        raise SystemExit("シーンが取得できませんでした。JSON の構造を確認してください。")
    segments = build_segments(scenes, args.min_len, args.max_len, args.count)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"segments": segments, "total_scenes": len(scenes)}, f, ensure_ascii=False, indent=2)
    print(f"{len(segments)} 区間を {args.out} に出力しました（要レビュー）")
    for seg in segments:
        print(f"  {seg['start']:>7.1f}s - {seg['end']:>7.1f}s  score={seg['score']:>5.1f}  {seg['reason'][:80]}")


if __name__ == "__main__":
    main()
