"""絵コンテ（手描き/スキャンPDF）から、カット別の situation / remove を抽出する（④）。

設計（design-notes §19 / prompt-design.md §6）:
  ep7 コンテはテキスト層の無い純スキャンで OCR 不可。よって
    PDF → ページ画像化(PyMuPDF) → Vision(Claude)でコマ別に構造化 → cut_scene_info へマージ
  の流れで「カット→場面(situation)・除去対象(remove)」を埋める。

このモジュールは3工程に分かれ、各工程を個別に実行できる（途中再開・人手レビュー可）:
  1. render  : PDF の指定ページ範囲を PNG 化（ローカルにコンテ実物が要る）
  2. extract : ページPNGを Claude Vision に渡し、コマ別 JSON を runs/conte_frames_ep7.json へ
  3. merge   : frames JSON を cut_scene_info_ep7.csv の situation/remove へ反映

Vision を使わず人手で埋める場合は render だけ実行し、出力CSVテンプレ(_template.csv)を手書きでも良い。

依存: PyMuPDF（render）, 標準ライブラリのみで Anthropic REST を叩く（extract）。
環境変数: ANTHROPIC_API_KEY（extract）。
"""
from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request

# Vision 既定モデル（手描き日本語の読みに強い順で opus を既定に）
DEFAULT_MODEL = "claude-opus-4-8"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
# ep7 DANGUN コンテ用紙の列境界比率（pic|act, act|dia, dia|time）。
# 本編ページのオーバーレイで目視確認済み（表紙=表なしは cuts:[] になるので無関係）。
EP7_COLS = "0.50,0.70,0.90"

# 抽出の指示（コンテのコマ枠 No./scene/picture/action/dialogue/time を読む）。
# 背景美術の原図修正が目的なので、出力は「背景に何が要るか(situation)」と
# 「画面内のキャラ＋付随物(remove)」に寄せる。qc.py の除去基準と一致させる。
EXTRACTION_PROMPT = """\
あなたは日本の商業アニメの絵コンテを読む専門家です。渡された画像は手描き/スキャンの
絵コンテ1ページで、複数のコマ（カット）が縦に並びます。各コマには No.（カット番号）、
scene（場所/時間の注記）、picture（描かれた絵）、action（ト書き）、dialogue（セリフ）、
time（尺）の欄があります。手描き文字は崩れています。読めない箇所は推測せず空文字にしてください。

このページに写る各コマについて、次を抽出してJSONで返してください。背景美術の「原図修正」が
目的なので、背景に必要な情報と、画面内の人物・付随物（＝背景から消す対象）を分けて捉えること。

- cut_label: No.欄に印字されたカット番号を文字列で（例 "15", "16", "16A"）。読めなければ ""。
- scene_label: scene欄の場所/時間の注記（例 "夜/復活の儀の部屋"）。無ければ ""。
- time_label: 時間帯が分かれば（朝/昼/夕方/夜/明け方 等）。無ければ ""。
- action: action欄の要約（読めた範囲、日本語）。
- dialogue: dialogue欄の要約（読めた範囲、日本語）。
- characters: 画面内に居る人物・動物・その人が持つ/着る/連れた物（＝背景から消す対象）。日本語リスト。
- characters_en: characters の英訳リスト（同じ順・同じ数。背景生成プロンプトに入れる用）。
- background_elements: その場所に在る環境物（祭壇/柱/寝台/燭台/窓/扉/塀/樹木 等＝残す背景）。日本語リスト。
- situation: 「この背景に何が要るか・何が起きているか」を1〜2文（日本語）。背景再構成の根拠。
- situation_en: situation の英訳（簡潔に。背景生成プロンプトに入れる用）。
- confidence: "high" / "medium" / "low"（手描きの読み取り自信度）。

英訳（*_en）は固有名や時代様式を保った簡潔な英語にすること（背景美術の指示文として使う）。
出力は次の形の JSON のみ（前後に説明文を付けない）:
{"frames": [{"cut_label": "...", "scene_label": "...", "time_label": "...",
  "action": "...", "dialogue": "...",
  "characters": ["..."], "characters_en": ["..."],
  "background_elements": ["..."], "situation": "...", "situation_en": "...",
  "confidence": "..."}]}
このページにコマが無い（表紙/扉/白紙）場合は {"frames": []} を返す。\
"""


