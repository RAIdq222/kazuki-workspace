"""場面理解モジュール — 「このカットは何で、どんな背景を描くべきか」を精緻に詰める前段。

プロンプト設計（どう生成するか）は後工程に分離する。本モジュールは *理解* だけを扱う。

設計の肝＝**独立性は入力の遮断で担保する**:
  3つの観点を別コンテキスト（別エージェント）で走らせ、各役に見せる入力を物理的に絞る。
  同一文脈で3役を演じると必ず結論が揃ってしまい、「食い違いを出す」という目的が壊れるため。

  Step0  シーン要約（絵コンテのみ）         … 全役へ渡す唯一の共有シード
  観点1  原図に忠実な役  入力= 原図PNG のみ           （コンテ/ボード/設定は見せない）
  観点2  演出の役        入力= 絵コンテ＋前後カット のみ（原図/ボードは見せない）
  観点3  様式・考証の役  入力= 原図PNG＋ボード＋設定資料（絵コンテは見せない）
  Step2  統合（司会＋裁定） 入力= 3観点の出力＋裁定基準
  Step3  出力（概要≤3行／詳細／アラート）

入力源は既存資産から機械的に束ねる:
  原図PNG   handoff/ep7/cut<NN>/{genzu.png, genzu_visible.png}（PCのCLI実行が gather で出す）
  絵コンテ  runs/conte_raw_ep7.csv（cut＋前後）
  美術ボード runs/cut_board_map_ep7.csv → runs/board_manifest_ep7.csv（drive_id/画像）
  設定資料  runs/scene_profiles/<key>.json ＋ runs/ep7_設定資料まとめ.md

モデル呼び出し自体は本モジュールに持たせない（prompt.py と同じ思想＝組み立てとスキーマだけ）。
実行ドライバ（サブエージェント or API）に role_prompt と schema を渡して回す。
"""
from __future__ import annotations

import base64
import csv
import io
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from . import prompt as promptlib
from . import psd_export

# Anthropic REST（conte.py と同じ流儀＝標準ライブラリのみ・要 ANTHROPIC_API_KEY）
DEFAULT_MODEL = "claude-opus-4-8"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _p(*parts: str) -> str:
    return os.path.join(ROOT, *parts)


# ---------------------------------------------------------------------------
# 役の system プロンプト（日本語。出力は人のレビュー用なので日本語で思考させる）
# ---------------------------------------------------------------------------
STEP0_SYSTEM = (
    "あなたは絵コンテだけを見て、このカットが何のシーンかを短い1〜2行の一文で書く。"
    "前後カットのつながりを踏まえる。解釈を盛らず、芝居の要点だけを一文で。"
    "以降の3観点はこの理解だけを共有する。"
)

KANTEN1_SYSTEM = (
    "あなたは『原図に忠実な役』。渡された原図PNGに**何が描いてあるか**だけを報告する。\n"
    "・解釈・補正・様式的な良し悪しの判断はしない（それは他の役の仕事）。\n"
    "・文字情報、描かれているキャラクター・構成物を列挙する。\n"
    "・想定されるカメラワーク（画角・クローズアップ度合い）の“読み取り”は述べてよい。\n"
    "・**制作マーク（カット番号・タップ穴・フレーム枠）は要素から除外**する。\n"
    "・確信度の低い文字・意図が読めない描き込みは、確信度を下げて『要素情報』として提示する。\n"
    "絵コンテ・美術ボード・設定資料は見ていない前提で、原図に写っている事実だけを述べること。"
)

