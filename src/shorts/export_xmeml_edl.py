"""モンタージュEDL（segments.json）→ 元マスター参照の FCP XML (xmeml v4)。

export_xmeml.py が「カット済みmp4を並べる」出力なのに対し、こちらは
**元動画1本への in/out タイムスタンプ**でシーケンスを組む。ユーザーのローカルに
あるマスターへリリンクすれば、切り貼り構造がそのまま Premiere で微調整できる。

- 映像トラック: cuts を順に配置（in/out=元動画フレーム）
- 音声トラック: audio_bed.parts を A1/A2 交互に配置し、クロスフェード分
  （crossfade 秒）だけ重ねて置く → そのまま音声クロスフェードを適用すれば
  自動組みと同じ尺になる。末尾のフェードアウトは編集側で
- シーケンス設定は元動画ネイティブ（例: 1920x1080 29.97fps）。縦持ち用の
  クロップ/リフレームは編集側の裁量に残す

使い方:
    python -m src.shorts.export_xmeml_edl MASTER.mp4 segments.json \
        -o edl.xml --name "キング牛丼" --source-name "天使ちゃん15話＿音割れ修正.mp4"

--source-name: XMLに書くファイル名（ユーザーのローカルのファイル名に合わせると
リリンクが自動で決まる。省略時はMASTERのbasename）
"""
from __future__ import annotations

import argparse
import json
import os
from fractions import Fraction
from xml.sax.saxutils import escape

from .probe import probe


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("master")
    ap.add_argument("segments")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--name", default="montage")
    ap.add_argument("--source-name", default=None)
    ap.add_argument("--segment-index", type=int, default=0)
    args = ap.parse_args()

    info = probe(args.master)
    fps = Fraction(info.fps) if hasattr(info, "fps") and info.fps else None
    if fps is None:
        import subprocess
        out = subprocess.check_output(
            ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
             "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", args.master])
        fps = Fraction(out.decode().strip())
    ntsc = fps.denominator != 1
    tb = round(float(fps))
    rate = f"<rate><timebase>{tb}</timebase><ntsc>{'TRUE' if ntsc else 'FALSE'}</ntsc></rate>"

    def fr(sec: float) -> int:
        return round(sec * float(fps))

    seg = json.load(open(args.segments))["segments"][args.segment_index]
    cuts = seg["cuts"]
    bed = seg.get("audio_bed") or {}
    parts = bed.get("parts") or ([{"start": bed["start"],
                                   "end": bed["start"] + sum(c["end"] - c["start"] for c in cuts)}]
                                 if "start" in bed else
                                 [{"start": c["start"], "end": c["end"]} for c in cuts])
    xf = float(bed.get("crossfade", 0.0)) if "parts" in bed else 0.0

    src_name = args.source_name or os.path.basename(args.master)
    total_src_frames = fr(info.duration)
    file_def = f"""<file id="file-1">
      <name>{escape(src_name)}</name>
      <pathurl>{escape(src_name)}</pathurl>
      {rate}
      <duration>{total_src_frames}</duration>
      <media>
        <video><samplecharacteristics>{rate}
          <width>{info.width}</width><height>{info.height}</height>
          <anamorphic>FALSE</anamorphic><pixelaspectratio>square</pixelaspectratio>
          <fielddominance>none</fielddominance>
        </samplecharacteristics></video>
        <audio><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate>
        </samplecharacteristics><channelcount>2</channelcount></audio>
      </media>
    </file>"""
    file_ref = '<file id="file-1"/>'

    # 映像トラック
    v_items, cur = [], 0
    for i, c in enumerate(cuts):
        i_f, o_f = fr(c["start"]), fr(c["end"])
        d = o_f - i_f
        v_items.append(f"""<clipitem id="clipitem-v-{i}">
      <name>cut{i+1} {escape(src_name)}</name><enabled>TRUE</enabled>
      <duration>{d}</duration>{rate}
      <start>{cur}</start><end>{cur + d}</end>
      <in>{i_f}</in><out>{o_f}</out>
      {file_def if i == 0 else file_ref}
      <sourcetrack><mediatype>video</mediatype><trackindex>1</trackindex></sourcetrack>
    </clipitem>""")
        cur += d
    total = cur

    # 音声: parts を A1/A2 交互、クロスフェード分だけ重ねて配置
    a_tracks: list[list[str]] = [[], []]
    acur = 0
    for i, p in enumerate(parts):
        i_f, o_f = fr(p["start"]), fr(p["end"])
        d = o_f - i_f
        start = max(0, acur - (fr(xf) if i > 0 else 0))
        tr = i % 2
        for ch in (1, 2):
            a_tracks[tr].append(f"""<clipitem id="clipitem-a-{i}-{ch}">
      <name>bed{i+1} {escape(src_name)}</name><enabled>TRUE</enabled>
      <duration>{d}</duration>{rate}
      <start>{start}</start><end>{start + d}</end>
      <in>{i_f}</in><out>{o_f}</out>
      {file_ref}
      <sourcetrack><mediatype>audio</mediatype><trackindex>{ch}</trackindex></sourcetrack>
    </clipitem>""" if ch == 1 else f"""<clipitem id="clipitem-a2-{i}-{ch}">
      <name>bed{i+1} {escape(src_name)}</name><enabled>TRUE</enabled>
      <duration>{d}</duration>{rate}
      <start>{start}</start><end>{start + d}</end>
      <in>{i_f}</in><out>{o_f}</out>
      {file_ref}
      <sourcetrack><mediatype>audio</mediatype><trackindex>{ch}</trackindex></sourcetrack>
    </clipitem>""")
        acur = start + d

    # A1/A2×ステレオ2ch → トラック4本（Premiereはstereoペアで解釈）
    audio_xml = ""
    for tr in (0, 1):
        ch1 = "\n".join(x for x in a_tracks[tr][0::2])
        ch2 = "\n".join(x for x in a_tracks[tr][1::2])
        audio_xml += f"<track>{ch1}</track><track>{ch2}</track>"

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
  <sequence id="sequence-1">
    <name>{escape(args.name)}</name>
    <duration>{total}</duration>
    {rate}
    <media>
      <video>
        <format><samplecharacteristics>{rate}
          <width>{info.width}</width><height>{info.height}</height>
          <anamorphic>FALSE</anamorphic><pixelaspectratio>square</pixelaspectratio>
          <fielddominance>none</fielddominance>
        </samplecharacteristics></format>
        <track>{''.join(v_items)}</track>
      </video>
      <audio>
        <numOutputChannels>2</numOutputChannels>
        <format><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate>
        </samplecharacteristics></format>
        {audio_xml}
      </audio>
    </media>
  </sequence>
</xmeml>
"""
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"{args.out}: video {len(cuts)}cuts {total}f ({total/float(fps):.1f}s) / "
          f"audio {len(parts)}parts (A1/A2交互・{xf}s重ね) @ {float(fps):.3f}fps "
          f"source={src_name}")


if __name__ == "__main__":
    main()
