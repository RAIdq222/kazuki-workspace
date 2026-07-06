"""ffprobe で動画のメタ情報を取得する。"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class VideoInfo:
    path: str
    duration: float  # 秒
    width: int
    height: int
    fps: float
    has_audio: bool

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 0.0

    @property
    def is_horizontal(self) -> bool:
        return self.aspect > 1.0


def _ffprobe_bin() -> str:
    exe = shutil.which("ffprobe")
    if not exe:
        raise RuntimeError("ffprobe が見つかりません。`apt-get install ffmpeg` を実行してください。")
    return exe


def probe(path: str) -> VideoInfo:
    out = subprocess.check_output(
        [
            _ffprobe_bin(), "-v", "error",
            "-print_format", "json",
            "-show_format", "-show_streams",
            path,
        ],
        text=True,
    )
    data = json.loads(out)
    vstream = next(s for s in data["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in data["streams"])
    num, _, den = vstream.get("avg_frame_rate", "0/1").partition("/")
    fps = (float(num) / float(den)) if den and float(den) else 0.0
    return VideoInfo(
        path=path,
        duration=float(data["format"]["duration"]),
        width=int(vstream["width"]),
        height=int(vstream["height"]),
        fps=fps,
        has_audio=has_audio,
    )


if __name__ == "__main__":
    import sys

    info = probe(sys.argv[1])
    print(json.dumps(info.__dict__, ensure_ascii=False, indent=2))
