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

import csv
import json
import os
import re
from dataclasses import dataclass, field

from . import prompt as promptlib

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
    "・このカットの主体は何か。\n"
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
    "出力は (a) 概要版3行以内（主体・カメラワーク等）、(b) 詳細版、(c) アラート（簡潔に対応すべき内容）。"
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
# CLI（show=入力束と各役プロンプトを確認。実行は別ドライバ）
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
    a = ap.parse_args(argv)
    if a.cmd == "show":
        _show(a.cut)


if __name__ == "__main__":
    main()
