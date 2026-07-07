"""香盤表(xlsx) → カット表。新話数の cut_board_map を自動生成する最後のピース。

ep7 実データ（尚善_色香盤表#07）の構造:
  ヘッダ行: CUT / 場所 / シーン色 / 備考
  行の例  : 001～002, 夜空, ,蛾おまかせ
            003～013, ,BANK,           ← バンク＝原図作業なし（スキップ・件数は報告）
            023～046, , ,c046…         ← 場所空欄＝直前の場所を継承
            207～239A / 239B～246      ← 枝番つきレンジ（239A で終わり 239B で始まる）
            290~292 / 290〜292          ← チルダの全半角ゆれ
            293～                       ← 終端開き（--last-cut で閉じる）
  ノイズ  : 「Bパート」行、CUT空欄の備考続き行、「色彩設計戻しカット」節（c117等の単票）、
            2枚目シート「シーン色」（キャラ色対応表）

xlsx の読み取りは標準ライブラリのみ（zip+XML）。openpyxl 不要＝作業マシンに追加installなし。
"""
from __future__ import annotations
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

_TILDES = "～〜~"
# レンジ:  <数字+枝番> ～ <数字+枝番>?   例) 001～002 / 239B～246 / 293～ / 047(単体)
_RANGE_RX = re.compile(
    rf"^\s*c?\s*(\d+)([A-Za-z]?)\s*(?:[{_TILDES}]\s*(?:c?\s*(\d+)([A-Za-z]?))?)?\s*$")


# ---------------------------------------------------------------------------
# xlsx リーダ（値のみ・標準ライブラリ）
# ---------------------------------------------------------------------------

def _iter_local(elem, name: str):
    """名前空間を無視してローカル名 name の要素を列挙（Element.iter は {*} 非対応のため）。"""
    for e in elem.iter():
        tag = e.tag
        if tag == name or (isinstance(tag, str) and tag.endswith("}" + name)):
            yield e


def _cell_col(ref: str) -> int:
    """'C12' -> 2（0始まり列番号）。"""
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return max(0, n - 1)