KANTEN2_SYSTEM = (
    "あなたは『演出の役』。絵コンテの内容と前後カットのつながりから、芝居として正しい形を主張する。\n"
    "・**原図が何を描いているかは一旦置く**（原図は見ていない）。\n"
    "・絵コンテは手描きのOCR読み取りで**誤読が多い（uncertain）**。人名・固有名は確信度が低い前提で扱い、"
    "読み取り名を実在の登場人物と決めつけない。確信が持てない要素は basis に『OCR不確実』と明記する。\n"
    "・このカットの主体は何か（背景カットでは人物でなく“その場所・空間”が主体になりうる）。\n"
    "・主体に従属して、妥当なカメラ（寄り／アングル／フォーカス対象の高さ）はどうあるべきか。\n"
    "・芝居として画面に映るべきもの／映る必要のないものは何か。\n"
    "・カメラは fix か動きがあるか（絵コンテの指定を読む）。\n"
    "原図に引きずられず、芝居の理屈で“あるべき形”を述べること。"
)

KANTEN3_SYSTEM = (
    "あなたは『様式・考証の役』。原図と美術ボード・設定資料を対比して判断する。\n"
    "・原図は美術ボードから**どの場面を切り取ったシーン**になりそうか。\n"
    "・建築・什器・様式はどうあるべきか。\n"
    "・**美術ボードは構図の参照には使わない**（様式・語彙の参照に限る）。\n"
    "・設定資料に該当什器の設定があれば**それを一次資料**とする。無ければボードを様式の語彙として使う。\n"
    "・各項目について出典（設定資料=一次 / ボード=語彙）を明示する。\n"
    "芝居（絵コンテ）は見ていない前提で、様式・考証の観点だけで述べること。"
)

INTEGRATE_SYSTEM = (
    "あなたは『統合役』。3観点の司会と裁定を兼ねる。\n"
    "1) 3観点の意見を並べ、**食い違っている点だけ**を抜き出す。一致点は確定とし議論しない。\n"
    "2) 食い違いごとに原因を見分ける:\n"
    "   ・認識ミスの匂い（ある観点が見間違い・読み違いの可能性）→ その観点に再精査を促す（alert化）。\n"
    "   ・扱いの違い（事実は一致だが採否が割れる）→ 下記の裁定基準で裁く。\n"
    "【裁定基準】\n"
    "  ・原図と絵コンテ・演出判断が食い違ったら、**原図を正**とする"
    "（コンテは設計であり、打合せや原図作成を通じて詳細は変化しうるため）。\n"
    "  ・構成物は、カットの主体と被らず、描き込みを増やしすぎない解を選ぶ。曖昧な所は断定しない。\n"
    "  ・精査しても割れる／原図と絵コンテが矛盾／どちらの解釈もありうる → 無理に決めず、"
    "**判断が割れたアラート箇所として人間確認にまわす**。\n"
    "【入力健全性の最優先チェック】\n"
    "  ・観点1が『背景作画線が無い／指示メモ・タップ穴だけ』と報告、または原図がBGonlyなのに人物が主体に"
    "なっている場合は、**レイヤー誤読＝入力が壊れている疑い**を最優先のアラート『要・原図確認』とし、"
    "下流（主体・カメラ・構成物）は確定させず暫定に留める。壊れた入力の上に自信ある結論を作らないこと。\n"
    "  ・人名など固有名はOCR誤読を疑い、実在キャラと断定しない。\n"
    "出力は (a) 概要版3行以内（主体・カメラワーク等。未確定なら『未確定』と書く）、(b) 詳細版、"
    "(c) アラート（簡潔に対応すべき内容）。"
)

# ---------------------------------------------------------------------------
# 構造化出力スキーマ（実行ドライバが StructuredOutput で強制する用）
# ---------------------------------------------------------------------------
SCHEMA_STEP0 = {
    "type": "object",
    "properties": {"scene_line": {"type": "string", "description": "1〜2行のシーン要約"}},
    "required": ["scene_line"],
}

SCHEMA_KANTEN1 = {
    "type": "object",
    "properties": {
        "elements": {"type": "array", "items": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["構成物", "キャラ", "文字", "その他"]},
            "what": {"type": "string"}, "where": {"type": "string"},
            "confidence": {"type": "string", "enum": ["高", "中", "低"]}},
            "required": ["kind", "what", "confidence"]}},
        "camera_read": {"type": "object", "properties": {
            "framing": {"type": "string"}, "closeup": {"type": "string"}, "notes": {"type": "string"}}},
        "excluded_marks": {"type": "array", "items": {"type": "string"},
                           "description": "除外した制作マーク（カット番号/タップ穴/枠）"},
    },
    "required": ["elements", "camera_read"],
}

