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
import urllib.request

# Vision 既定モデル（手描き日本語の読みに強い順で opus を既定に）
DEFAULT_MODEL = "claude-opus-4-8"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

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
def _cut_key(label: str) -> str:
    """カット番号の正規化キー（前ゼロを落とす。枝番は保持）。例 '015'->'15', '016A'->'16A'。"""
    s = (label or "").strip()
    m = re.match(r"0*(\d+)([A-Za-z]?)$", s)
    return (m.group(1) + m.group(2).upper()) if m else s


def _cut_num(label: str):
    """カット番号の整数部（連番引き継ぎ用）。'259B'->259, 'title'->None。"""
    m = re.match(r"\s*0*(\d+)", str(label or ""))
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
                min_band_frac: float = 0.04):
    """グレースケール配列から、行バンド[(y0,y1)] と picture|action 縦境界(0..1) を返す。"""
    import numpy as np
    a = np.asarray(gray)
    h, w = a.shape
    dark = (a < 128).astype(np.float32)
    hlines = _cluster(np.where(dark.mean(axis=1) > row_thresh)[0])
    bands = [(hlines[i], hlines[i + 1]) for i in range(len(hlines) - 1)
             if hlines[i + 1] - hlines[i] > h * min_band_frac]
    vlines = _cluster(np.where(dark.mean(axis=0) > col_thresh)[0])
    # picture|action 境界 = 0.5*w に最も近い縦罫線（無ければ 0.5）
    split = 0.5
    if vlines:
        cx = min(vlines, key=lambda x: abs(x - 0.5 * w))
        if 0.35 * w < cx < 0.65 * w:
            split = cx / w
    return bands, split


def _crop_b64(img, box):
    """PIL画像を box=(l,t,r,b) で切り PNG base64 を返す。小さければ拡大して可読性確保。"""
    c = img.crop(box).convert("RGB")
    if c.width < 1100:
        s = 1100 / c.width
        c = c.resize((int(c.width * s), int(c.height * s)))
    buf = io.BytesIO()
    c.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii"), c


def _extraction_prompt_page(glossary: str) -> str:
    return (
        "あなたは日本の商業アニメ絵コンテを読む専門家です。これから**1ページ分**を渡します。\n"
        "1枚目=『ページ上部ヘッダ』(左上の『No.◯』=用紙通し番号 と 表頭 scene/picture/action/dialogue/time)。\n"
        "2枚目以降=各コマを上から順に「左」= scene欄のカット番号＋picture(絵)、「右」= action/dialogue/time欄。\n\n"
        "【ページ種別の判定（最初に行う）】\n"
        "・ヘッダに『No.◯』と表頭(scene/picture/action/...)があれば**絵コンテ本編ページ**＝カットを読む。\n"
        "・『No.』も表頭も無いページ(タイトルカード/計算メモ/前付け)は**カットでない → cuts:[] を返す**。\n\n"
        "このページに含まれる全カットを、上から順に JSON 配列で返してください。\n"
        "【最重要・番号ずれ防止】\n"
        "・カット番号は作品を通して**連番で増えていく**。上から順にコマを見て、丸囲み数字が新しく現れたら"
        "次のカット、現れないコマは現在のカットの続き。番号補完は『直前カット+1』を基本とする。\n"
        "・**scene欄(左)に縦棒『｜』だけがあり丸囲み数字が無いコマは、直前のカットの『続き』(同一カット)**。\n"
        "  これは新しいカット番号ではない。縦棒を数字『1』と読み間違えないこと。\n"
        "  その続きコマの本文(action/dialogue/time)は、**直前のカットに統合**して1カットにまとめる。\n"
        "・丸で囲まれた数字(①②③/1,2,3)だけが本物のカット番号。1カットが複数コマに跨ることがある。\n"
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
        '{"cuts":[{"cut_label":"カット番号。差し込みは英字枝番つき 例 8 / 16A / 259B(Bを落とさない)。補完したら notes に明記",'
        '"action":"action欄。カメラ用語は上の正規形に寄せる",'
        '"dialogue":"dialogue欄","se":"効果音があれば",'
        '"time":"time欄。秒+コマ表記(例 4+12)。分数読みは誤り",'
        '"characters":["本文に書かれた人名を忠実に。実在しない誤読名のみ実在名に正す(例 芦龍→芦花)。'
        '書かれた字数字形に合わない名前を当てず、短い名を長い正式名に拡張しない。曖昧は空+notesに要確認"],'
        '"confidence":"high|medium|low","notes":"不確実箇所/番号補完/保留"}]}'
    )


