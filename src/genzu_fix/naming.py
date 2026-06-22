"""ファイル名の解析（名寄せ＝カット↔美術ボード対応の素材）。

検証で分かった構造:
- 原図ファイル名は「カット番号」で識別: shz_07_268_genzu / shz_07_091_101_116_genzu(複数) / shz_07_239B(枝番)
- 美術ボード名は「シーン番号＋場所＋時間＋天気＋改訂」で識別: SZ#2#3_南康群_街並_清書 / #6_花氏邸_全景（夜）_R2
  → 原図名とボード名は **直接は一致しない**（カット番号とシーン番号は別系統）。
  → 対応には「カット → シーン/場所/時間/天気」の索引（香盤表・絵コンテ由来）が必須。

このモジュールは、機械的に取れる範囲（ボード名の構造化・原図のカット番号抽出）を担う。
残るリンク（カット→シーン/場所/時間）は香盤表パーサで埋める。
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

# 時間帯（長い語を先に判定する）
_TIMES = ["明け方", "浅夕", "夕方", "夕", "朝", "昼", "夜"]
# 天気（長い語を先に）
_WEATHERS = ["霧あり", "霧なし", "雨", "霧"]


@dataclass
class BoardInfo:
    raw: str
    scene_tags: list[str] = field(default_factory=list)  # 例: ['SZ#2#3'] / ['#6'] / ['b01_07']
    place: str = ""                                       # 例: 南康群_街並
    time: str = ""                                        # 朝/昼/夕方/夜...
    weather: str = ""                                     # 雨/霧あり...
    revision: str = ""                                    # R1/R2


def _scene_tags(name: str) -> list[str]:
    tags = []
    # SZ#2#3 / SZ#6 / #6#7 / #6
    for m in re.finditer(r"SZ#\d+(?:#\d+)*|#\d+(?:#\d+)*", name):
        tags.append(m.group(0))
    # shz_b01_07 のような別系統キー
    for m in re.finditer(r"b0?\d+_\d+", name):
        tags.append(m.group(0))
    return tags


def parse_board(filename: str) -> BoardInfo:
    name = re.sub(r"\.(png|jpg|jpeg|psd)$", "", filename, flags=re.I)
    info = BoardInfo(raw=filename, scene_tags=_scene_tags(name))

    for t in _TIMES:
        if t in name:
            info.time = t
            break
    for w in _WEATHERS:
        if w in name:
            info.weather = w
            break
    m = re.search(r"R\d+", name)
    if m:
        info.revision = m.group(0)

    # place: タグ・時間・天気・改訂・定型語を除いた残り（best-effort）
    place = name
    for tok in info.scene_tags + [info.time, info.weather, info.revision,
                                  "清書", "全景", "_ver", "（", "）", "(", ")"]:
        if tok:
            place = place.replace(tok, " ")
    place = re.sub(r"[_\s]+", "_", place).strip("_ ")
    info.place = place
    return info


def parse_cut_codes(filename: str) -> dict:
    """原図ファイル名からエピソードとカット番号群を取り出す。
    例: shz_07_091_101_116_genzu -> {'work':'shz','ep':'07','cuts':['091','101','116']}
        shz_07_239B_genzu_BGonly -> cuts ['239B']
    複数番号は離散カットの束として返す（連番レンジ展開は香盤表規則で別途）。
    """
    name = re.sub(r"\.(png|jpg|jpeg|psd)$", "", filename, flags=re.I)
    m = re.match(r"([a-zA-Z]+)_(\d+)_(.+)", name)
    if not m:
        return {"work": "", "ep": "", "cuts": [], "raw": filename}
    work, ep, rest = m.group(1), m.group(2), m.group(3)
    # rest の先頭から続く「数字(+英字枝番)」トークンを集める
    cuts = re.findall(r"\d+[A-Za-z]?", rest.split("genzu")[0])
    return {"work": work, "ep": ep, "cuts": cuts, "raw": filename}


if __name__ == "__main__":
    import sys, json
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if "genzu" in line:
            print(json.dumps(parse_cut_codes(line), ensure_ascii=False))
        else:
            from dataclasses import asdict
            print(json.dumps(asdict(parse_board(line)), ensure_ascii=False))