SCHEMA_KANTEN2 = {
    "type": "object",
    "properties": {
        "subject": {"type": "string", "description": "このカットの主体"},
        "camera": {"type": "object", "properties": {
            "yori": {"type": "string", "description": "寄り/引き"},
            "angle": {"type": "string"}, "focus_height": {"type": "string"},
            "fix_or_move": {"type": "string", "enum": ["fix", "move", "不明"]}}},
        "should_show": {"type": "array", "items": {"type": "string"}},
        "need_not_show": {"type": "array", "items": {"type": "string"}},
        "basis": {"type": "string", "description": "前後カットのつながり等、判断の根拠"},
    },
    "required": ["subject", "camera", "should_show", "need_not_show"],
}

SCHEMA_KANTEN3 = {
    "type": "object",
    "properties": {
        "master_crop": {"type": "string", "description": "ボードのどの場面を切り取った絵か"},
        "architecture": {"type": "array", "items": {"type": "string"}},
        "fixtures": {"type": "array", "items": {"type": "object", "properties": {
            "item": {"type": "string"},
            "source": {"type": "string", "enum": ["設定資料(一次)", "ボード(語彙)"]}},
            "required": ["item", "source"]}},
        "avoid": {"type": "array", "items": {"type": "string"}},
        "note": {"type": "string", "description": "設定資料に該当什器があったか等"},
    },
    "required": ["master_crop", "architecture", "fixtures"],
}

SCHEMA_INTEGRATE = {
    "type": "object",
    "properties": {
        "agreed": {"type": "array", "items": {"type": "string"}, "description": "一致＝確定事項"},
        "conflicts": {"type": "array", "items": {"type": "object", "properties": {
            "point": {"type": "string"},
            "cause": {"type": "string", "enum": ["認識ミス", "扱いの違い"]},
            "resolution": {"type": "string"}, "basis": {"type": "string"}},
            "required": ["point", "cause", "resolution"]}},
        "summary": {"type": "string", "description": "概要版・3行以内（主体・カメラワーク）"},
        "detail": {"type": "string", "description": "詳細版"},
        "alerts": {"type": "array", "items": {"type": "object", "properties": {
            "tag": {"type": "string", "enum": ["要・原図確認", "要・判断", "要・ボード確認"]},
            "point": {"type": "string"}, "action": {"type": "string"}},
            "required": ["tag", "point"]}},
        "situation": {"type": "string", "description": "cut_scene_info の situation 列に書く確定文"},
        "remove": {"type": "string", "description": "cut_scene_info の remove 列に書く確定文"},
    },
    "required": ["agreed", "conflicts", "summary", "alerts"],
}


# ---------------------------------------------------------------------------
# 入力束ね
# ---------------------------------------------------------------------------
@dataclass
class Bundle:
    cut: str
    scene: str = ""
    # 原図（PCのCLIが handoff へ出す。未着なら pending）
    genzu_base_png: str | None = None
    genzu_visible_png: str | None = None
    genzu_pending: bool = True
    genzu_filename: str = ""          # cut_board_map の PSD ファイル名
    bg_only: bool = False             # *_BGonly.psd ＝背景のみ（人物は別セル）
    extract_info: dict | None = None  # export_background_layer の strategy/layers
    # 絵コンテ（cut＋前後）
    conte: list[dict] = field(default_factory=list)
    # 美術ボード
    board_name: str = ""
    board_drive_id: str = ""
    board_local_png: str | None = None
    # 設定資料
    scene_key: str = ""
    place: str = ""
    time: str = ""
    weather: str = ""
    structures: str = ""
    era: str = ""
    profile: dict | None = None