def _vision_page(crops: list[tuple], prompt: str, model: str, api_key: str,
                 max_tokens: int = 4096) -> list[dict]:
    """crops=[(label, b64), ...] を順に並べ、ページ全体を1リクエストでOCR。cuts配列を返す。"""
    content = []
    for label, b64 in crops:
        content.append({"type": "text", "text": f"【{label}】"})
        content.append({"type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": b64}})
    content.append({"type": "text", "text": prompt})
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}]}
    req = urllib.request.Request(
        ANTHROPIC_URL, data=json.dumps(body).encode("utf-8"),
        headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION,
                 "content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=240) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return []
    try:
        return json.loads(m.group(0)).get("cuts", [])
    except json.JSONDecodeError:
        return []


def extract2(page_paths: list[str], out_json: str = "runs/conte_frames_v2_ep7.json",
             model: str = DEFAULT_MODEL, api_key: str | None = None,
             glossary_path: str = GLOSSARY_MD, debug_crops: str | None = None) -> list[dict]:
    """ページPNG群を、表の行検出→カット単位2枚切り→用語集付きOCR で読む。
    debug_crops を指定すると API を叩かず、各カットの左右クロップを保存して切り出しを目視確認できる。"""
    from PIL import Image
    if not debug_crops:
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY が未設定です。")
    glossary = load_glossary(glossary_path)
    prompt = _extraction_prompt_page(glossary)
    all_frames = []
    last_cut = 0  # 前ページまでの最後のカット番号（連番をページ越しに引き継ぐ）
    for pp in page_paths:
        img = Image.open(pp)
        bands, split = detect_grid(img.convert("L"))
        sx = int(split * img.width)
        print(f"  {os.path.basename(pp)}: {len(bands)}コマ検出 split={split:.2f}")
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
            lb, lc = _crop_b64(img, (0, y0, sx, y1))            # scene番号(継続縦棒) + picture
            rb, rc = _crop_b64(img, (sx, y0, img.width, y1))    # action + dialogue + time
            if debug_crops:
                d = os.path.join(debug_crops, os.path.splitext(os.path.basename(pp))[0])
                os.makedirs(d, exist_ok=True)
                lc.save(os.path.join(d, f"row{i:02d}_left.png"))
                rc.save(os.path.join(d, f"row{i:02d}_right.png"))
                continue
            crops.append((f"コマ{i} 左(番号+絵)", lb))
            crops.append((f"コマ{i} 右(本文)", rb))
        if debug_crops:
            continue
        ctx = (prompt + f"\n【継続情報】前ページまでの最後のカット番号は {last_cut}。"
               "このページのカットはそれ以降の連番。ページに描かれた丸番号を優先し、無い所だけ連番で補完。")
        cuts = _vision_page(crops, ctx, model, api_key)
        for j, fr in enumerate(cuts):
            fr["_page"] = os.path.basename(pp)
            fr["_idx"] = j
            all_frames.append(fr)
            n = _cut_num(fr.get("cut_label", ""))
            if n is not None:
                last_cut = max(last_cut, n)
            print(f"    cut={fr.get('cut_label','')!r} conf={fr.get('confidence','')} "
                  f"action={(fr.get('action','') or '')[:28]}")
    if debug_crops:
        print(f"[debug] 左右クロップを {debug_crops} に保存（APIは未実行）。中身を確認して罫線/列がズレてなければ本実行。")
        return []
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
    rank = {"high": 3, "medium": 2, "low": 1, "": 1}
    for fr in frames:
        k = _cut_key(fr.get("cut_label", ""))
        if not k or k == "-":
            continue
        if k not in by:
            by[k] = {"cut": k, "action": [], "dialogue": [], "se": [], "time": [],
                     "characters": [], "confidence": "high", "notes": []}
            order.append(k)
        r = by[k]
        for col in ("action", "dialogue", "se", "time"):
            v = (fr.get(col) or "").strip()
            if v and v not in r[col]:
                r[col].append(v)
        for c in fr.get("characters") or []:
            if c and c not in r["characters"]:
                r["characters"].append(c)
        if fr.get("notes"):
            r["notes"].append(fr["notes"].strip())
        # 結合カットの confidence は最も低いものに合わせる（保守的）
        if rank.get((fr.get("confidence") or "").lower(), 1) < rank.get(r["confidence"], 3):
            r["confidence"] = (fr.get("confidence") or "").lower()
    # 番号順（枝番は数値→英字でソート）
    def sk(k):
        m = re.match(r"(\d+)([A-Za-z]*)", k)
        return (int(m.group(1)), m.group(2)) if m else (10**9, k)
    rows = []
    for k in sorted(by, key=sk):
        r = by[k]
        rows.append({"cut": k,
                     "action": " / ".join(r["action"]), "dialogue": " / ".join(r["dialogue"]),
                     "se": " / ".join(r["se"]), "time": " / ".join(r["time"]),
                     "characters": "、".join(r["characters"]),
                     "confidence": r["confidence"], "notes": " ｜ ".join(r["notes"])})
    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["cut", "action", "dialogue", "se", "time",
                                          "characters", "confidence", "notes"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out_csv}: {len(rows)} cuts（{len(frames)} frames を統合）")
    return len(rows)


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


def review_v2(frames_json: str = "runs/conte_frames_v2_ep7.json",
              overrides_csv: str = OVERRIDES_CSV, pages_dir: str | None = None,
              out_html: str = "work/conte_review2.html", only_flagged: bool = False) -> str:
    """運用向けレビュー: ページ画像（左・固定）と各カットの編集可能フィールド（右）を左右に並べ、
    全カット表示・その場編集・『訂正CSV書き出し』ボタン付き。色=confidence(🔴low/🟡medium/通常high/🟢訂正済)。
    only_flagged=True で要チェックのみ。"""
    with open(frames_json, encoding="utf-8") as f:
        frames = json.load(f).get("frames", [])
    ov = load_overrides(overrides_csv)
    by_page: dict[str, list[dict]] = {}
    for fr in frames:
        by_page.setdefault(fr.get("_page", "（ページ不明）"), []).append(fr)

    def esc(s):
        return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def attr(s):
        return esc(s).replace('"', "&quot;").replace("\n", "&#10;")

    css = (
        "body{font:14px/1.55 sans-serif;margin:0;padding:0 16px 80px}"
        "h2{margin:24px 0 6px}.page{display:flex;gap:16px;align-items:flex-start;"
        "border-top:2px solid #ccc;padding-top:8px}"
        ".pimg{flex:0 0 48%;position:sticky;top:8px;align-self:flex-start}"
        ".pimg img{width:100%;border:1px solid #ddd}"
        ".cuts{flex:1 1 52%}"
        ".cut{border:1px solid #ccc;border-left-width:6px;border-radius:5px;padding:6px 10px;margin:6px 0}"
        ".red{border-left-color:#cf222e;background:#fff5f4}.yel{border-left-color:#f0b400;background:#fffdf5}"
        ".hi{border-left-color:#2da44e}.grn{border-left-color:#2da44e;background:#f2fff6}"
        ".lbl{color:#888;font-size:11px;margin-right:4px}.note{color:#b35900;font-size:11px;margin-top:2px}"
        "label{display:flex;gap:6px;align-items:baseline;margin:2px 0}"
        ".f{flex:1;border:1px solid #cbd5e1;border-radius:4px;padding:2px 6px;min-height:1.4em;background:#fff}"
        ".f:focus{outline:2px solid #4493f8;background:#fffef0}.f.ch{background:#fff7d6;border-color:#f0b400}"
        "#bar{position:fixed;bottom:0;left:0;right:0;background:#1f2328;color:#fff;padding:8px 16px;"
        "display:flex;gap:12px;align-items:center;z-index:9}"
        "#bar button{font-size:14px;padding:6px 14px;cursor:pointer}"
        ".cl{font-size:12px;font-weight:bold}")
    js = (
        "function csv(only){let R=[['cut','action','dialogue','se','time','note']];"
        "document.querySelectorAll('.cut').forEach(c=>{let cut=c.dataset.cut,ch=false,v={};"
        "c.querySelectorAll('.f').forEach(e=>{let f=e.dataset.field,o=e.dataset.orig,t=e.innerText.trim();"
        "if(t!==o){ch=true;v[f]=t;}});"
        "if(ch)R.push([cut,v.action||'',v.dialogue||'',v.se||'',v.time||'','']);});"
        "if(R.length<2){alert('編集された箇所がありません');return;}"
        "let s=R.map(r=>r.map(x=>'\"'+(x||'').replace(/\"/g,'\"\"')+'\"').join(',')).join('\\r\\n');"
        "let b=new Blob(['\\ufeff'+s],{type:'text/csv'});let a=document.createElement('a');"
        "a.href=URL.createObjectURL(b);a.download='conte_overrides_ep7.csv';a.click();}"
        "function mark(e){e.classList.toggle('ch',e.innerText.trim()!==e.dataset.orig);"
        "let n=document.querySelectorAll('.f.ch').length;document.getElementById('cnt').innerText=n;}")
    H = [f"<!doctype html><meta charset='utf-8'><title>conte review2</title><style>{css}</style>",
         f"<script>{js}</script>",
         "<h1>絵コンテ 読みレビュー（編集可）</h1>",
         "<p class='lbl'>左=ページ画像／右=各カット。色◧ 🔴low 🟡medium 通常high 🟢訂正済。"
         "右の欄を直接書き換え→下のボタンで <b>conte_overrides_ep7.csv</b> を書き出し、runs/ に置けば反映。</p>"]
    n_flag = 0
    for page, items in by_page.items():
        cuts_html = []
        for fr in items:
            cut = fr.get("cut_label", "")
            fixes = ov.get(_cut_key(cut), {})
            corrected = [fld for fld in OVERRIDE_FIELDS if fixes.get(fld)]
            for fld in corrected:
                fr[fld] = fixes[fld]
            conf = (fr.get("confidence") or "").lower()
            notes = fr.get("notes", "")
            flagged = conf == "low" or _looks_garbled(fr.get("action", ""))
            if only_flagged and not (flagged or corrected):
                continue
            cls = "grn" if corrected else ("red" if flagged else ("yel" if conf == "medium" else "hi"))
            if flagged and not corrected:
                n_flag += 1
            fields = []
            for fld in ("action", "dialogue", "se", "time"):
                val = fr.get(fld, "")
                fields.append(
                    f"<label><span class='lbl'>{fld}</span>"
                    f"<span class='f' contenteditable='true' data-field='{fld}' "
                    f"data-orig=\"{attr(val)}\" oninput='mark(this)'>{esc(val)}</span></label>")
            chars = ("<div class='lbl'>登場: " + esc('、'.join(fr.get('characters'))) + "</div>"
                     if fr.get("characters") else "")
            note = f"<div class='note'>⚠ {esc(notes)}</div>" if notes else ""
            cuts_html.append(
                f"<div class='cut {cls}' data-cut=\"{attr(cut)}\">"
                f"<span class='cl'>cut {esc(cut)}</span> <span class='lbl'>conf={esc(conf)}</span>"
                + "".join(fields) + chars + note + "</div>")
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
    H.append("<div id='bar'>編集した欄: <span id='cnt'>0</span> 件　"
             "<button onclick='csv()'>💾 訂正CSVを書き出す</button>"
             "<span class='lbl'>※ ダウンロードした conte_overrides_ep7.csv を runs/ に置けば反映</span></div>")
    os.makedirs(os.path.dirname(out_html) or ".", exist_ok=True)
    with open(out_html, "w", encoding="utf-8") as f:
        f.write("\n".join(H))
    print(f"wrote {out_html}: {len(frames)} cuts / 要チェック {n_flag} 件（全カット表示・編集可）")
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
                    help="指定するとAPIを叩かず左右クロップを保存（切り出し確認用）")
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

    cr = sub.add_parser("corrections-report", help="OCR(baseline)→人手訂正(overrides)の差分を出す")
    cr.add_argument("--baseline", default="runs/conte_v2_ep7.baseline.csv")
    cr.add_argument("--overrides", default=OVERRIDES_CSV)
    cr.add_argument("--out", default="runs/conte_corrections_report.md")

    r2 = sub.add_parser("review2", help="extract2のframesを confidence/notesで色分けレビュー(🔴要チェック)")
    r2.add_argument("--frames", default="runs/conte_frames_v2_ep7.json")
    r2.add_argument("--overrides", default=OVERRIDES_CSV)
    r2.add_argument("--pages-dir", default=None)
    r2.add_argument("--out", default="work/conte_review2.html")
    r2.add_argument("--only-flagged", action="store_true", help="要チェック/訂正済のカットだけ表示")
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
        extract2(imgs, a.out, a.model, glossary_path=a.glossary, debug_crops=a.debug_crops)
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
    elif a.cmd == "corrections-report":
        corrections_report(a.baseline, a.overrides, a.out)
    elif a.cmd == "review2":
        out = review_v2(a.frames, a.overrides, a.pages_dir, a.out, a.only_flagged)
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