def read_xlsx(path: str) -> list[list[str]]:
    """全シートの行を順に返す（値のみ）。shared string / inline string / 数値に対応。"""
    rows: list[list[str]] = []
    with zipfile.ZipFile(path) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in _iter_local(root, "si"):
                shared.append("".join(t.text or "" for t in _iter_local(si, "t")))
        sheets = sorted(n for n in z.namelist()
                        if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        for sh in sheets:
            root = ET.fromstring(z.read(sh))
            for row in _iter_local(root, "row"):
                cells: dict[int, str] = {}
                for c in _iter_local(row, "c"):
                    ref = c.get("r") or ""
                    col = _cell_col(ref)
                    t = c.get("t")
                    if t == "inlineStr":
                        val = "".join(x.text or "" for x in _iter_local(c, "t"))
                    else:
                        v = next(iter(_iter_local(c, "v")), None)
                        val = v.text if (v is not None and v.text is not None) else ""
                        if t == "s" and val != "":
                            try:
                                val = shared[int(val)]
                            except (ValueError, IndexError):
                                pass
                    cells[col] = val
                if cells:
                    width = max(cells) + 1
                    rows.append([cells.get(i, "") for i in range(width)])
    return rows


# ---------------------------------------------------------------------------
# パース（行 → セグメント）と展開（セグメント → カット）
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    start: int
    start_sfx: str = ""
    end: int | None = None          # None = 単体 or 終端開き
    end_sfx: str = ""
    open_end: bool = False          # 「293～」のような終端開き
    place: str = ""
    color: str = ""                 # シーン色（BANK含む）
    note: str = ""
    bank: bool = False


# シーン色 → time の翻訳（長い語を先に）
_COLOR_TIME = [("よどんだ朝", "よどんだ朝"), ("明け方", "明け方"), ("夕方", "夕方"),
               ("朝", "朝"), ("昼", "昼"), ("夜", "夜"), ("夕", "夕方")]


def color_to_time(color: str) -> str:
    for k, t in _COLOR_TIME:
        if k in (color or ""):
            return t
    return ""


def parse_rows(rows: list[list[str]]) -> tuple[list[Segment], list[str]]:
    """香盤表の行からセグメント列を作る。戻り: (segments, warnings)。"""
    segs: list[Segment] = []
    warns: list[str] = []
    cur_place = ""
    stopped = False
    for r in rows:
        c0 = (r[0] if len(r) > 0 else "").strip()
        c1 = (r[1] if len(r) > 1 else "").strip()
        c2 = (r[2] if len(r) > 2 else "").strip()
        c3 = (r[3] if len(r) > 3 else "").strip()
        if "戻しカット" in c0 or "戻しカット" in c1:
            stopped = True     # 以降は色彩設計戻しの単票（カット定義ではない）
            continue
        if stopped:
            continue
        if not c0:
            # CUT空欄＝直前の備考の続き行
            if segs and c3:
                segs[-1].note = (segs[-1].note + " / " + c3).strip(" /")
            continue
        m = _RANGE_RX.match(c0)
        if not m:
            continue           # ヘッダ・Bパート・シーン色シート等
        start, ssfx, end, esfx = m.group(1), m.group(2), m.group(3), m.group(4)
        open_end = end is None and any(t in c0 for t in _TILDES)
        if c1:
            cur_place = c1
        bank = "bank" in c2.lower()
        segs.append(Segment(
            start=int(start), start_sfx=ssfx.upper(),
            end=(int(end) if end is not None else None), end_sfx=(esfx or "").upper(),
            open_end=open_end, place=cur_place, color=c2, note=c3, bank=bank))
    if not segs:
        warns.append("カット行が1件も見つかりませんでした（シート構造を確認）")
    return segs, warns


def expand(segs: list[Segment], last_cut: int | None = None) -> tuple[list[dict], list[str]]:
    """セグメントをカット単位に展開する。

    戻り: (cuts, warnings)。cuts の各要素:
      {cut, num, sfx, place, time, color, note, bank, range_label}
    枝番レンジ(207～239A / 239B～246)は、枝番が付いた端点のみ枝番付きカットになる。
    """
    out: list[dict] = []
    warns: list[str] = []
    for s in segs:
        rng = f"{s.start:03d}{s.start_sfx}"
        end = s.end
        if s.open_end:
            if last_cut is None:
                warns.append(f"{rng}～ が終端開き。--last-cut 未指定のため開始カットのみ出力")
                end = s.start
            else:
                end = last_cut
            rng += "～" + (f"{end:03d}" if s.end is None and last_cut else "")
        elif end is None:
            end = s.start
        else:
            rng += f"～{end:03d}{s.end_sfx}"
        if end < s.start:
            warns.append(f"レンジが逆順: {rng}（スキップ）")
            continue
        for n in range(s.start, end + 1):
            sfx = s.start_sfx if n == s.start else (s.end_sfx if n == end else "")
            out.append({
                "cut": f"{n}{sfx}", "num": n, "sfx": sfx,
                "place": s.place, "time": color_to_time(s.color), "color": s.color,
                "note": s.note, "bank": s.bank, "range_label": rng,
            })
    # 同一カットが複数セグメントに現れたら後勝ちで警告（239A/239B は別カットなので衝突しない）
    seen: dict[str, int] = {}
    dedup: list[dict] = []
    for c in out:
        if c["cut"] in seen:
            warns.append(f"カット {c['cut']} が複数レンジに出現（後の定義を採用）")
            dedup[seen[c["cut"]]] = c
        else:
            seen[c["cut"]] = len(dedup)
            dedup.append(c)
    return dedup, warns


def parse_koban_xlsx(path: str, last_cut: int | None = None) -> tuple[list[dict], list[str]]:
    """香盤表xlsx → カット一覧。戻り: (cuts, warnings)。"""
    segs, w1 = parse_rows(read_xlsx(path))
    cuts, w2 = expand(segs, last_cut=last_cut)
    return cuts, (w1 + w2)