def _norm(cut: str) -> str:
    m = re.match(r"0*(\d+)([A-Za-z]?)$", str(cut).strip())
    return (m.group(1) + m.group(2).upper()) if m else str(cut).strip()


def _read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def assemble(cut: str, context: int = 2) -> Bundle:
    """1カット分の入力束を、既存資産から機械的に組む。原図は handoff にあれば差す。"""
    cut = _norm(cut)
    b = Bundle(cut=cut)

    # 絵コンテ（cut＋前後 context 本）
    rows = _read_csv(_p("runs", "conte_raw_ep7.csv"))
    by_num = {}
    for r in rows:
        m = re.match(r"\s*(\d+)", r.get("cut", ""))
        if m:
            by_num.setdefault(int(m.group(1)), r)
    cn = int(re.match(r"(\d+)", cut).group(1))
    for n in range(cn - context, cn + context + 1):
        if n in by_num:
            r = by_num[n]
            b.conte.append({"cut": r.get("cut"), "self": n == cn,
                            "action": r.get("action", ""), "dialogue": r.get("dialogue", ""),
                            "se": r.get("se", ""), "uncertain": r.get("uncertain", "")})

    # ボード（cut_board_map → board_manifest）
    for r in _read_csv(_p("runs", "cut_board_map_ep7.csv")):
        if _norm(r.get("cut", "")) == cut:
            b.board_name = (r.get("board") or "").strip()
            b.scene = r.get("scene", "")
            b.genzu_filename = (r.get("filename") or "").strip()
            b.bg_only = "bgonly" in b.genzu_filename.lower()
            break
    for r in _read_csv(_p("runs", "board_manifest_ep7.csv")):
        if (r.get("board") or "").strip() == b.board_name:
            b.board_drive_id = r.get("drive_id", "")
            break
    cand = _p("handoff", "ep7", f"cut{cn:03d}", "board.png")
    b.board_local_png = cand if os.path.exists(cand) else None

    # 設定資料（cut_scene_info に行があれば優先。無ければ board 名から機械補完）
    info_row = None
    for r in _read_csv(_p("runs", "cut_scene_info_ep7.csv")):
        if _norm(r.get("cut", "")) == cut:
            info_row = r
            break
    try:
        reg = promptlib.SceneRegistry.load()
        info = (promptlib.CutInfo.from_row(info_row) if info_row
                else promptlib.cut_info_from_board(b.board_name, b.scene, reg, cut=cut))
        b.scene_key = info.scene_key or ""
        b.place, b.time, b.weather = info.place or "", info.time or "", info.weather or ""
        b.structures, b.era = info.structures or "", info.era or ""
        prof = next((p for p in reg.profiles if p.key == b.scene_key), None)
        if prof is None and b.board_name:
            prof = reg.resolve(b.board_name, b.scene)
        if prof is not None and hasattr(prof, "__dict__"):
            b.profile = dict(prof.__dict__)
    except Exception:
        pass

    # 原図（handoff にあれば差す。無ければ pending）
    base = _p("handoff", "ep7", f"cut{cn:03d}", "genzu.png")
    vis = _p("handoff", "ep7", f"cut{cn:03d}", "genzu_visible.png")
    if os.path.exists(base):
        b.genzu_base_png, b.genzu_pending = base, False
    if os.path.exists(vis):
        b.genzu_visible_png = vis
    return b


# ---------------------------------------------------------------------------
# 役ごとの入力ルーティング（独立性の本体）＝各役に渡すテキストブロック
# ---------------------------------------------------------------------------
def _conte_block(b: Bundle) -> str:
    lines = []
    for c in b.conte:
        tag = "▶このカット" if c["self"] else f"  cut{c['cut']}"
        lines.append(f"{tag}: 動き『{c['action']}』  セリフ『{c['dialogue']}』"
                     + (f" SE『{c['se']}』" if c['se'] else "")
                     + (" ※OCR不確実" if str(c['uncertain']).lower() == "true" else ""))
    return "\n".join(lines) or "(絵コンテ該当なし)"


