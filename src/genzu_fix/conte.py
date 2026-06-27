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

    m = sub.add_parser("merge", help="frames JSON を cut_scene_info の situation/remove へ反映")
    m.add_argument("--frames", default="runs/conte_frames_ep7.json")
    m.add_argument("--cut-info", default="runs/cut_scene_info_ep7.csv")
    m.add_argument("--out", default=None, help="未指定なら cut-info を上書き")
    m.add_argument("--overwrite", action="store_true", help="既存の situation/remove も上書き")

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
    elif a.cmd == "merge":
        frames = json.load(open(a.frames, encoding="utf-8")).get("frames", [])
        merge(frames, a.cut_info, a.out, a.overwrite)


if __name__ == "__main__":
    main()
