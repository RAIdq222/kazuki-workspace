"""シーンライブラリ取り込み: Clipperクリップ→等間隔フレーム＋メタデータmanifest。

設計: docs/scene-library-design.md。この環境はYouTube直DL不可のため、
Personal Clipper のクリップ（CloudFront mp4）を入力にする。
クリップの start_seconds を渡すと、各フレームの元動画タイムスタンプを復元して
manifest に書く（ライブラリの「▶ この場面から再生」の要）。

使い方（1クリップずつ）:
    python -m src.shorts.scene_ingest clip_01.mp4 \
        --video-id 8AoIEagt3x8 --start-seconds 18.3 \
        --interval 2 --crop-bottom 0.26 -o work/scenes/8AoIEagt3x8_c1

出力:
    <out>/frame_0001.png ...   (字幕帯クロップ済み)
    <out>/manifest.json        [{file, t_clip, t_orig, phash}]
近接pHashのフレームは間引く（--dedup-threshold, デフォルト6bit差以内を重複扱い）。

この後の手順（AIワーカー）:
 1. フレームを目視して閉集合タグ＋キャプションを付ける（語彙は SKILL.md 参照）
 2. quality>=2 のフレームを media_upload → media_confirm
 3. POST /api/agent/scenes へバルク登録
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess

from PIL import Image


def ahash(img: Image.Image, size: int = 8) -> int:
    g = img.convert("L").resize((size, size), Image.LANCZOS)
    px = list(g.getdata())
    avg = sum(px) / len(px)
    bits = 0
    for i, p in enumerate(px):
        if p > avg:
            bits |= 1 << i
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("clip")
    ap.add_argument("--video-id", required=True)
    ap.add_argument("--start-seconds", type=float, required=True,
                    help="Clipperレスポンスの start_seconds")
    ap.add_argument("--interval", type=float, default=2.0, help="サンプリング間隔秒")
    ap.add_argument("--crop-bottom", type=float, default=0.0,
                    help="焼き込み字幕帯の除去率。マスター素材=0（無劣化）、"
                         "Clipper由来のみ 1行≈0.14 / 2行≈0.26 を指定")
    ap.add_argument("--dedup-threshold", type=int, default=6)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    tmp = os.path.join(args.out, "_raw")
    os.makedirs(tmp, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "quiet", "-y", "-i", args.clip,
         "-vf", f"fps=1/{args.interval}", os.path.join(tmp, "f_%04d.png")],
        check=True)

    manifest, last_hash = [], None
    kept = 0
    files = sorted(os.listdir(tmp))
    for i, name in enumerate(files):
        src = os.path.join(tmp, name)
        im = Image.open(src)
        h = ahash(im)
        if last_hash is not None and hamming(h, last_hash) <= args.dedup_threshold:
            os.remove(src)
            continue  # 直前フレームとほぼ同じ → 間引き
        last_hash = h
        kept += 1
        w, height = im.size
        out_name = f"frame_{kept:04d}.png"
        im.crop((0, 0, w, int(height * (1 - args.crop_bottom)))).save(
            os.path.join(args.out, out_name))
        os.remove(src)
        t_clip = i * args.interval
        manifest.append({
            "file": out_name,
            "t_clip": round(t_clip, 1),
            "t_orig": round(args.start_seconds + t_clip, 1),
            "video_id": args.video_id,
        })
    os.rmdir(tmp)
    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f"{kept}/{len(files)} frames kept -> {args.out}/manifest.json")


if __name__ == "__main__":
    main()