def _settei_block(b: Bundle) -> str:
    out = [f"場所: {b.place or b.scene_key}", f"時代: {b.era}",
           f"時間: {b.time}　天気: {b.weather}", f"構成物(候補): {b.structures}"]
    if b.profile:
        for k in ("structures", "style_note", "avoid"):
            v = b.profile.get(k) if isinstance(b.profile, dict) else None
            if v:
                out.append(f"profile.{k}: {v}")
    return "\n".join(out)


def role_inputs(role: str, b: Bundle, step0: str) -> dict:
    """role ∈ {kanten1,kanten2,kanten3}。各役に**許可された入力だけ**を返す。
    画像（原図/ボード）は images に絶対パスで入れる（ドライバが添付する）。"""
    shared = f"[共有シーン要約] {step0}\n[カット] cut{b.cut}（{b.scene}）"
    if b.bg_only:
        shared += (f"\n[重要] 原図ファイルは {b.genzu_filename}＝**背景のみ(BGonly)**。"
                   "人物・キャラは別セルに分かれ本図には描かれない。主体を人物にしないこと。")
    if b.extract_info and b.extract_info.get("strategy") == "fallback":
        shared += ("\n[警告] 原図の背景作画レイヤーを特定できずフォールバック合成。"
                   "画にタップ穴・指示メモしか無い場合は『背景作画が取れていない』と報告し、推測で背景を創作しない。")
    if role == "kanten1":
        return {"system": KANTEN1_SYSTEM, "schema": SCHEMA_KANTEN1,
                "text": shared + "\n（原図PNGのみを見て報告。コンテ/ボード/設定は与えない）",
                "images": [p for p in (b.genzu_base_png, b.genzu_visible_png) if p]}
    if role == "kanten2":
        return {"system": KANTEN2_SYSTEM, "schema": SCHEMA_KANTEN2,
                "text": shared + "\n[絵コンテ(前後含む)]\n" + _conte_block(b),
                "images": []}
    if role == "kanten3":
        return {"system": KANTEN3_SYSTEM, "schema": SCHEMA_KANTEN3,
                "text": shared + f"\n[美術ボード] {b.board_name}（drive:{b.board_drive_id or '—'}）\n"
                                 + "[設定資料]\n" + _settei_block(b),
                "images": [p for p in (b.genzu_base_png, b.board_local_png) if p]}
    raise ValueError(role)


def step0_inputs(b: Bundle) -> dict:
    return {"system": STEP0_SYSTEM, "schema": SCHEMA_STEP0,
            "text": f"[カット] cut{b.cut}（{b.scene}）\n[絵コンテ(前後含む)]\n" + _conte_block(b),
            "images": []}


def integrate_inputs(b: Bundle, step0: str, k1: dict, k2: dict, k3: dict) -> dict:
    body = (f"[共有シーン要約] {step0}\n\n"
            f"[観点1 原図忠実]\n{json.dumps(k1, ensure_ascii=False, indent=2)}\n\n"
            f"[観点2 演出]\n{json.dumps(k2, ensure_ascii=False, indent=2)}\n\n"
            f"[観点3 様式考証]\n{json.dumps(k3, ensure_ascii=False, indent=2)}")
    return {"system": INTEGRATE_SYSTEM, "schema": SCHEMA_INTEGRATE, "text": body, "images": []}


# ---------------------------------------------------------------------------
# Step3 出力レンダリング（人レビュー用 Markdown。アラートは 🔴＋太字）
# ---------------------------------------------------------------------------
def render_markdown(cut: str, integrated: dict) -> str:
    o = integrated
    md = [f"# cut{cut} 場面理解", "", "## 概要", o.get("summary", "(なし)").strip(), "", "## 詳細",
          o.get("detail", "(なし)").strip(), ""]
    if o.get("situation") or o.get("remove"):
        md += ["## cut_scene_info への記入案",
               f"- situation: {o.get('situation','')}", f"- remove: {o.get('remove','')}", ""]
    md.append("## アラート（人間確認）")
    alerts = o.get("alerts") or []
    if not alerts:
        md.append("（なし）")
    for a in alerts:
        md.append(f"- 🔴 **※{a.get('tag','要・判断')}** — {a.get('point','')}"
                  + (f"／対応: {a.get('action','')}" if a.get("action") else ""))
    return "\n".join(md)