# ---------------------------------------------------------------------------
# 1. render : PDF → ページPNG
# ---------------------------------------------------------------------------
def render(pdf_path: str, out_dir: str, dpi: int = 200,
           first: int | None = None, last: int | None = None) -> list[str]:
    """PDF の [first, last]（1始まり・両端含む）ページを PNG 化して保存。パス一覧を返す。"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("PyMuPDF が必要です: pip install pymupdf")
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    n = doc.page_count
    f = (first or 1) - 1
    l = (last or n)
    paths = []
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    for i in range(max(0, f), min(n, l)):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=mat)
        p = os.path.join(out_dir, f"page_{i + 1:03d}.png")
        pix.save(p)
        paths.append(p)
    print(f"rendered {len(paths)} pages -> {out_dir}")
    return paths


# ---------------------------------------------------------------------------
# 2. extract : ページPNG → Claude Vision → frames
# ---------------------------------------------------------------------------
def _vision_extract_page(image_path: str, model: str, api_key: str,
                         max_tokens: int = 4096) -> list[dict]:
    """1ページを Claude Vision に渡し frames リストを返す。"""
    with open(image_path, "rb") as fh:
        b64 = base64.standard_b64encode(fh.read()).decode("ascii")
    media = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": media, "data": b64}},
                {"type": "text", "text": EXTRACTION_PROMPT},
            ],
        }],
    }
    req = urllib.request.Request(
        ANTHROPIC_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return parse_frames(text)


def parse_frames(text: str) -> list[dict]:
    """Vision 応答テキストから frames 配列を取り出す（前後の説明文に頑健）。"""
    # ```json ... ``` フェンスを剥がす
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    raw = m.group(1) if m else text
    # 最初の { から対応する } までを拾う
    start = raw.find("{")
    if start < 0:
        return []
    depth, end = 0, None
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        return []
    try:
        obj = json.loads(raw[start:end])
    except json.JSONDecodeError:
        return []
    return obj.get("frames", []) if isinstance(obj, dict) else []


def extract(image_paths: list[str], out_json: str, model: str = DEFAULT_MODEL,
            api_key: str | None = None) -> list[dict]:
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY が未設定です。")
    all_frames = []
    for p in image_paths:
        try:
            frames = _vision_extract_page(p, model, api_key)
        except Exception as e:  # 1ページ失敗で全体を止めない
            print(f"    ! {os.path.basename(p)}: 抽出失敗 {e}")
            frames = []
        for fr in frames:
            fr["_page"] = os.path.basename(p)
        all_frames.extend(frames)
        print(f"    {os.path.basename(p)}: {len(frames)} frames")
    os.makedirs(os.path.dirname(out_json) or ".", exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"frames": all_frames}, f, ensure_ascii=False, indent=2)
    print(f"wrote {out_json}: {len(all_frames)} frames")
    return all_frames


# ---------------------------------------------------------------------------
# 3. merge : frames → cut_scene_info_ep7.csv の situation/remove
# ---------------------------------------------------------------------------
def _cut_key(label) -> str:
    """カット番号の正規化キー（前ゼロを落とす。枝番は保持）。例 '015'->'15', '016A'->'16A'。
    モデルが int で返す場合があるため文字列化に頑健にする。"""
    s = ("" if label is None else str(label)).strip()
    m = re.match(r"0*(\d+)([A-Za-z]?)$", s)
    return (m.group(1) + m.group(2).upper()) if m else s


def _cut_num(label):
    """カット番号の整数部（連番引き継ぎ用）。'259B'->259, 'title'->None。int/None でも可。"""
    m = re.match(r"\s*0*(\d+)", "" if label is None else str(label))
    return int(m.group(1)) if m else None


def merge(frames: list[dict], cut_info_csv: str, out_csv: str | None = None,
          overwrite: bool = False) -> dict:
    """frames を cut 番号で突き合わせ、cut_info_csv の situation/remove を埋める。
    既存値は overwrite=False なら温存。マッチ統計を返す。"""
    out_csv = out_csv or cut_info_csv
    # frames を cut_key でまとめる（同一カットが複数コマに跨る場合は連結）
    by_cut: dict[str, list[dict]] = {}
    for fr in frames:
        k = _cut_key(fr.get("cut_label", ""))
        if k:
            by_cut.setdefault(k, []).append(fr)

    with open(cut_info_csv, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys()) if rows else []

    matched, filled = 0, 0
    used_keys = set()
    for r in rows:
        k = _cut_key(r.get("cut", ""))
        frs = by_cut.get(k)
        if not frs:
            continue
        matched += 1
        used_keys.add(k)
        situation = " / ".join(s for s in (fr.get("situation", "").strip() for fr in frs) if s)
        situation_en = " / ".join(s for s in (fr.get("situation_en", "").strip() for fr in frs) if s)

        def _uniq(key):
            seen2 = []
            for fr in frs:
                for c in fr.get(key, []) or []:
                    if c and c not in seen2:
                        seen2.append(c)
            return seen2
        remove = "、".join(_uniq("characters"))
        remove_en = ", ".join(_uniq("characters_en"))

        def _set(col, val):
            if val and col in fields and (overwrite or not r.get(col)):
                r[col] = val
        if situation and (overwrite or not r.get("situation")):
            filled += 1
        _set("situation", situation)
        _set("situation_en", situation_en)
        _set("remove", remove)
        _set("remove_en", remove_en)

    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    unmatched_frames = sorted(set(by_cut) - used_keys)
    stat = {"cuts_total": len(rows), "cuts_matched": matched, "cuts_filled": filled,
            "frame_cuts_unmatched": unmatched_frames}
    print(f"merge -> {out_csv}: {matched}/{len(rows)} cuts matched, "
          f"{filled} situation filled")
    if unmatched_frames:
        print(f"  ! frames にあるが CSV に無いカット番号: {', '.join(unmatched_frames)}")
        print("    （コンテのNo.採番がパート別オフセット等でCSVカット番号とズレている可能性。要確認）")
    return stat


# ---------------------------------------------------------------------------
# 3.5 extract2 : コマ単位・高解像度・用語集注入のOCR（精度版）
#   旧 extract はページ丸ごと低解像度で読むため手書きが潰れた。表の罫線を検出して
#   1カット＝1リクエストで「左=scene番号+picture / 右=action+dialogue+time」を大きく送る。
#   登場人物・絵コンテ用語（runs/conte_glossary_ep7.md）をプロンプトに差し込み誤読を抑える。
# ---------------------------------------------------------------------------
GLOSSARY_MD = "runs/conte_glossary_ep7.md"


def load_glossary(path: str = GLOSSARY_MD) -> str:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return "（用語集なし）"


def _cluster(idxs, gap: int = 6):
    """連続/近接インデックスを束ね、各クラスタの中心を返す。"""
    out = []
    if len(idxs) == 0:
        return out
    s = p = idxs[0]
    for x in idxs[1:]:
        if x - p > gap:
            out.append((s + p) // 2)
            s = x
        p = x
    out.append((s + p) // 2)
    return out


def detect_grid(gray, row_thresh: float = 0.35, col_thresh: float = 0.30,
                min_band_frac: float = 0.04, cols_override=None):
    """グレースケール配列から、行バンド[(y0,y1)] と列境界(0..1) を返す。
    返り値 (bands, split, cols)：
      split = picture|action 境界（後方互換のため単独でも返す）
      cols  = {"pic_act":~0.50, "act_dia":~0.70, "dia_time":~0.90} 各列の縦境界(0..1)。
              用紙の縦罫線から拾い、拾えない時のみ DANGUN 標準比率にフォールバック。
      cols_override=[pic_act, act_dia, dia_time] を渡すと検出せずその比率で固定する
      （フォームは全ページ同一なので、一度目視で合わせたら固定するのが確実）。"""
    import numpy as np
    a = np.asarray(gray)
    h, w = a.shape
    dark = (a < 128).astype(np.float32)
    hlines = _cluster(np.where(dark.mean(axis=1) > row_thresh)[0])
    bands = [(hlines[i], hlines[i + 1]) for i in range(len(hlines) - 1)
             if hlines[i + 1] - hlines[i] > h * min_band_frac]
    if cols_override:
        pa, ad, dt = cols_override
        # scene(番号)|picture 境界は固定指定に含めず常に検出（無ければ0.10）。番号欄の切り出し用。
        vl = _cluster(np.where(((np.asarray(gray) < 128).astype(np.float32)).mean(axis=0) > col_thresh)[0])
        sp = 0.10
        if vl:
            cx = min(vl, key=lambda x: abs(x - 0.10 * w))
            if 0.05 * w < cx < 0.18 * w:
                sp = cx / w
        return bands, pa, {"scene_pic": sp, "pic_act": pa, "act_dia": ad, "dia_time": dt, "_src": "override"}
    vlines = _cluster(np.where(dark.mean(axis=0) > col_thresh)[0])

    def nearest(ratio, lo, hi, default):
        """ratio*w に最も近い縦罫線を [lo,hi]*w の範囲で拾う。無ければ default。"""
        if vlines:
            cx = min(vlines, key=lambda x: abs(x - ratio * w))
            if lo * w < cx < hi * w:
                return cx / w
        return default

    split = nearest(0.50, 0.35, 0.65, 0.50)                  # picture|action
    cols = {
        "scene_pic": nearest(0.10, 0.05, 0.18, 0.10),        # scene(番号)|picture
        "pic_act": split,
        "act_dia": nearest(0.70, 0.60, 0.80, 0.70),          # action|dialogue
        "dia_time": nearest(0.90, 0.82, 0.97, 0.90),         # dialogue|time
        "_src": "auto", "_nvlines": len(vlines),
    }
    return bands, split, cols


def _crop_b64(img, box, min_w: int = 1100, max_edge: int = 1568):
    """PIL画像を box=(l,t,r,b) で切り PNG base64 を返す。
    小さければ拡大して可読性確保。ただし長辺は max_edge(=Anthropic推奨上限)で頭打ち
    （巨大画像によるAPI 400/トークン浪費を防ぐ）。"""
    c = img.crop(box).convert("RGB")
    if c.width < min_w:                                   # 可読性のため最低幅まで拡大
        s = min_w / max(c.width, 1)
        c = c.resize((max(int(c.width * s), 1), max(int(c.height * s), 1)))
    longest = max(c.width, c.height)
    if longest > max_edge:                                # 大きすぎる場合は長辺を上限に縮小
        s = max_edge / longest
        c = c.resize((max(int(c.width * s), 1), max(int(c.height * s), 1)))
    buf = io.BytesIO()
    c.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii"), c


def _extraction_prompt_page(glossary: str) -> str:
    return (
        "あなたは日本の商業アニメ絵コンテを読む専門家です。これから**1ページ分**を渡します。\n"
        "1枚目=『ページ上部ヘッダ』(左上の『No.◯』=用紙通し番号 と 表頭 scene/picture/action/dialogue/time)。\n"
        "2枚目以降=各コマを上から順に**列ごとに5枚**渡す: \n"
        "  「scene番号欄」= そのコマの**カット番号（丸囲み数字）か、縦棒｜か、空白**だけが入った画像、\n"
        "  「picture(絵)」= 絵だけが入った画像、\n"
        "  「action欄」= ト書き(動き・カメラ指示)だけが入った画像、\n"
        "  「dialogue欄(セリフのみ)」= セリフだけが入った画像、\n"
        "  「time欄」= 尺だけが入った画像。\n"
        "**各画像はその列の中身だけを抜き出してある。ラベルの列以外の内容を絶対に混ぜない**"
        "(例: 『action欄』画像の文字を dialogue に入れない。『dialogue欄』にはセリフ以外を入れない)。\n\n"
        "【ページ種別の判定（最初に行う）】\n"
        "・ヘッダに『No.◯』と表頭(scene/picture/action/...)があれば**絵コンテ本編ページ**＝カットを読む。\n"
        "・『No.』も表頭も無いページ(タイトルカード/計算メモ/前付け)は**カットでない → cuts:[] を返す**。\n\n"
        "このページに含まれる全カットを、上から順に JSON 配列で返してください。\n"
        "【最重要・番号ずれ防止（scene番号欄の画像だけで番号を判定する）】\n"
        "・**新カットの境目は scene番号欄に番号が書かれているか否か、それだけで決める**。"
        "番号があれば新カット、無ければ直前カットの続き。"
        "**絵や動きが変わった/別の芝居に見える等の“内容”で勝手に新カットを起こさない**。"
        "(例: 番号の無いコマに『鱗粉が舞う』等の新しいト書きがあっても、それは直前カットの続き)。\n"
        "・各コマの **scene番号欄** 画像を見て、次の3通りに**必ず分類**する:\n"
        "  (1) **丸囲み数字**(①②③ / 丸で囲まれた 1,2,3…)がある → これが**そのカットの番号**。"
        "**読めた数字をそのまま cut_label にする**。自分の走る連番(直前+1)で上書きしない。\n"
        "  (2) **縦棒『｜』だけ**(丸囲み数字なし) → **直前カットの続き(同一カット)**。numbered=false。"
        "新しい番号を振らず、本文(action/dialogue/time)を直前カットに統合する。縦棒を数字『1』と読み間違えない。\n"
        "  (3) **空白**(番号も縦棒もない) → 直前カットの続き。numbered=false。\n"
        "・各カットに **scene_mark** を付ける: 丸囲み数字なら読めた数字の文字列(例『2』)、縦棒なら『｜』、空白なら空。\n"
        "・各カットに **numbered** を付ける: scene番号欄に丸囲み数字があれば true、縦棒/空白なら false。\n"
        "・**ページ最初のコマが縦棒/空白(丸番号なし)なら numbered=false**＝前ページ最後のカットの続き(新番号にしない)。\n"
        "・**番号は『丸囲み数字を読む』のが第一。連番は数字が読めない時の補完にだけ使う**。"
        "丸囲み②が見えているのに走る連番を優先して『3』等にしてはいけない(縦棒コマを1カットと誤算した時に起きる典型ミス)。\n"
        "・丸で囲まれた数字だけが本物のカット番号。1カットが複数コマに跨ることがある。\n"
        "・**1カットが複数コマに跨る場合は、本文(action/dialogue/time)を結合して1エントリにまとめる**。"
        "同じカット番号で複数のエントリを作らない。\n"
        "・カット番号と本文が隣り合うコマにまたがる場合も、レイアウトと連番性から正しく1つにまとめる。\n"
        "・番号が読めないコマは、前後のカット番号の連番から補ってよい(その旨 notes に記す)。\n"
        "・番号も本文も無い空コマ(リード/つなぎ/白紙)は出力に含めない。\n"
        "・**タイトルカード/計算メモ(○○cut+△△cut 等の集計)/前付けなどカットでないページは cuts を空配列[]で返す**。\n"
        "・手書きは崩れている。推測で埋めず、確信の範囲を書き、不確実は confidence を下げ notes に書く。\n"
        "・**人名・固有名は書かれた字を忠実に読む**。glossaryは(a)実在しない誤読名を実在名に正す/(b)表記ゆれ統一 "
        "にのみ使い、**書かれていない名前を補ったり、短い手書きを長い正式名に“拡張”したりしない**。\n"
        "・**字数・字形が合う候補だけ採用**する(例: 3文字の手書きに6文字の名を当てない)。合わなければ書かれたまま、"
        "または空にして notes に『要確認』と記す。場面(場所・時代)に合わない人物名は選ばない。\n\n"
        "【文脈＝誤読防止に必ず使う】\n" + glossary + "\n\n"
        "出力(前後に説明文を付けない、JSONのみ):\n"
        '{"cuts":[{"cut_label":"カット番号(整数)。**続き(縦棒/番号なし)のコマに枝番を振らず直前カットに統合**。'
        '英字枝番(259B等)は用紙に明示的に英字が描かれた差し込みカットのときだけ。補完したら notes に明記",'
        '"action":"action欄(ト書き=動き/カメラ指示)。カメラ用語は上の正規形に寄せる。'
        'action欄画像の文字はすべて action に入れ、dialogue へ移さない",'
        '"dialogue":"dialogue欄=**登場人物が発する話し言葉(セリフ)だけ**。'
        'M(モノローグ)/ナレーションはセリフ扱い。'
        'OK/A.P./承認印・サイン・演出メモ・ト書き・効果音はセリフではない→dialogueに入れない(空でよい)",'
        '"se":"効果音があれば",'
        '"time":"time欄。秒+コマ表記(例 4+12)。分数読みは誤り",'
        '"scene_mark":"scene番号欄の見たまま: 丸囲み数字なら数字(例『2』)、縦棒なら『｜』、空白なら空",'
        '"numbered":"丸囲みのカット番号が実際に描かれていれば true、続きコマ(縦棒/番号なし)なら false",'
        '"characters":["本文に書かれた人名を忠実に。実在しない誤読名のみ実在名に正す(例 芦龍→芦花)。'
        '書かれた字数字形に合わない名前を当てず、短い名を長い正式名に拡張しない。曖昧は空+notesに要確認"],'
        '"confidence":"high|medium|low","notes":"不確実箇所/番号補完/保留"}]}'
    )


def _vision_page(crops: list[tuple], prompt: str, model: str, api_key: str,
                 max_tokens: int = 8192) -> list[dict]:
    """crops=[(label, b64), ...] を順に並べ、ページ全体を1リクエストでOCR。cuts配列を返す。"""
    import time as _time
    content = []
    for label, b64 in crops:
        content.append({"type": "text", "text": f"【{label}】"})
        content.append({"type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": b64}})
    content.append({"type": "text", "text": prompt})
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}]}
    payload = json.dumps(body).encode("utf-8")
    nb = len(crops)
    print(f"    [api] 画像{nb}枚 / 送信 {len(payload)/1_048_576:.1f}MB", flush=True)
    # 画像点数の上限(Anthropic=100枚/リクエスト)を超えていれば、原因を明示して早期に止める
    if nb > 100:
        raise RuntimeError(f"画像が{nb}枚で上限(100枚/リクエスト)超過。コマ数が多すぎる可能性。"
                           "列分割で 1コマ=5枚のため、約20コマ超で超える。ページ分割が必要。")
    for attempt in range(4):
        req = urllib.request.Request(
            ANTHROPIC_URL, data=payload,
            headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION,
                     "content-type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", "replace")
            # 400(リクエスト不正)は再試行しても無駄＝中身を見せて即停止
            if e.code in (429, 500, 502, 503, 529) and attempt < 3:
                wait = 2 ** (attempt + 1)
                print(f"    [api] HTTP {e.code} 再試行 {attempt+1}/3（{wait}s後）", flush=True)
                _time.sleep(wait)
                continue
            raise RuntimeError(f"Anthropic API HTTP {e.code}: {err[:1000]}") from None
        except urllib.error.URLError as e:
            if attempt < 3:
                wait = 2 ** (attempt + 1)
                print(f"    [api] 通信失敗 {e.reason} 再試行 {attempt+1}/3（{wait}s後）", flush=True)
                _time.sleep(wait)
                continue
            raise
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    stop = data.get("stop_reason", "")
    if stop == "max_tokens":
        print(f"    [api] !! 応答が max_tokens({max_tokens})で打ち切られJSONが壊れた可能性。"
              "max_tokensを上げる必要あり。", flush=True)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        print(f"    [api] !! 応答にJSONが見つからない（stop={stop}）。モデル応答の冒頭:\n"
              f"        {text[:400]!r}", flush=True)
        return []
    try:
        cuts = json.loads(m.group(0)).get("cuts", [])
        if not cuts:
            print(f"    [api] !! cuts=空（stop={stop}）。モデル応答の冒頭:\n        {text[:400]!r}",
                  flush=True)
        return cuts
    except json.JSONDecodeError as e:
        print(f"    [api] !! JSON解析失敗({e}, stop={stop})。応答の冒頭:\n        {text[:400]!r}",
              flush=True)
        return []


def _attach_continuations(frames: list[dict]) -> list[dict]:
    """決定的な番号付け: numbered=false(丸番号が描かれていない続きコマ)を直前カットへ統合する。
    これでページまたぎの続きが必ず直前カットにつながる（モデルの番号推測に依存しない）。
    numbered キーが無い旧データは cut_label の有無で判定（後方互換）。"""
    rank = {"high": 3, "medium": 2, "low": 1, "": 1}
    out: list[dict] = []
    for fr in frames:
        nb = fr.get("numbered")
        if nb is None:
            has_num = _cut_num(fr.get("cut_label")) is not None
        else:
            has_num = bool(nb) and _cut_num(fr.get("cut_label")) is not None
        if has_num or not out:
            out.append(fr)
            continue
        prev = out[-1]  # 続きコマ → 直前カットへ統合
        for k in ("action", "dialogue", "se", "time"):
            a, b = (prev.get(k) or "").strip(), (fr.get(k) or "").strip()
            if b and b not in a:
                prev[k] = (a + " / " + b) if a else b
        pc = prev.get("characters") or []
        for c in fr.get("characters") or []:
            if c and c not in pc:
                pc.append(c)
        prev["characters"] = pc
        if fr.get("notes"):
            prev["notes"] = ((prev.get("notes", "") + " ｜ " + fr["notes"]).strip(" ｜"))
        if rank.get((fr.get("confidence") or "").lower(), 1) < rank.get((prev.get("confidence") or "").lower(), 3):
            prev["confidence"] = (fr.get("confidence") or "").lower()
    return out


def extract2(page_paths: list[str], out_json: str = "runs/conte_frames_v2_ep7.json",
             model: str = DEFAULT_MODEL, api_key: str | None = None,
             glossary_path: str = GLOSSARY_MD, debug_crops: str | None = None,
             cols_override=None) -> list[dict]:
    """ページPNG群を、表の行検出→列ごと(番号+絵/action/dialogue/time)に切り出し→用語集付きOCR で読む。
    フィールドは「文字がどの列にあるか」で機械的に決まる（モデルに割り当てを選ばせない）。
    debug_crops を指定すると API を叩かず、各列クロップ＋列境界オーバーレイを保存して切り出しを目視確認できる。
    cols_override=[pic_act, act_dia, dia_time]（0..1）で列境界を固定できる。"""
    from PIL import Image, ImageDraw
    if not debug_crops:
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY が未設定です。")
        api_key = api_key.strip().strip('"').strip("'")  # 引用符の付け間違いを許容
        if not api_key.isascii():
            raise RuntimeError(
                "ANTHROPIC_API_KEY に非ASCII文字が含まれています。プレースホルダ（例『（あなたの鍵）』）を"
                "そのまま設定していませんか？ 本物の鍵（sk-ant-… のASCII文字列）を "
                "`set ANTHROPIC_API_KEY=sk-ant-...` で設定してください。")
    glossary = load_glossary(glossary_path)
    prompt = _extraction_prompt_page(glossary)
    # 正規の枝番カット一覧を cut_board_map から注入＝枝番の位置をモデルに教える(捏造防止/読み落とし防止)
    ref = "runs/cut_board_map_ep7.csv"
    if os.path.exists(ref):
        with open(ref, encoding="utf-8-sig") as rf:
            br = sorted({_cut_key(r.get("cut", "")) for r in csv.DictReader(rf)
                         if re.search(r"[A-Za-z]$", _cut_key(r.get("cut", "")))},
                        key=lambda x: (int(re.match(r"\d+", x).group()), x))
        if br:
            prompt += ("\n【このエピソードに実在する枝番カット】" + " / ".join(br) +
                       "。**これらの位置では用紙の丸番号の英字(A/B)を必ず読む**。"
                       "リストに無いコマに枝番を振らない（続きは直前カットに統合）。")
    all_frames = []
    last_cut = 0  # 前ページまでの最後のカット番号（連番をページ越しに引き継ぐ）
    for pp in page_paths:
        img = Image.open(pp)
        bands, split, cols = detect_grid(img.convert("L"), cols_override=cols_override)
        spx = int(cols.get("scene_pic", 0.10) * img.width)   # scene(番号)|picture
        sx = int(cols["pic_act"] * img.width)    # picture|action
        ax = int(cols["act_dia"] * img.width)    # action|dialogue
        dx = int(cols["dia_time"] * img.width)   # dialogue|time
        print(f"  {os.path.basename(pp)}: {len(bands)}コマ検出 列境界[{cols.get('_src','auto')}] "
              f"scene|pic={cols.get('scene_pic',0.10):.3f} pic|act={cols['pic_act']:.3f} "
              f"act|dia={cols['act_dia']:.3f} dia|time={cols['dia_time']:.3f}")
        if debug_crops:
            # 列境界をページ全体に重ね描き＝切り位置を一目で検証できる（API前に確認する核心）
            d0 = os.path.join(debug_crops, os.path.splitext(os.path.basename(pp))[0])
            os.makedirs(d0, exist_ok=True)
            ov = img.convert("RGB").copy()
            dr = ImageDraw.Draw(ov)
            lw = max(8, img.width // 250)  # 高解像度でも見えるよう太め
            for x, c in ((spx, (255, 140, 0)), (sx, (255, 0, 0)), (ax, (0, 160, 0)), (dx, (0, 0, 255))):
                dr.line([(x, 0), (x, img.height)], fill=c, width=lw)
            ovp = os.path.join(d0, "_columns_overlay.png")
            ov.save(ovp)
            print(f"    [overlay] {ovp}  橙=scene|pic({spx}px) 赤=pic|act({sx}px) "
                  f"緑=act|dia({ax}px) 青=dia|time({dx}px)")
        crops = []  # ページ全コマを順に並べて1リクエストで関連付けさせる
        # 1枚目=ページ上部ヘッダ（No.◯ と 表頭）。前付けページの判定に使う。
        hdr_y = bands[0][0] if bands else int(img.height * 0.10)
        hb, hc = _crop_b64(img, (0, 0, img.width, max(hdr_y, 1)))
        if debug_crops:
            d0 = os.path.join(debug_crops, os.path.splitext(os.path.basename(pp))[0])
            os.makedirs(d0, exist_ok=True)
            hc.save(os.path.join(d0, "header.png"))
        else:
            crops.append(("ページ上部ヘッダ(No.と表頭)", hb))
        for i, (y0, y1) in enumerate(bands):
            nb, nc = _crop_b64(img, (0, y0, spx, y1))            # scene番号欄のみ(丸数字 or 縦棒)
            pb, pc = _crop_b64(img, (spx, y0, sx, y1))           # picture(絵)のみ
            ab, ac = _crop_b64(img, (sx, y0, ax, y1))            # action欄のみ
            db, dc = _crop_b64(img, (ax, y0, dx, y1))            # dialogue欄のみ
            tb, tc = _crop_b64(img, (dx, y0, img.width, y1))     # time欄のみ
            if debug_crops:
                d = os.path.join(debug_crops, os.path.splitext(os.path.basename(pp))[0])
                os.makedirs(d, exist_ok=True)
                nc.save(os.path.join(d, f"row{i:02d}_1scene.png"))
                pc.save(os.path.join(d, f"row{i:02d}_2picture.png"))
                ac.save(os.path.join(d, f"row{i:02d}_3action.png"))
                dc.save(os.path.join(d, f"row{i:02d}_4dialogue.png"))
                tc.save(os.path.join(d, f"row{i:02d}_5time.png"))
                continue
            # 番号欄を単独で渡す → 丸数字か縦棒(継続)かの判定が絵に紛れず安定する。
            # 各本文列も別画像 → 列をまたいだ取り違えが起きない。
            crops.append((f"コマ{i} scene番号欄(丸数字 or 縦棒)", nb))
            crops.append((f"コマ{i} picture(絵)", pb))
            crops.append((f"コマ{i} action欄", ab))
            crops.append((f"コマ{i} dialogue欄(セリフのみ)", db))
            crops.append((f"コマ{i} time欄", tb))
        if debug_crops:
            continue
        ctx = (prompt + f"\n【継続情報】前ページまでの最後のカット番号は {last_cut}。"
               "このページのカットはそれ以降の連番。ページに描かれた丸番号を優先し、無い所だけ連番で補完。")
        cuts = _vision_page(crops, ctx, model, api_key)
        for j, fr in enumerate(cuts):
            fr["_page"] = os.path.basename(pp)
            fr["_idx"] = j
            # scene_mark（番号欄の見たまま）から numbered を決定的に導く＝モデルの自己矛盾を防ぐ。
            # 丸数字あり→新カット(true)、縦棒｜/空白→続き(false)。scene_mark未出力なら従来通り。
            mark = fr.get("scene_mark")
            if mark is not None:
                m = str(mark)
                # 半角/全角数字 or 丸囲み数字(①〜 U+2460..U+24FF)があれば新カット。縦棒｜/空白は続き。
                fr["numbered"] = (bool(re.search(r"[0-9０-９]", m))
                                  or any("①" <= ch <= "⓿" for ch in m))
            all_frames.append(fr)
            n = _cut_num(fr.get("cut_label", ""))
            if n is not None:
                last_cut = max(last_cut, n)
            print(f"    cut={fr.get('cut_label','')!r} mark={fr.get('scene_mark','')!r} "
                  f"conf={fr.get('confidence','')} action={(fr.get('action','') or '')[:24]}")
    if debug_crops:
        print(f"[debug] 列クロップと _columns_overlay.png を {debug_crops} に保存（APIは未実行）。"
              "各ページの _columns_overlay.png を開き、赤/緑/青の線が用紙の縦罫線に乗っているか確認。"
              "ズレていれば --cols 0.xx,0.yy,0.zz で固定してから本実行。")
        return []
    all_frames = _attach_continuations(all_frames)
    os.makedirs(os.path.dirname(out_json) or ".", exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"frames": all_frames}, f, ensure_ascii=False, indent=2)
    print(f"wrote {out_json}: {len(all_frames)} frames")
    return all_frames


# ---------------------------------------------------------------------------
# 4. 訂正レイヤー（raw=機械読みは不変。人手の訂正は別CSVに置き、読む側で重ねる）
#    目的: OCR誤読は避けられない前提で「どこで間違えたか確認」「手軽に直す」を支える。
# ---------------------------------------------------------------------------
RAW_CSV = "runs/conte_raw_ep7.csv"
OVERRIDES_CSV = "runs/conte_overrides_ep7.csv"
OVERRIDE_FIELDS = ("action", "dialogue", "se", "time")


def load_overrides(overrides_csv: str = OVERRIDES_CSV) -> dict[str, dict]:
    """cut 正規化キー → {field: 訂正値} 。空セルは“訂正なし”として無視。"""
    ov: dict[str, dict] = {}
    if not os.path.exists(overrides_csv):
        return ov
    with open(overrides_csv, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            k = _cut_key(r.get("cut", ""))
            if not k:
                continue
            fixes = {fld: (r.get(fld) or "").strip()
                     for fld in OVERRIDE_FIELDS if (r.get(fld) or "").strip()}
            if fixes:
                ov[k] = fixes
    return ov


def load_corrected(raw_csv: str = RAW_CSV, overrides_csv: str = OVERRIDES_CSV) -> list[dict]:
    """raw コンテに訂正レイヤーを重ねた行を返す。各行に _corrected(訂正したフィールド名のリスト)と
    _orig_<field>(元のOCR値) を付す。raw ファイルには一切書き込まない。"""
    rows: list[dict] = []
    if os.path.exists(raw_csv):
        with open(raw_csv, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    ov = load_overrides(overrides_csv)
    for r in rows:
        k = _cut_key(r.get("cut", ""))
        r["_corrected"] = []
        for fld, val in ov.get(k, {}).items():
            if val != (r.get(fld) or ""):
                r["_orig_" + fld] = r.get(fld, "")
                r[fld] = val
                r["_corrected"].append(fld)
    return rows


def _page_image(pages_dir: str | None, page: str) -> str | None:
    """page 番号に対応する画像をいくつかの命名規則で探す。"""
    if not pages_dir or not str(page).strip():
        return None
    m = re.match(r"\s*(\d+)", str(page))
    if not m:
        return None
    n = int(m.group(1))
    for name in (f"page_{n:03d}.png", f"page_{n}.png", f"p{n}.png", f"page_{n:03d}.jpg"):
        p = os.path.join(pages_dir, name)
        if os.path.exists(p):
            return p
    return None


def review_html(raw_csv: str = RAW_CSV, overrides_csv: str = OVERRIDES_CSV,
                pages_dir: str | None = None, out_html: str = "work/conte_review.html",
                only_uncertain: bool = False) -> str:
    """「ページ画像 ↔ OCRテキスト ↔ 訂正」を並べたレビューHTMLを書き出す。
    pages_dir を渡すと conte render のページ画像を埋め込み、手描き原文と読みを目視照合できる。"""
    rows = load_corrected(raw_csv, overrides_csv)
    if only_uncertain:
        rows = [r for r in rows if str(r.get("uncertain", "")).lower() == "true"]
    by_page: dict[str, list[dict]] = {}
    for r in rows:
        by_page.setdefault((r.get("page") or "").strip() or "（ページ不明）", []).append(r)

    def esc(s):
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    H = ["<!doctype html><meta charset='utf-8'><title>conte review</title>",
         "<style>body{font:14px/1.6 sans-serif;margin:20px}"
         "h2{border-bottom:2px solid #888;margin-top:32px}"
         ".cut{border:1px solid #ccc;border-radius:6px;padding:8px 12px;margin:8px 0}"
         ".unc{background:#fff7e6;border-color:#f0b400}"
         ".fix{background:#e6ffed;border-color:#2da44e}"
         ".lbl{color:#888;font-size:12px}.cor{color:#2da44e;font-weight:bold}"
         ".was{color:#999;text-decoration:line-through}"
         "img{max-width:520px;border:1px solid #ddd;display:block;margin:6px 0}"
         "table{border-collapse:collapse}td{vertical-align:top;padding:4px 10px}</style>"]
    H.append("<h1>絵コンテ OCR レビュー</h1>")
    H.append(f"<p class='lbl'>raw=<code>{esc(raw_csv)}</code> / 訂正=<code>{esc(overrides_csv)}</code>。"
             "🟡=OCR不確実 / 🟢=訂正済み。<b>直し方</b>: "
             f"<code>{esc(overrides_csv)}</code> に該当 cut の行を作り、直したい列"
             "(action/dialogue/se/time)に正しい値を書く（空欄は無視）。保存して再実行で反映。</p>")
    for page, items in by_page.items():
        H.append(f"<h2>page {esc(page)}</h2>")
        img = _page_image(pages_dir, page)
        if img:
            rel = os.path.relpath(img, os.path.dirname(os.path.abspath(out_html)) or ".")
            H.append(f"<img src='{esc(rel)}' alt='page {esc(page)}'>")
        for r in items:
            cls = "cut fix" if r.get("_corrected") else (
                "cut unc" if str(r.get("uncertain", "")).lower() == "true" else "cut")
            badge = "🟢" if r.get("_corrected") else (
                "🟡" if str(r.get("uncertain", "")).lower() == "true" else "")
            H.append(f"<div class='{cls}'><b>cut {esc(r.get('cut',''))}</b> {badge} "
                     f"<span class='lbl'>src={esc(r.get('src',''))} time={esc(r.get('time',''))}</span>")
            for fld in ("action", "dialogue", "se"):
                val = esc(r.get(fld, ""))
                if fld in r.get("_corrected", []):
                    H.append(f"<div><span class='lbl'>{fld}</span> "
                             f"<span class='was'>{esc(r.get('_orig_'+fld,''))}</span> → "
                             f"<span class='cor'>{val}</span></div>")
                elif val:
                    H.append(f"<div><span class='lbl'>{fld}</span> {val}</div>")
            H.append("</div>")
    os.makedirs(os.path.dirname(out_html) or ".", exist_ok=True)
    with open(out_html, "w", encoding="utf-8") as f:
        f.write("\n".join(H))
    print(f"wrote {out_html}: {len(rows)} cuts"
          + (f"（pages_dir={pages_dir} 画像埋め込み）" if pages_dir else "（画像なし＝テキストのみ）"))
    return out_html


def ensure_overrides_template(overrides_csv: str = OVERRIDES_CSV) -> None:
    """訂正CSVが無ければ空テンプレ（ヘッダのみ）を作る。"""
    if os.path.exists(overrides_csv):
        print(f"既存: {overrides_csv}")
        return
    os.makedirs(os.path.dirname(overrides_csv) or ".", exist_ok=True)
    with open(overrides_csv, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerow(["cut", *OVERRIDE_FIELDS, "note"])
    print(f"作成: {overrides_csv}（cut と直したい列だけ書けばよい。空欄は無視）")


def consolidate(frames_json: str = "runs/conte_frames_v2_ep7.json",
                out_csv: str = "runs/conte_v2_ep7.csv") -> int:
    """extract2 の frames を cut 番号で統合（跨り/重複を1カットに結合）して per-cut CSV を書く。
    列: cut, action, dialogue, se, time, characters, confidence, notes。これが新しいコンテ読みの正。"""
    with open(frames_json, encoding="utf-8") as f:
        frames = json.load(f).get("frames", [])
    order: list[str] = []
    by: dict[str, dict] = {}
    # 正規のカット一覧(枝番含む)を cut_board_map から読み、これをホワイトリストにする。
    valid = set()
    ref = "runs/cut_board_map_ep7.csv"
    if os.path.exists(ref):
        with open(ref, encoding="utf-8-sig") as rf:
            for rr in csv.DictReader(rf):
                valid.add(_cut_key(rr.get("cut", "")))
    rank = {"high": 3, "medium": 2, "low": 1, "": 1}
    for fr in frames:
        # 正規の枝番(123A/295B 等)は保持。OCRが続きに勝手につけた枝番(14B/131-cont等)だけ基数に統合。
        raw = _cut_key(fr.get("cut_label", ""))
        if re.search(r"[A-Za-z]$", raw) and raw not in valid:
            nn = _cut_num(raw)
            k = str(nn) if nn is not None else raw
        else:
            k = raw
        if not k or k == "-":
            continue
        # ページをまたいで番号統合しない（同番号でも別ページは別カット＝番号衝突。真の続きは
        # numbered=false で _attach_continuations が既に統合済み）。キーに page を含める。
        page = fr.get("_page", "")
        gk = (page, k)
        if gk not in by:
            by[gk] = {"cut": k, "page": page, "action": [], "dialogue": [],
                      "se": [], "time": [], "characters": [], "confidence": "high", "notes": []}
            order.append(gk)
        r = by[gk]
        def _s(x):  # モデルが int 等で返すことがあるため文字列化に頑健化
            return ("" if x is None else str(x)).strip()
        for col in ("action", "dialogue", "se", "time"):
            v = _s(fr.get(col))
            if v and v not in r[col]:
                r[col].append(v)
        chars = fr.get("characters") or []
        if not isinstance(chars, list):
            chars = [chars]
        for c in chars:
            cs = _s(c)
            if cs and cs not in r["characters"]:
                r["characters"].append(cs)
        if _s(fr.get("notes")):
            r["notes"].append(_s(fr.get("notes")))
        # 結合カットの confidence は最も低いものに合わせる（保守的）
        if rank.get((fr.get("confidence") or "").lower(), 1) < rank.get(r["confidence"], 3):
            r["confidence"] = (fr.get("confidence") or "").lower()
    # 出力はページ→出現順（order=挿入順）を保つ。番号でソートするとページまたぎが崩れるため。
    rows = []
    for gk in order:
        r = by[gk]
        rows.append({"cut": r["cut"], "page": r["page"],
                     "action": " / ".join(r["action"]), "dialogue": " / ".join(r["dialogue"]),
                     "se": " / ".join(r["se"]), "time": " / ".join(r["time"]),
                     "characters": "、".join(r["characters"]),
                     "confidence": r["confidence"], "notes": " ｜ ".join(r["notes"])})
    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["cut", "page", "action", "dialogue", "se", "time",
                                          "characters", "confidence", "notes"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out_csv}: {len(rows)} cuts（{len(frames)} frames を統合）")
    return len(rows)


def verify(csv_path: str = "runs/conte_v2_ep7.csv") -> int:
    """構造不変条件を機械チェックする（API不要・決定論）。再OCR後に通して、列の取り違え/
    枝番の崩れ/欠番を目視でなく自動で洗い出す。corrected があればそちらを優先して読む。
    返り値=異常件数（0なら構造的にクリーン）。"""
    cor = os.path.splitext(csv_path)[0] + ".corrected.csv"
    src = cor if os.path.exists(cor) else csv_path
    with open(src, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    # action由来とみなすトークン（dialogue/timeに出たら列取り違えの疑い）
    cam = ("OK", "A.P.", "AP", "承認", "サイン", "PAN", "T.U", "T.B", "TU", "TB", "F.I", "F.O",
           "O.L", "FIX", "BANK", "兼用", "BOOK", "BG", "全尺", "じわ", "AC", "A.C", "△")
    # time欄の正当形：秒+コマ / 整数 / 空 を ' / ' 連結したもの。括弧は許容。
    time_ok = re.compile(r"^[\s（(]*\d+\s*\+\s*\d+[\s)）]*$|^\s*\d+\s*$")
    issues: list[str] = []

    def cell(r, k):
        return (r.get(k) or "").strip()

    for r in rows:
        cut, page = cell(r, "cut"), cell(r, "page")
        tag = f"cut {cut}（{page}）"
        # 1) time欄に秒+コマ以外（＝action文字の漏れ）が無いか
        for piece in [p for p in cell(r, "time").split(" / ") if p.strip()]:
            if not time_ok.match(piece):
                issues.append(f"[time混入] {tag}: time='{piece}'（秒+コマでない＝action漏れ疑い）")
        # 2) dialogue欄に承認印/カメラ用語（＝セリフでない）が無いか
        dia = cell(r, "dialogue")
        hit = [t for t in cam if t in dia]
        if hit:
            issues.append(f"[dialogue混入] {tag}: dialogue='{dia[:40]}' に {hit}（セリフでない）")

    # 3) 枝番の整合（cut_board_map の正規枝番だけが存在するか）
    valid_branch = set()
    ref = "runs/cut_board_map_ep7.csv"
    if os.path.exists(ref):
        with open(ref, encoding="utf-8-sig") as rf:
            for rr in csv.DictReader(rf):
                k = _cut_key(rr.get("cut", ""))
                if re.search(r"[A-Za-z]$", k):
                    valid_branch.add(k)
    seen_branch = {cell(r, "cut") for r in rows if re.search(r"[A-Za-z]$", cell(r, "cut"))}
    for b in sorted(seen_branch - valid_branch):
        issues.append(f"[枝番] 想定外の枝番 {b}（正規一覧に無い→続きの取り違え疑い）")
    for b in sorted(valid_branch - seen_branch):
        issues.append(f"[枝番] 正規枝番 {b} が欠落（読み落とし疑い）")

    # 4) 欠番（1..max の連番で抜けている数字）
    nums = sorted({_cut_num(cell(r, "cut")) for r in rows if _cut_num(cell(r, "cut")) is not None})
    if nums:
        missing = [n for n in range(1, nums[-1] + 1) if n not in nums]
        if missing:
            issues.append(f"[欠番] {len(missing)}件: {missing[:40]}{' …' if len(missing) > 40 else ''}")

    print(f"verify {src}: {len(rows)} cuts / 異常 {len(issues)} 件"
          + ("（構造的にクリーン）" if not issues else ""))
    for s in issues:
        print("  " + s)
    return len(issues)


def corrections_report(baseline_csv: str = "runs/conte_v2_ep7.baseline.csv",
                       overrides_csv: str = OVERRIDES_CSV,
                       out_md: str = "runs/conte_corrections_report.md") -> int:
    """ベースライン(OCRの読み)と overrides(人手の訂正)を突き合わせ、OCR→訂正 の差分を出す。
    誤読パターンの抽出＝OCR精度改善のヒント用。フィールド単位で old→new を一覧。"""
    base: dict[str, dict] = {}
    if os.path.exists(baseline_csv):
        with open(baseline_csv, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                base[_cut_key(r.get("cut", ""))] = r
    ov = load_overrides(overrides_csv)
    rows = []
    for cut, fixes in ov.items():
        b = base.get(cut, {})
        for fld, newv in fixes.items():
            oldv = (b.get(fld) or "").strip()
            if newv != oldv:
                rows.append((cut, fld, oldv, newv))
    rows.sort(key=lambda r: (re.match(r"\d+", r[0]) and int(re.match(r"\d+", r[0]).group()) or 0, r[1]))
    H = [f"# 絵コンテ OCR→訂正 差分（{len(rows)}件）",
         "> ベースライン(OCR) と overrides(人手訂正) の差。誤読パターンの抽出用。", "",
         "| cut | 欄 | OCRの読み | 訂正後 |", "|---|---|---|---|"]
    for cut, fld, oldv, newv in rows:
        e = lambda s: (s or "").replace("|", "\\|").replace("\n", " ")
        H.append(f"| {cut} | {fld} | {e(oldv)} | {e(newv)} |")
    os.makedirs(os.path.dirname(out_md) or ".", exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(H))
    print(f"wrote {out_md}: OCR→訂正 {len(rows)}件")
    return len(rows)


def _looks_garbled(s: str) -> bool:
    """意味が通らなそうな読みの簡易判定（人名でなく本文の崩れ向け）。"""
    s = (s or "").strip()
    if not s:
        return False
    if "�" in s or "??" in s:
        return True
    # 記号・読点だけ/極端に短い断片
    jp = sum(1 for c in s if "ぁ" <= c <= "ん" or "ァ" <= c <= "ヶ" or "一" <= c <= "龥")
    return len(s) >= 2 and jp == 0


EP7_SPEAKERS = ["SE", "M(モノローグ)", "ナレーション", "尚善", "道然", "呂仁", "黄爺さん",
                "芦花婆さん", "苗", "苗(子供)", "近所の男の子", "沈公子", "花家妻", "花家爺",
                "花家主人", "家来"]


def review_v2(csv_path: str = "runs/conte_v2_ep7.csv", pages_dir: str | None = None,
              out_html: str = "work/conte_review2.html", only_flagged: bool = False) -> str:
    """運用向けコンテ・エディタ。conte_v2 CSV を読み、ページ画像(左・固定)と各カットの編集欄(右)を並置。
    絵コンテ構成 action→dialogue→time。actionはコマ単位で行追加(1コマ目/2コマ目…)、dialogueは話者選択で複数行。
    cut番号も編集可／カット削除・挿入／『訂正済みコンテ全体』を書き出す。corrected があればそれを開く。"""
    cor = os.path.splitext(csv_path)[0] + ".corrected.csv"
    src = cor if os.path.exists(cor) else csv_path
    with open(src, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    def esc(s):
        return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    by_page: dict[str, list[dict]] = {}
    for r in rows:
        by_page.setdefault((r.get("page") or "（ページ不明）").strip(), []).append(r)

    css = (
        "body{font:14px/1.5 sans-serif;margin:0;padding:0 14px 70px}h2{margin:20px 0 4px}"
        ".page{display:flex;gap:14px;align-items:flex-start;border-top:2px solid #ccc;padding-top:6px}"
        ".pimg{flex:0 0 46%;position:sticky;top:6px;align-self:flex-start}.pimg img{width:100%;border:1px solid #ddd}"
        ".cuts{flex:1 1 54%}"
        ".cut{border:1px solid #ccc;border-left-width:6px;border-radius:5px;padding:5px 9px;margin:6px 0}"
        ".red{border-left-color:#cf222e;background:#fff5f4}.yel{border-left-color:#f0b400;background:#fffdf5}"
        ".hi{border-left-color:#2da44e}"
        ".lbl{color:#888;font-size:11px;margin-right:4px}.note{color:#b35900;font-size:11px;margin-top:2px}"
        ".hd{display:flex;align-items:center;gap:6px;margin-bottom:2px}"
        ".sec{margin:3px 0}.slbl{color:#444;font-size:11px;font-weight:bold}"
        ".aline,.line{display:flex;gap:5px;align-items:center;margin:2px 0 2px 8px}"
        ".klbl{flex:0 0 56px;color:#0a66c2;font-size:11px}.spk{flex:0 0 110px}"
        ".f{flex:1;border:1px solid #cbd5e1;border-radius:4px;padding:1px 6px;min-height:1.35em;background:#fff}"
        ".f:focus{outline:2px solid #4493f8;background:#fffef0}"
        ".cutno{flex:0 0 56px;text-align:center;font-weight:bold}"
        "label{display:flex;gap:6px;align-items:baseline;margin:2px 0}"
        ".mini{font-size:11px;padding:1px 7px;cursor:pointer}.add{margin-left:8px}"
        "#bar{position:fixed;bottom:0;left:0;right:0;background:#1f2328;color:#fff;padding:8px 14px;"
        "display:flex;gap:12px;align-items:center;z-index:9}#bar button{font-size:14px;padding:6px 14px;cursor:pointer}")

    js = r"""
