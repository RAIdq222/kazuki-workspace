"""ショート動画の納品パッケージを作る。

動画 + メタ情報(タイトル/説明/ハッシュタグ) + 確認用サムネイルを1フォルダにまとめ、
そのままYouTube Shortsのアップロード画面にコピペできる形にする。

使い方:
    python -m src.shorts.package_short SHORT.mp4 --meta meta.json -o deliver/
meta.json:
    {"title": "...", "description": "...", "hashtags": ["#Shorts", ...],
     "thumbnail_at": 0.5}   # サムネ抽出位置(秒)。省略時は先頭フレーム
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess

from .probe import probe


def package(video_path: str, meta: dict, outdir: str) -> str:
    name = meta.get("name") or os.path.splitext(os.path.basename(video_path))[0]
    dest = os.path.join(outdir, name)
    os.makedirs(dest, exist_ok=True)

    info = probe(video_path)
    if info.width / info.height != 9 / 16:
        print(f"警告: {info.width}x{info.height} は 9:16 ではありません")

    # 動画本体
    dst_video = os.path.join(dest, f"{name}.mp4")
    shutil.copy2(video_path, dst_video)

    # 確認用サムネイル（Shortsは自動サムネだが、内容確認と将来のカスタム用に残す）
    t = float(meta.get("thumbnail_at", 0.0))
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", video_path, "-frames:v", "1",
         "-loglevel", "error", os.path.join(dest, "thumbnail.jpg")],
        check=True, capture_output=True,
    )

    # アップロード用テキスト（コピペ前提）
    hashtags = meta.get("hashtags", ["#Shorts"])
    lines = [
        "=== タイトル ===",
        meta.get("title", name),
        "",
        "=== 説明文 ===",
        meta.get("description", ""),
        "",
        " ".join(hashtags),
        "",
        "=== 情報 ===",
        f"尺: {info.duration:.1f}秒 / {info.width}x{info.height}",
        f"元動画: {meta.get('source_url', '-')}",
    ]
    with open(os.path.join(dest, "upload.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    with open(os.path.join(dest, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"納品パッケージ: {dest}/")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video")
    ap.add_argument("--meta", required=True, help="タイトル等を書いた meta.json")
    ap.add_argument("-o", "--outdir", default="work/deliver")
    args = ap.parse_args()

    with open(args.meta, encoding="utf-8") as f:
        meta = json.load(f)
    package(args.video, meta, args.outdir)


if __name__ == "__main__":
    main()