# ---------------------------------------------------------------------------
# 実行ドライバ（run）— 原図PSD→PNG（ローカル）＋ Claude で観点1〜3＋統合を独立実行
# ---------------------------------------------------------------------------
def _resolve_psd(cut: str, genzu_dir: str, csv_path: str | None = None) -> str | None:
    """cut番号→本体PSDを cut_board_map で引き、genzu_dir 配下を再帰探索（render_genzu と同手順）。"""
    csv_path = csv_path or _p("runs", "cut_board_map_ep7.csv")
    n = int(re.match(r"(\d+)", _norm(cut)).group(1))
    cand: list[str] = []
    for r in _read_csv(csv_path):
        m = re.match(r"\s*(\d+)", r.get("cut", ""))
        fn = (r.get("filename") or "").strip()
        if m and int(m.group(1)) == n and fn and fn not in cand:
            cand.append(fn)
    cand.sort(key=lambda f: (f.count("_"), "bgonly" in f.lower(), len(f)))
    names = cand or [f"shz_07_{n:03d}_genzu.psd"]
    idx: dict[str, str] = {}
    for root, _, files in os.walk(genzu_dir):
        for f in files:
            if f.lower().endswith(".psd"):
                idx.setdefault(f, os.path.join(root, f))
    for nm in names:
        if nm in idx:
            return idx[nm]
    for f, p in idx.items():
        if f"_{n:03d}_" in f or re.search(rf"_{n:03d}\b", f):
            return p
    return None


def render_genzu_png(cut: str, genzu_dir: str,
                     work: str = "work") -> tuple[str | None, str | None, dict | None]:
    """原図PSD→ base/visible PNG。コンソール＝/read-genzu と同じ psd_export を使う。
    戻り: (base_png, visible_png, info)。info=export_background_layer の strategy/layers。"""
    psd = _resolve_psd(cut, genzu_dir)
    if not psd:
        return None, None, None
    n = int(re.match(r"(\d+)", _norm(cut)).group(1))
    out = os.path.join(work, "_genzu_view", f"cut{n:03d}")
    os.makedirs(out, exist_ok=True)
    base = os.path.join(out, "genzu_base.png")
    vis = os.path.join(out, "genzu_visible.png")
    _, _, info = psd_export.export_background_layer(psd, base)
    psd_export.export_visible_to_png(psd, vis, drop_text=False)
    return base, vis, info


def _parse_json_obj(text: str) -> dict:
    """Claude応答から最初のJSONオブジェクトを取り出す（conte.parse_frames と同じ頑健さ）。"""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    raw = m.group(1) if m else text
    start = raw.find("{")
    if start < 0:
        return {}
    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw[start:i + 1])
                except json.JSONDecodeError:
                    return {}
    return {}


def _encode_image(path: str, max_edge: int = 1568) -> tuple[str, str]:
    """画像を長辺 max_edge 以下に縮小して (media_type, base64) を返す。
    原図PNGは大きく、そのまま送るとVision呼び出しが遅い（Anthropicも内部で1568へ縮小する）。"""
    try:
        from PIL import Image
        im = Image.open(path)
        w, h = im.size
        if max(w, h) > max_edge:
            s = max_edge / max(w, h)
            im = im.convert("RGB").resize((max(1, int(w * s)), max(1, int(h * s))))
        else:
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        return "image/png", base64.standard_b64encode(buf.getvalue()).decode("ascii")
    except Exception:  # PIL不在/壊れ等は原本をそのまま送る
        with open(path, "rb") as fh:
            b64 = base64.standard_b64encode(fh.read()).decode("ascii")
        return ("image/png" if path.lower().endswith(".png") else "image/jpeg"), b64


