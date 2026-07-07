"""カット素材列から Premiere Pro 読み込み用の FCP XML (xmeml v4) シーケンスを生成する。

Premiere の「ファイル→読み込み」で .xml を開くと、カットが順に並んだ
シーケンス＋素材ビンが再現される（映像1トラック＋ステレオ音声）。
mp4 と同じフォルダに xml を置く前提（pathurl はファイル名相対。
見つからない場合も最初の1本をリリンクすれば残りは自動で解決される）。

使い方:
    python -m src.shorts.export_xmeml -o work/xxx/seq.xml \
        --name "床と一体化" work/xxx/cut1.mp4 work/xxx/cut2.mp4 ...

各カットの fps / 解像度 / 実尺は ffprobe で読む。fps が混在する場合は
最初のカットの fps をシーケンスに採用する（Premiere 側で補間）。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from fractions import Fraction
from xml.sax.saxutils import escape


def probe(path: str) -> dict:
    out = subprocess.check_output(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", path])
    info = json.loads(out)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    fps = Fraction(v["r_frame_rate"])
    return {
        "path": os.path.abspath(path),
        "name": os.path.basename(path),
        "width": int(v["width"]),
        "height": int(v["height"]),
        "fps": fps,
        "duration": float(info["format"]["duration"]),
        "has_audio": a is not None,
        "samplerate": int(a["sample_rate"]) if a else 48000,
        "channels": int(a.get("channels", 2)) if a else 2,
    }


def _rate_xml(timebase: int, ntsc: bool) -> str:
    return (f"<rate><timebase>{timebase}</timebase>"
            f"<ntsc>{'TRUE' if ntsc else 'FALSE'}</ntsc></rate>")


def _timebase(fps: Fraction) -> tuple[int, bool]:
    """23.976→(24,TRUE) / 29.97→(30,TRUE) / 24→(24,FALSE) 等の xmeml 表現。"""
    if fps.denominator == 1:
        return fps.numerator, False
    rounded = round(float(fps))
    return rounded, True


def build_xmeml(clips: list[dict], seq_name: str) -> str:
    tb, ntsc = _timebase(clips[0]["fps"])
    rate = _rate_xml(tb, ntsc)
    width, height = clips[0]["width"], clips[0]["height"]

    # 各クリップのフレーム数（シーケンスtimebase基準）とタイムライン位置
    pos = 0
    for i, c in enumerate(clips):
        c["frames"] = max(1, round(c["duration"] * tb))
        c["tl_start"] = pos
        c["tl_end"] = pos + c["frames"]
        c["file_id"] = f"file-{i + 1}"
        pos = c["tl_end"]
    total = pos

    def file_xml(c: dict, full: bool) -> str:
        if not full:  # 2回目以降は id 参照のみ（xmeml仕様）
            return f'<file id="{c["file_id"]}"/>'
        audio_part = ""
        if c["has_audio"]:
            audio_part = (
                "<audio><samplecharacteristics><depth>16</depth>"
                f"<samplerate>{c['samplerate']}</samplerate>"
                "</samplecharacteristics>"
                f"<channelcount>{c['channels']}</channelcount></audio>")
        return f"""<file id="{c['file_id']}">
      <name>{escape(c['name'])}</name>
      <pathurl>{escape(c['name'])}</pathurl>
      {rate}
      <duration>{c['frames']}</duration>
      <media>
        <video><samplecharacteristics>{rate}
          <width>{c['width']}</width><height>{c['height']}</height>
          <anamorphic>FALSE</anamorphic>
          <pixelaspectratio>square</pixelaspectratio>
          <fielddominance>none</fielddominance>
        </samplecharacteristics></video>
        {audio_part}
      </media>
    </file>"""

    def clipitem(c: dict, idx: int, kind: str, channel: int = 1) -> str:
        cid = f"clipitem-{kind}-{idx}-{channel}"
        src = ("<sourcetrack><mediatype>audio</mediatype>"
               f"<trackindex>{channel}</trackindex></sourcetrack>"
               if kind == "a" else
               "<sourcetrack><mediatype>video</mediatype>"
               "<trackindex>1</trackindex></sourcetrack>")
        # file 全定義は最初に登場する clipitem（映像側）でのみ行う
        full = kind == "v"
        return f"""<clipitem id="{cid}">
      <name>{escape(c['name'])}</name>
      <enabled>TRUE</enabled>
      <duration>{c['frames']}</duration>
      {rate}
      <start>{c['tl_start']}</start><end>{c['tl_end']}</end>
      <in>0</in><out>{c['frames']}</out>
      {file_xml(c, full)}
      {src}
    </clipitem>"""

    video_items = "\n".join(clipitem(c, i, "v") for i, c in enumerate(clips))
    audio_tracks = ""
    if any(c["has_audio"] for c in clips):
        ch1 = "\n".join(clipitem(c, i, "a", 1)
                        for i, c in enumerate(clips) if c["has_audio"])
        ch2 = "\n".join(clipitem(c, i, "a", 2)
                        for i, c in enumerate(clips)
                        if c["has_audio"] and c["channels"] >= 2)
        audio_tracks = f"<track>{ch1}</track>"
        if ch2:
            audio_tracks += f"<track>{ch2}</track>"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
  <sequence id="sequence-1">
    <name>{escape(seq_name)}</name>
    <duration>{total}</duration>
    {rate}
    <media>
      <video>
        <format><samplecharacteristics>{rate}
          <width>{width}</width><height>{height}</height>
          <anamorphic>FALSE</anamorphic>
          <pixelaspectratio>square</pixelaspectratio>
          <fielddominance>none</fielddominance>
        </samplecharacteristics></format>
        <track>{video_items}</track>
      </video>
      <audio>
        <numOutputChannels>2</numOutputChannels>
        <format><samplecharacteristics><depth>16</depth>
          <samplerate>{clips[0]['samplerate']}</samplerate>
        </samplecharacteristics></format>
        {audio_tracks}
      </audio>
    </media>
  </sequence>
</xmeml>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("clips", nargs="+", help="カットmp4（並べたい順）")
    ap.add_argument("-o", "--out", required=True, help="出力 .xml パス")
    ap.add_argument("--name", default="sequence", help="シーケンス名")
    args = ap.parse_args()

    clips = [probe(p) for p in args.clips]
    xml = build_xmeml(clips, args.name)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(xml)
    total = sum(c["duration"] for c in clips)
    print(f"{args.out}: {len(clips)} cuts, {total:.1f}s, "
          f"{clips[0]['width']}x{clips[0]['height']} @{float(clips[0]['fps']):.3f}fps")


if __name__ == "__main__":
    main()