function val(e){return e?e.innerText.trim():'';}
function renum(box){var i=0;box.querySelectorAll('.aline').forEach(function(a){i++;a.querySelector('.klbl').innerText=i+'コマ目';});}
function alineHTML(txt){return "<div class='aline'><span class='klbl'></span><span class='f atext' contenteditable='true'>"+(txt||'')+"</span><button class='mini' onclick='delAct(this)'>×</button></div>";}
function addAct(btn){btn.insertAdjacentHTML('beforebegin',alineHTML(''));renum(btn.parentElement);}
function delAct(x){var box=x.closest('.sec');x.parentElement.remove();renum(box);}
function spk(spk,txt){return "<div class='line'><input class='spk' list='speakers' placeholder='話者/SE' value=\""+(spk||'').replace(/"/g,'&quot;')+"\"><span class='f dtext' contenteditable='true'>"+(txt||'')+"</span><button class='mini' onclick='delLine(this)'>×</button></div>";}
function addLine(btn){btn.insertAdjacentHTML('beforebegin',spk('',''));}
function delLine(x){x.parentElement.remove();}
function delCut(btn){if(confirm('このカットを削除しますか？'))btn.closest('.cut').remove();}
function cutHTML(page){
 return "<div class='cut hi' data-page='"+page+"'><div class='hd'><span class='lbl'>cut</span>"
  +"<span class='f cutno' contenteditable='true'></span>"
  +"<button class='mini' onclick='insCut(this)'>＋カット</button>"
  +"<button class='mini' onclick='delCut(this)'>🗑</button></div>"
  +"<div class='sec'><span class='slbl'>action（コマ）</span>"+alineHTML('')
  +"<button class='mini add' onclick='addAct(this)'>＋コマ</button></div>"
  +"<div class='sec'><span class='slbl'>dialogue（話者＋セリフ）</span>"+spk('','')
  +"<button class='mini add' onclick='addLine(this)'>＋行</button></div>"
  +"<label><span class='lbl'>time</span><span class='f' data-field='time' contenteditable='true'></span></label></div>";}
function insCut(btn){var c=btn.closest('.cut');c.insertAdjacentHTML('afterend',cutHTML(c.dataset.page||''));
 var nc=c.nextElementSibling;nc.querySelectorAll('.sec').forEach(renum);}
function exportCSV(){
 var R=[['cut','page','action','dialogue','time']];
 document.querySelectorAll('.cut').forEach(function(c){
  var cut=val(c.querySelector('.cutno')); if(!cut) return;
  var acts=[];c.querySelectorAll('.atext').forEach(function(e){var t=val(e); if(t)acts.push(t);});
  var time=val(c.querySelector("[data-field='time']"));
  var dl=[];c.querySelectorAll('.line').forEach(function(ln){
   var s=ln.querySelector('.spk').value.trim(), tx=val(ln.querySelector('.dtext'));
   if(tx) dl.push(s? s+'：'+tx : tx);});
  R.push([cut, c.dataset.page||'', acts.join(' / '), dl.join(' / '), time]);});
 var s=R.map(function(r){return r.map(function(x){return '"'+(x||'').replace(/"/g,'""')+'"';}).join(',');}).join('\r\n');
 var b=new Blob(['﻿'+s],{type:'text/csv'});var a=document.createElement('a');
 a.href=URL.createObjectURL(b);a.download='conte_v2_ep7.corrected.csv';a.click();}
window.addEventListener('DOMContentLoaded',function(){document.querySelectorAll('.sec').forEach(renum);});
"""
    js = "var SPEAKERS=" + json.dumps(EP7_SPEAKERS, ensure_ascii=False) + ";\n" + js

    def aline_html(txt):
        return (f"<div class='aline'><span class='klbl'></span>"
                f"<span class='f atext' contenteditable='true'>{esc(txt)}</span>"
                f"<button class='mini' onclick='delAct(this)'>×</button></div>")

    def spk_html(spk, txt):
        return (f"<div class='line'><input class='spk' list='speakers' placeholder='話者/SE' "
                f"value=\"{esc(spk).replace(chr(34), '&quot;')}\">"
                f"<span class='f dtext' contenteditable='true'>{esc(txt)}</span>"
                f"<button class='mini' onclick='delLine(this)'>×</button></div>")

    datalist = "<datalist id='speakers'>" + "".join(
        f"<option value='{esc(s)}'>" for s in EP7_SPEAKERS) + "</datalist>"
    H = [f"<!doctype html><meta charset='utf-8'><title>conte editor</title><style>{css}</style>",
         f"<script>{js}</script>", datalist, "<h1>絵コンテ 編集（訂正済みコンテを書き出す）</h1>",
         "<p class='lbl'>左=ページ画像／右=各カット。action はコマ単位で『＋コマ』(1コマ目/2コマ目…)、"
         "dialogue は話者を選び『＋行』。cut番号も編集可。『🗑』削除／『＋カット』挿入。"
         "下の💾で <b>conte_v2_ep7.corrected.csv</b> を書き出し、runs/ に置けば正データ。</p>"]
    n_flag = 0
    for page, items in by_page.items():
        cuts_html = []
        for r in items:
            conf = (r.get("confidence") or "").lower()
            flagged = conf == "low" or _looks_garbled(r.get("action", ""))
            if only_flagged and not flagged:
                continue
            if flagged:
                n_flag += 1
            cls = "red" if flagged else ("yel" if conf == "medium" else "hi")
            acts = [t for t in (r.get("action") or "").split(" / ") if t.strip()] or [""]
            dls = [("SE", t) for t in (r.get("se") or "").split(" / ") if t.strip()]
            for t in (r.get("dialogue") or "").split(" / "):
                if t.strip():
                    sp, _, tx = t.partition("：")
                    dls.append((sp, tx) if tx else ("", t.strip()))
            if not dls:
                dls = [("", "")]
            note = f"<div class='note'>⚠ {esc(r.get('notes',''))}</div>" if r.get("notes") else ""
            cuts_html.append(
                f"<div class='cut {cls}' data-page='{esc(page)}'>"
                f"<div class='hd'><span class='lbl'>cut</span>"
                f"<span class='f cutno' contenteditable='true'>{esc(r.get('cut',''))}</span>"
                f"<span class='lbl'>conf={esc(conf)}</span>"
                f"<button class='mini' onclick='insCut(this)'>＋カット</button>"
                f"<button class='mini' onclick='delCut(this)'>🗑</button></div>"
                f"<div class='sec'><span class='slbl'>action（コマ）</span>"
                + "".join(aline_html(t) for t in acts)
                + "<button class='mini add' onclick='addAct(this)'>＋コマ</button></div>"
                f"<div class='sec'><span class='slbl'>dialogue（話者＋セリフ）</span>"
                + "".join(spk_html(sp, tx) for sp, tx in dls)
                + "<button class='mini add' onclick='addLine(this)'>＋行</button></div>"
                f"<label><span class='lbl'>time</span>"
                f"<span class='f' data-field='time' contenteditable='true'>{esc(r.get('time',''))}</span></label>"
                + note + "</div>")
        if not cuts_html:
            continue
        img = ""
        if pages_dir:
            p = os.path.join(pages_dir, page)
            if os.path.exists(p):
                rel = os.path.relpath(p, os.path.dirname(os.path.abspath(out_html)) or ".")
                img = f"<div class='pimg'><img src='{esc(rel)}' alt='{esc(page)}'></div>"
        H.append(f"<h2>{esc(page)}</h2><div class='page'>{img}<div class='cuts'>"
                 + "".join(cuts_html) + "</div></div>")
    H.append("<div id='bar'><button onclick='exportCSV()'>💾 訂正済みコンテを書き出す</button>"
             "<span class='lbl'>※ conte_v2_ep7.corrected.csv を runs/ に保存→正データ。再開は同じコマンド。</span></div>")
    os.makedirs(os.path.dirname(out_html) or ".", exist_ok=True)
    with open(out_html, "w", encoding="utf-8") as f:
        f.write("\n".join(H))
    print(f"wrote {out_html}: {len(rows)} cuts（{'corrected読込' if src == cor else 'baseline'}）/ 要チェック {n_flag}")
    return out_html


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="genzu_fix.conte",
                                 description="絵コンテ→カット別 situation/remove 抽出（④）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="PDF の指定ページを PNG 化")
    r.add_argument("--pdf", required=True, help="コンテPDFのローカルパス")
    r.add_argument("--out", default="work/conte_pages")
    r.add_argument("--dpi", type=int, default=200)
    r.add_argument("--first", type=int, default=None, help="開始ページ(1始まり)")
    r.add_argument("--last", type=int, default=None, help="終了ページ(両端含む)")

    e = sub.add_parser("extract", help="ページPNG群を Claude Vision でコマ別JSON化")
    e.add_argument("--pages-dir", required=True, help="render の出力ディレクトリ")
    e.add_argument("--out", default="runs/conte_frames_ep7.json")
    e.add_argument("--model", default=DEFAULT_MODEL)

    e2 = sub.add_parser("extract2", help="コマ単位・高解像度・用語集注入の高精度OCR")
    e2.add_argument("--pages-dir", required=True, help="render の出力ディレクトリ")
    e2.add_argument("--out", default="runs/conte_frames_v2_ep7.json")
    e2.add_argument("--model", default=DEFAULT_MODEL)
    e2.add_argument("--glossary", default=GLOSSARY_MD)
    e2.add_argument("--debug-crops", default=None,
                    help="指定するとAPIを叩かず列クロップ＋列境界オーバーレイを保存（切り出し確認用）")
    e2.add_argument("--cols", default=EP7_COLS,
                    help=f"列境界の固定比率 pic|act,act|dia,dia|time（既定={EP7_COLS}＝ep7 DANGUN用紙で目視確認済）。"
                         "用紙が違う場合のみ変更。'auto' で自動検出に戻す")
    e2.add_argument("--first-page", type=int, default=None, help="先頭Nページだけ（試走用）")

    m = sub.add_parser("merge", help="frames JSON を cut_scene_info の situation/remove へ反映")
    m.add_argument("--frames", default="runs/conte_frames_ep7.json")
    m.add_argument("--cut-info", default="runs/cut_scene_info_ep7.csv")
    m.add_argument("--out", default=None, help="未指定なら cut-info を上書き")
    m.add_argument("--overwrite", action="store_true", help="既存の situation/remove も上書き")

    rv = sub.add_parser("review", help="OCR読み↔ページ画像↔訂正 を並べたレビューHTMLを出力")
    rv.add_argument("--raw", default=RAW_CSV)
    rv.add_argument("--overrides", default=OVERRIDES_CSV)
    rv.add_argument("--pages-dir", default=None, help="conte render のページ画像ディレクトリ（あれば画像埋め込み）")
    rv.add_argument("--out", default="work/conte_review.html")
    rv.add_argument("--only-uncertain", action="store_true", help="OCR不確実のカットだけ表示")
    rv.add_argument("--no-open", action="store_true", help="生成後にブラウザを自動で開かない")

    io_ = sub.add_parser("init-overrides", help="訂正レイヤーCSVの空テンプレを作る")
    io_.add_argument("--overrides", default=OVERRIDES_CSV)

    cs = sub.add_parser("consolidate", help="extract2のframesをcut番号で統合しper-cut CSVに")
    cs.add_argument("--frames", default="runs/conte_frames_v2_ep7.json")
    cs.add_argument("--out", default="runs/conte_v2_ep7.csv")

    vf = sub.add_parser("verify", help="構造不変条件を機械チェック(列取り違え/枝番/欠番)。API不要")
    vf.add_argument("--csv", default="runs/conte_v2_ep7.csv",
                    help="検査対象(corrected があれば自動でそれを優先)")

    cr = sub.add_parser("corrections-report", help="OCR(baseline)→人手訂正(overrides)の差分を出す")
    cr.add_argument("--baseline", default="runs/conte_v2_ep7.baseline.csv")
    cr.add_argument("--overrides", default=OVERRIDES_CSV)
    cr.add_argument("--out", default="runs/conte_corrections_report.md")

    r2 = sub.add_parser("review2", help="コンテ編集エディタ(ページ画像と並置・cut番号/台詞編集・訂正済CSV書出し)")
    r2.add_argument("--csv", default="runs/conte_v2_ep7.csv",
                    help="編集元(corrected があれば自動でそれを開く)")
    r2.add_argument("--pages-dir", default=None)
    r2.add_argument("--out", default="work/conte_review2.html")
    r2.add_argument("--only-flagged", action="store_true", help="要チェックのカットだけ表示")
    r2.add_argument("--no-open", action="store_true")

    a = ap.parse_args(argv)
    if a.cmd == "render":
        render(a.pdf, a.out, a.dpi, a.first, a.last)
    elif a.cmd == "extract":
        imgs = sorted(os.path.join(a.pages_dir, f)
                      for f in os.listdir(a.pages_dir)
                      if f.lower().endswith((".png", ".jpg", ".jpeg")))
        if not imgs:
            sys.exit(f"ページ画像が見つかりません: {a.pages_dir}")
        extract(imgs, a.out, a.model)
    elif a.cmd == "extract2":
        imgs = sorted(os.path.join(a.pages_dir, f)
                      for f in os.listdir(a.pages_dir)
                      if f.lower().endswith((".png", ".jpg", ".jpeg")))
        if a.first_page:
            imgs = imgs[:a.first_page]
        if not imgs:
            sys.exit(f"ページ画像が見つかりません: {a.pages_dir}")
        cols_override = None
        if a.cols and a.cols.lower() != "auto":
            try:
                cols_override = [float(x) for x in a.cols.split(",")]
                assert len(cols_override) == 3
            except (ValueError, AssertionError):
                sys.exit("--cols は比率3つ（例 0.50,0.70,0.90）または 'auto' を指定してください。")
        extract2(imgs, a.out, a.model, glossary_path=a.glossary,
                 debug_crops=a.debug_crops, cols_override=cols_override)
    elif a.cmd == "merge":
        frames = json.load(open(a.frames, encoding="utf-8")).get("frames", [])
        merge(frames, a.cut_info, a.out, a.overwrite)
    elif a.cmd == "review":
        out = review_html(a.raw, a.overrides, a.pages_dir, a.out, a.only_uncertain)
        ap_ = os.path.abspath(out)
        if not a.pages_dir or not os.path.isdir(a.pages_dir) or not os.listdir(a.pages_dir):
            print("※ ページ画像なし＝テキストのみ。手描き原文と照合するには先に "
                  "`conte render --pdf <pdf> --out work/conte_pages` を実行し --pages-dir に渡す。"
                  "（render には pip install pymupdf が必要）")
        print(f"開く: {ap_}")
        if not a.no_open:
            try:
                import webbrowser
                webbrowser.open("file:///" + ap_.replace("\\", "/"))
                print("→ 既定ブラウザで開きました（開かない場合は上のパスを直接開く）")
            except Exception:
                print("→ 自動オープン不可。上のパスをブラウザで開いてください。")
    elif a.cmd == "init-overrides":
        ensure_overrides_template(a.overrides)
    elif a.cmd == "consolidate":
        consolidate(a.frames, a.out)
    elif a.cmd == "verify":
        verify(a.csv)
    elif a.cmd == "corrections-report":
        corrections_report(a.baseline, a.overrides, a.out)
    elif a.cmd == "review2":
        out = review_v2(a.csv, a.pages_dir, a.out, a.only_flagged)
        ap_ = os.path.abspath(out)
        print(f"開く: {ap_}")
        if not a.no_open:
            try:
                import webbrowser
                webbrowser.open("file:///" + ap_.replace("\\", "/"))
            except Exception:
                pass


if __name__ == "__main__":
    main()