def _anthropic_call(role_in: dict, model: str, api_key: str,
                    max_tokens: int = 4096, timeout: int = 180) -> dict:
    """1役分（system＋許可入力＋画像＋schema）を Claude に渡し JSON を返す。役ごとに独立リクエスト。"""
    content: list[dict] = []
    for img in role_in.get("images", []):
        media, b64 = _encode_image(img)
        content.append({"type": "image",
                        "source": {"type": "base64", "media_type": media, "data": b64}})
    instr = (role_in["text"] + "\n\n出力は次のJSONスキーマに厳密に従い、**JSONのみ**返す"
             "（前後に説明文を付けない）:\n" + json.dumps(role_in["schema"], ensure_ascii=False))
    content.append({"type": "text", "text": instr})
    body = {"model": model, "max_tokens": max_tokens, "system": role_in["system"],
            "messages": [{"role": "user", "content": content}]}
    req = urllib.request.Request(
        ANTHROPIC_URL, data=json.dumps(body).encode("utf-8"),
        headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION,
                 "content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise SystemExit(f"Anthropic APIエラー {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Anthropic API 接続失敗: {e.reason}（ネット/プロキシ要確認）")
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return _parse_json_obj(text)


def run(cut: str, genzu_dir: str | None = None, model: str = DEFAULT_MODEL,
        out_dir: str | None = None, context: int = 2, dry_run: bool = False) -> dict:
    """1カットの場面理解を通しで実行。観点1〜3を**役ごとに独立リクエスト**で回し統合する。
    genzu_dir があれば原図PSD→PNGを起こして観点1/3へ渡す。無ければ観点1は保留。"""
    out_dir = out_dir or _p("runs", "scene_understanding")
    b = assemble(cut, context=context)
    if genzu_dir:
        base, vis, info = render_genzu_png(cut, genzu_dir)
        if base:
            b.genzu_base_png, b.genzu_visible_png, b.genzu_pending = base, vis, False
            b.extract_info = info
            print(f"原図: {base}")
            print(f"  レイヤー抽出: strategy={info.get('strategy')} layers={info.get('layers')}"
                  if info else "  レイヤー抽出: info無し")
            if info and info.get("strategy") == "fallback":
                print("  ⚠️ strategy=fallback ＝ BG/LO/背景 のどれにも一致せず。"
                      "指示・タップ穴だけ拾った誤読の恐れ大。--layers で要確認。")
            if b.bg_only:
                print(f"  ℹ️ {b.genzu_filename} は BGonly＝背景のみ。人物は別セル（主体を人物にしない）。")
        else:
            print(f"原図: PSDが {genzu_dir} に見つからず（観点1は保留）")

    plan = ["step0(コンテのみ)",
            ("観点1(原図)" if not b.genzu_pending else "観点1=保留(原図未着)"),
            "観点2(コンテのみ)", "観点3(原図＋ボード＋設定)", "統合"]
    print("実行計画:", " → ".join(plan))
    if dry_run:
        print("[dry-run] APIは叩かない。各役の入力ルーティングは show で確認可。")
        return {"cut": _norm(cut), "dry_run": True, "genzu_pending": b.genzu_pending}

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY が未設定です（conte extract と同じ）。")

    def _step(label, fn):
        print(f"  … {label} 実行中", flush=True)
        r = fn()
        print(f"  ✓ {label} 完了", flush=True)
        return r

    step0 = _step("step0(コンテ要約)",
                  lambda: _anthropic_call(step0_inputs(b), model, api_key)).get("scene_line", "")
    print(f"step0: {step0}", flush=True)
    if b.genzu_pending:
        k1 = {"status": "未実行", "reason": "原図PNG未着"}
        print("  － 観点1(原図) スキップ（原図未着）", flush=True)
    else:
        k1 = _step("観点1(原図/画像Vision)",
                   lambda: _anthropic_call(role_inputs("kanten1", b, step0), model, api_key))
    k2 = _step("観点2(コンテ)",
               lambda: _anthropic_call(role_inputs("kanten2", b, step0), model, api_key))
    k3 = _step("観点3(原図＋ボード＋設定)",
               lambda: _anthropic_call(role_inputs("kanten3", b, step0), model, api_key))

    ii = integrate_inputs(b, step0, k1, k2, k3)
    if b.genzu_pending:
        ii["text"] += ("\n\n※観点1(原図忠実)は原図PNG未着のため未実行。"
                       "原図に依存する判断は確定せず『要・原図確認』アラートに倒すこと。")
    integrated = _step("統合(裁定)", lambda: _anthropic_call(ii, model, api_key))

    n = int(re.match(r"(\d+)", _norm(cut)).group(1))
    os.makedirs(out_dir, exist_ok=True)
    record = {"cut": _norm(cut), "scene": b.scene, "model": model, "step0": step0,
              "genzu_pending": b.genzu_pending,
              "kanten1": k1, "kanten2": k2, "kanten3": k3, "integrated": integrated}
    with open(os.path.join(out_dir, f"cut{n:03d}.json"), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    md = render_markdown(_norm(cut), integrated)
    with open(os.path.join(out_dir, f"cut{n:03d}.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(f"\n書き出し: {out_dir}/cut{n:03d}.{{json,md}}")
    print("\n" + md)
    return record


# ---------------------------------------------------------------------------
# CLI（show=入力束と各役プロンプトを確認 / run=通しで実行）
# ---------------------------------------------------------------------------
def _show(cut: str) -> None:
    b = assemble(cut)
    print(f"# cut{b.cut}  scene={b.scene!r}")
    print(f"原図: {'未着(handoff待ち)' if b.genzu_pending else b.genzu_base_png}")
    print(f"ボード: {b.board_name!r} drive={b.board_drive_id or '—'} "
          f"local={'有' if b.board_local_png else '無'}")
    print(f"設定: place={b.place or b.scene_key!r} time={b.time!r} weather={b.weather!r}")
    print("\n--- Step0 (絵コンテのみ) ---\n" + step0_inputs(b)["text"])
    for role in ("kanten1", "kanten2", "kanten3"):
        ri = role_inputs(role, b, "<step0要約>")
        print(f"\n=== {role} system ===\n{ri['system']}")
        print(f"--- {role} 入力テキスト ---\n{ri['text']}")
        print(f"--- {role} 画像 ---\n{ri['images'] or '(なし)'}")


def main(argv=None) -> None:
    import argparse
    ap = argparse.ArgumentParser(prog="genzu_fix.scene_understanding",
                                 description="場面理解（観点1〜3＋統合）の入力束ねとプロンプト確認")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show", help="1カットの入力束と各役プロンプトを表示")
    s.add_argument("--cut", required=True)

    r = sub.add_parser("run", help="1カットを通しで実行（観点1〜3＋統合）")
    r.add_argument("--cut", required=True)
    r.add_argument("--genzu-dir", default=None, help="原図PSDの探索ルート（例 ..\\00.原図）。"
                                                     "無ければ観点1は保留")
    r.add_argument("--model", default=DEFAULT_MODEL)
    r.add_argument("--out", default=None, help="出力先（既定 runs/scene_understanding）")
    r.add_argument("--context", type=int, default=2, help="絵コンテの前後参照本数")
    r.add_argument("--dry-run", action="store_true", help="APIを叩かず実行計画だけ表示")

    a = ap.parse_args(argv)
    if a.cmd == "show":
        _show(a.cut)
    elif a.cmd == "run":
        run(a.cut, genzu_dir=a.genzu_dir, model=a.model, out_dir=a.out,
            context=a.context, dry_run=a.dry_run)


if __name__ == "__main__":
    main()
