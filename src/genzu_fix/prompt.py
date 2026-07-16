"""カット別 生成プロンプトの組み立て（3層アセンブリ）。

層構造:
  [A] GLOBAL  作品共通（役割 / レジスト / 白黒線画 / 線質 / 除去 / 余白）— 固定文字列。
  [B] SCENE   シーン固有（場所語彙 / era / 構成物 / 避けるもの）— runs/scene_profiles/<key>.json。
  [C] CUT     カット固有（time/weather の線処理 + 場面 situation + 個別 remove）
              — 香盤表 / 美術ボード名 / 絵コンテ 由来。

出力は **EN（GPT Image 2 への入力）と JP（人の作業確認用）の対**で返す。
モデルへ渡すのは EN のみ。JP は突合・レビュー用であってモデルには渡さない。

`build(board, scene)` が表口。`runs/cut_scene_info_ep7.csv` の生成は `gen-info` サブコマンド、
1カットのプレビューは `show` サブコマンドで行う。
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
from dataclasses import dataclass, field, replace

from .naming import parse_board

# ---------------------------------------------------------------------------
# [A] GLOBAL — 作品共通ブロック（固定）
# ---------------------------------------------------------------------------

# 役割は「修正パス」: 保持(構図/配置/カメラ)・修正(パース/構造/様式)・品位向上(手描き清書)の
# 三分割。trace でも free re-illust でもない。除去ルールは qc.py の
# 「主体に属する=消す / 環境=残す」と一語一句揃える。
GLOBAL_EN = (
    "You are a background art director's correction pass. Take a rough background layout "
    "(genzu) — a low-fidelity request sketch that may contain perspective errors and weak "
    "structure — and produce a corrected, near-delivery-quality BLACK-AND-WHITE background "
    "line drawing (haikei). This is a clean-up that FIXES and ELEVATES; it is neither a "
    "literal trace nor a free re-illustration.\n"
    "PRESERVE (treat as directives): the composition, camera angle, eye-level and framing; "
    "the placement and front-to-back ordering of the major structures and natural elements; "
    "and the positions where characters stand, as spatial constraints. Do not zoom, crop, "
    "pan, re-center or re-stage what the layout shows.\n"
    "WHAT EXISTS: the layout alone defines what is visible in this shot. If the layout "
    "does not show it, it does not exist here — do not complete the rest of the room, and "
    "do not add furniture, openings, walls or scenery of your own.\n"
    "CORRECT (fix what is wrong): resolve perspective so edges converge cleanly to the "
    "intended vanishing points; straighten weak or implausible structure and proportion; "
    "correct the shapes of what is drawn so they read right for the era and culture of the "
    "setting below — by fixing existing forms, never by adding new ones. Keep the intended "
    "camera, but fix the geometry under it.\n"
    "ELEVATE (raise the quality): render like a master background artist's careful "
    "hand-drawn pencil clean-up — line weight varied (heavier in the foreground, finer in "
    "the distance) with natural entry/exit tapering, texture suggested by light broken "
    "strokes. Refine and articulate ONLY the forms the layout already shows: texture and "
    "construction detail may be added on existing surfaces, but never as new objects. Do "
    "NOT produce uniform vector outlines or a coloring-book look, and do not glamorize or "
    "upgrade any element beyond its role.\n"
    "COLOR: monochrome output only — pure black ink lines on white, no grey shading or "
    "solid fills. Colored regions in the input are placeholder fills: read them as shapes "
    "and draw them as plain line work, never as color.\n"
    "REMOVE: erase all production marks (handwritten notes, labels, numbers, frame borders, "
    "perspective guide lines, registration tap-holes). Large pale-grey CHECKERBOARD areas "
    "are transparency placeholders, not drawing: treat them as blank and never render the "
    "checker pattern. Also remove any character/person/"
    "animal and everything they hold, wear or carry, and rebuild the plain environment "
    "behind them. Keep furniture and fixtures that belong to the space (a bed, shelves, a "
    "lamp stay; a book in a hand goes).\n"
    "DON'T over-correct: where a judgement is genuinely ambiguous, respect the layout's "
    "intent rather than inventing. MARGINS: the blank padding bands are intentional — leave "
    "them empty."
)

GLOBAL_JP = (
    "あなたは背景美術監督の「修正パス」である。ラフな背景レイアウト（原図）— パースの狂いや弱い構造を含みうる、"
    "低精度の依頼用ラフ — を、納品手前の品質の白黒背景線画（背景）に仕上げる。\n"
    "これは「直して品位を引き上げる」クリーンアップであり、字義通りのトレースでも、自由な描き直しでもない。\n"
    "保持（指示として守る）: 構図・カメラアングル・アイレベル・画角／主要な建物と自然物の配置と前後関係／"
    "キャラの立ち位置（空間的な制約として）。原図が写しているものをズーム・トリミング・パン・再センタリング・再演出しない。\n"
    "存在の定義: このカットに何が写っているかは原図だけが定義する。原図に無いものはこのカットには存在しない — "
    "部屋の続きを補完しない。家具・開口部・壁・景物を自分で足さない。\n"
    "修正（狂いを直す）: エッジが意図した消失点へクリーンに収束するようパースを整える。弱い/不自然な構造と比率を正す。"
    "描かれているものの形を下記の時代・文化に照らして正す — 既存の形の修正であり、新しい物の追加ではない。"
    "意図したカメラは保ったまま、その下の幾何を直す。\n"
    "品位向上: 一流の背景美術が丁寧に手描き鉛筆で清書したように描く — 線幅変調（近景は太く・遠景は繊細に）と"
    "自然な入り抜き、質感は軽い擦れ/破線で示唆。磨き込むのは**原図に既に写っている形だけ**: 既存の面への質感・"
    "構造ディテールの追い込みは可、新しい物としての追加は不可。\n"
    "  均一なベクター輪郭や塗り絵調にしない。どの要素も役割以上に格上げ・豪華化しない。\n"
    "色: 出力は白黒のみ。白地に黒のインク線、グレーの陰影やベタ塗りは禁止。入力中の色面はプレースホルダの塗りで、"
    "形として読み取り、色ではなく素の線画として描く。\n"
    "除去: 制作用マーク（手書き指示・ラベル・番号・フレーム枠・パース補助線・タップ穴）を全て消す。"
    "薄いグレーの大きな市松模様は透明部分のプレースホルダであり絵ではない — 空白として扱い、市松柄を描かない。\n"
    "  さらに、キャラ/人物/動物と、その持ち物・着衣・携行物を全て消し、背後の素の環境を再構成する。\n"
    "  その場所に属する家具・什器は残す（寝台・棚・燭台は残す／手に持つ本は消す）。\n"
    "過修正の禁止: 判断が本当に曖昧な所は、捏造せず原図の意図を尊重する。余白: 周囲の空白パディング帯は意図的なもの。空白のまま残す。"
)

# ---------------------------------------------------------------------------
# genzu_trust="high" 用のA層 — 原図を「正」として扱う忠実清書モード。
# SP2のように3Dレイアウト出しでパース・アイレベルが最初から正しい原図に、
# 「狂いを直せ」と言うのは誤り（再解釈の権限を与え、構図が動く原因になる）。
# 「守る」か「直す」かは作品/カットごとの宣言であり、決め打ちにしない（黒江さん指摘）。
# ---------------------------------------------------------------------------
GLOBAL_TRUST_EN = (
    "You are a background art finishing pass. Take a background layout (genzu) exported "
    "from an accurate 3D layout — its composition, camera, perspective, eye level and "
    "proportions are ALREADY CORRECT — and redraw it as a delivery-quality BLACK-AND-WHITE "
    "background line drawing (haikei). This is faithful finishing and densification, NOT "
    "correction: change nothing about the geometry.\n"
    "PRESERVE (absolute): the composition, camera angle, eye-level and framing; the exact "
    "position, size and shape of every element. Do not zoom, crop, pan, re-center, "
    "re-proportion, or 'improve' the perspective — it is already right.\n"
    "WHAT EXISTS: the layout alone defines what is visible in this shot. If the layout "
    "does not show it, it does not exist here — do not complete the rest of the room, and "
    "do not add furniture, openings, walls or scenery of your own.\n"
    "ELEVATE (raise the quality): render like a master background artist's careful "
    "hand-drawn pencil finish laid over this exact layout — line weight varied (heavier in "
    "the foreground, finer in the distance) with natural entry/exit tapering, texture "
    "suggested by light broken strokes. Refine ONLY the surfaces the layout already shows, "
    "adding construction and texture detail on them without altering their geometry. Do "
    "NOT produce uniform vector outlines or a coloring-book look.\n"
    "COLOR: monochrome output only — pure black ink lines on white, no grey shading or "
    "solid fills. Colored regions in the input are placeholder fills: read them as shapes "
    "and draw them as plain line work, never as color.\n"
    "REMOVE: erase all production marks (handwritten notes, labels, numbers, frame borders, "
    "perspective guide lines, registration tap-holes). Large pale-grey CHECKERBOARD areas "
    "are transparency placeholders, not drawing: treat them as blank and never render the "
    "checker pattern. Also remove any character/person/animal and everything they hold, "
    "wear or carry, and rebuild the plain environment behind them. Keep furniture and "
    "fixtures that belong to the space.\n"
    "WHEN UNSURE: follow the layout literally. MARGINS: the blank padding bands are "
    "intentional — leave them empty."
)

GLOBAL_TRUST_JP = (
    "あなたは背景美術の「清書パス」である。この原図は正確な3Dレイアウトから出力されており、"
    "構図・カメラ・パース・アイレベル・比率は**最初から正しい**。それを納品品質の白黒背景線画（背景）として"
    "描き起こす。これは忠実な仕上げ・描き込みであり、修正ではない — 幾何は一切変えない。\n"
    "保持（絶対）: 構図・カメラアングル・アイレベル・画角／全要素の正確な位置・大きさ・形。"
    "ズーム・トリミング・パン・再センタリング・比率変更・パースの「改善」をしない — 既に正しい。\n"
    "存在の定義: このカットに何が写っているかは原図だけが定義する。原図に無いものは存在しない — "
    "部屋の続きを補完しない。家具・開口部・壁・景物を自分で足さない。\n"
    "品位向上: 一流の背景美術がこのレイアウトの上に丁寧に手描き鉛筆で仕上げたように描く — "
    "線幅変調（近景は太く・遠景は繊細に）と自然な入り抜き、質感は軽い擦れ/破線で示唆。"
    "磨き込むのは原図に既に写っている面だけ: 幾何を変えずに質感・構造ディテールを足す。"
    "均一なベクター輪郭や塗り絵調にしない。\n"
    "色: 出力は白黒のみ。白地に黒のインク線、グレーの陰影やベタ塗りは禁止。入力中の色面はプレースホルダの塗りで、"
    "形として読み取り、色ではなく素の線画として描く。\n"
    "除去: 制作用マーク（手書き指示・ラベル・番号・フレーム枠・パース補助線・タップ穴）を全て消す。"
    "薄いグレーの大きな市松模様は透明部分のプレースホルダであり絵ではない — 空白として扱い、市松柄を描かない。"
    "キャラ/人物/動物とその持ち物・着衣は全て消し、背後の素の環境を再構成する。場所に属する家具・什器は残す。\n"
    "迷ったら: 原図を字義通りに写す。余白: 周囲の空白パディング帯は意図的なもの。空白のまま残す。"
)

# era の既定値（作品共通の時代様式）。scene_profile 側で個別指定があればそちらを優先。
DEFAULT_ERA_EN = "Chinese Northern-and-Southern-Dynasties to early-Tang period"
DEFAULT_ERA_JP = "中国 南北朝〜初唐ごろ"

# ---------------------------------------------------------------------------
# [C] CUT — time / weather を白黒線画の「線の付け方」に翻訳する
#     （白黒なので色は出さない。陰影の輪郭密度・遠近の線の落とし方だけが変わる）
# ---------------------------------------------------------------------------
TIME_TREATMENT = {
    "夜": (
        "Night scene — convey darkness only through denser, heavier shadow contours and "
        "selective line build-up; remain pure black line on white, no grey fill, no solid "
        "black masses.",
        "夜の場面 — 暗さは陰影輪郭の密度と線の重ねだけで表す。白地に黒線のまま、グレーのベタやベタ黒の塊は使わない。",
    ),
    "明け方": (
        "Dawn — soft low light; faint, long cast-shadow contours, light overall linework.",
        "明け方 — 柔らかい低い光。淡く長い落ち影の輪郭、全体に軽い線。",
    ),
    "朝": (
        "Morning — even gentle light; minimal cast shadow, clean light linework.",
        "朝 — 均一で穏やかな光。落ち影は最小限、すっきりした軽い線。",
    ),
    "昼": (
        "Daytime — neutral even lighting; restrained shadow contour lines.",
        "昼 — ニュートラルで均一な光。陰影の輪郭線は控えめ。",
    ),
    "浅夕": (
        "Early evening — slightly longer directional cast shadows than midday, still line only.",
        "浅夕 — 昼よりやや長い方向性のある落ち影。線のみ。",
    ),
    "夕方": (
        "Evening — longer directional cast-shadow contours; line only, no grey.",
        "夕方 — 長い方向性のある落ち影の輪郭。線のみ、グレー無し。",
    ),
    "夕": (
        "Evening — longer directional cast-shadow contours; line only, no grey.",
        "夕 — 長い方向性のある落ち影の輪郭。線のみ、グレー無し。",
    ),
}

WEATHER_TREATMENT = {
    "雨": (
        "Rain — suggest wet ground and reflections with line only; do not add grey fills or "
        "rain streaks unless they are present in the layout.",
        "雨 — 濡れた地面や反射は線だけで示唆する。原図に無い限りグレーのベタや雨脚は足さない。",
    ),
    "霧あり": (
        "Fog — distant elements fade with lighter, sparser linework to suggest depth; no grey wash.",
        "霧あり — 遠景は線を薄く疎にして奥行きを示す。グレーのウォッシュは使わない。",
    ),
    "霧": (
        "Fog — distant elements fade with lighter, sparser linework to suggest depth; no grey wash.",
        "霧 — 遠景は線を薄く疎にして奥行きを示す。グレーのウォッシュは使わない。",
    ),
    "霧なし": ("", ""),  # 明示的に「霧なし」= 何も足さない
}


# ---------------------------------------------------------------------------
# [B] SCENE — シーン固有プロファイル（runs/scene_profiles/<key>.json）
# ---------------------------------------------------------------------------
@dataclass
class SceneProfile:
    key: str
    match: list[str] = field(default_factory=list)   # ボード名/シーン名に対する別名（substring）
    place_en: str = ""
    place_jp: str = ""
    era_en: str = DEFAULT_ERA_EN
    era_jp: str = DEFAULT_ERA_JP
    structures_en: list[str] = field(default_factory=list)
    structures_jp: list[str] = field(default_factory=list)
    style_en: str = ""
    style_jp: str = ""
    avoid_en: list[str] = field(default_factory=list)
    avoid_jp: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, path: str) -> "SceneProfile":
        d = json.load(open(path, encoding="utf-8"))

        def bi(key, default=""):
            v = d.get(key) or {}
            return v.get("en", default), v.get("jp", default)

        def bilist(key):
            v = d.get(key) or {}
            return list(v.get("en", [])), list(v.get("jp", []))

        place_en, place_jp = bi("place")
        era_en, era_jp = bi("era", "")
        st_en, st_jp = bilist("structures")
        style_en, style_jp = bi("style_note")
        av_en, av_jp = bilist("avoid")
        return cls(
            key=d["key"], match=list(d.get("match", [])),
            place_en=place_en, place_jp=place_jp,
            era_en=era_en or DEFAULT_ERA_EN, era_jp=era_jp or DEFAULT_ERA_JP,
            structures_en=st_en, structures_jp=st_jp,
            style_en=style_en, style_jp=style_jp,
            avoid_en=av_en, avoid_jp=av_jp,
        )

    def block_en(self) -> str:
        parts = [f"[SCENE] Setting: {self.place_en} — {self.era_en}."]
        if self.structures_en:
            parts.append("Elements likely present: " + ", ".join(self.structures_en) + ".")
        if self.style_en:
            parts.append(self.style_en.rstrip(".") + ".")
        if self.avoid_en:
            parts.append("Avoid: " + ", ".join(self.avoid_en) + ".")
        return " ".join(parts)

    def block_jp(self) -> str:
        parts = [f"[シーン] 舞台: {self.place_jp}（{self.era_jp}）。"]
        if self.structures_jp:
            parts.append("在りうる構成物: " + "、".join(self.structures_jp) + "。")
        if self.style_jp:
            parts.append(self.style_jp.rstrip("。") + "。")
        if self.avoid_jp:
            parts.append("避ける: " + "、".join(self.avoid_jp) + "。")
        return " ".join(parts)


def _default_profiles_dir() -> str:
    # リポジトリ直下の runs/scene_profiles（このファイルは src/genzu_fix/prompt.py）
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "runs", "scene_profiles"))


class SceneRegistry:
    """scene_profiles/*.json を読み込み、ボード名/シーン名から最適プロファイルを引く。"""

    def __init__(self, profiles: list[SceneProfile]):
        self.profiles = profiles

    @classmethod
    def load(cls, profiles_dir: str | None = None) -> "SceneRegistry":
        profiles_dir = profiles_dir or _default_profiles_dir()
        profs = []
        for p in sorted(glob.glob(os.path.join(profiles_dir, "*.json"))):
            try:
                profs.append(SceneProfile.from_json(p))
            except (KeyError, json.JSONDecodeError):
                continue
        return cls(profs)

    def resolve(self, board: str, scene: str) -> SceneProfile | None:
        """別名（match）が board / scene に最も多く・長く一致するプロファイルを返す。"""
        text = f"{board} {scene}"
        best, best_score = None, 0
        for prof in self.profiles:
            score = sum(len(m) for m in prof.match if m and m in text)
            if score > best_score:
                best, best_score = prof, score
        return best


# ---------------------------------------------------------------------------
# CutInfo — runs/cut_scene_info_ep7.csv の1行に対応する構造化情報
# ---------------------------------------------------------------------------
CUT_INFO_FIELDS = [
    "cut", "scene_key", "place", "time", "weather",
    "situation", "situation_en", "remove", "remove_en",
    "structures", "era", "source",
]


@dataclass
class CutInfo:
    cut: str = ""
    scene_key: str = ""
    place: str = ""
    time: str = ""
    weather: str = ""
    situation: str = ""     # 場面 JP（人の確認用。コンテ由来→④で充足）
    situation_en: str = ""  # 場面 EN（モデル入力用）
    remove: str = ""        # 除去対象 JP（確認用）
    remove_en: str = ""     # 除去対象 EN（モデル入力用）
    structures: str = ""    # scene_profile 由来の既定（; 区切り）。カット個別に上書き可
    era: str = ""
    source: str = ""

    def to_row(self) -> dict:
        return {k: getattr(self, k) for k in CUT_INFO_FIELDS}

    @classmethod
    def from_row(cls, row: dict) -> "CutInfo":
        return cls(**{k: (row.get(k) or "") for k in CUT_INFO_FIELDS})


@dataclass
class Prompt:
    en: str
    jp: str
    info: CutInfo


def cut_info_from_board(board: str, scene: str, registry: SceneRegistry,
                        cut: str = "") -> CutInfo:
    """ボード名 + シーン名から、機械で取れる範囲の CutInfo を作る。
    situation / remove はコンテ依存なので空欄のまま（#4 で充足）。"""
    bi = parse_board(board) if board else None
    prof = registry.resolve(board, scene)
    src = []
    if board:
        src.append(f"board:{board}")
    if prof:
        src.append(f"profile:{prof.key}")
    return CutInfo(
        cut=str(cut),
        scene_key=prof.key if prof else "",
        place=(prof.place_jp if prof else (bi.place if bi else "")),
        time=(bi.time if bi else ""),
        weather=(bi.weather if bi else ""),
        situation="",
        remove="",
        structures=("；".join(prof.structures_jp) if prof else ""),
        era=(prof.era_jp if prof else ""),
        source=";".join(src),
    )


def _en_sentence(s: str) -> str:
    """EN文末を整える（末尾の 。/. を1つの . に正規化）。"""
    return s.strip().rstrip("。.").strip() + "."


def _cut_block(info: CutInfo) -> tuple[str, str]:
    en_parts, jp_parts = [], []
    t_en, t_jp = TIME_TREATMENT.get(info.time, ("", ""))
    w_en, w_jp = WEATHER_TREATMENT.get(info.weather, ("", ""))
    if t_en:
        en_parts.append(t_en)
    if t_jp:
        jp_parts.append(t_jp)
    if w_en:
        en_parts.append(w_en)
    if w_jp:
        jp_parts.append(w_jp)
    # situation / remove は対訳。EN は *_en（無ければ JP でフォールバック）、JP は日本語。
    sit_en = info.situation_en or info.situation
    sit_jp = info.situation or info.situation_en
    if sit_en:
        en_parts.append("In this shot: " + _en_sentence(sit_en))
    if sit_jp:
        jp_parts.append(f"このカット: {sit_jp.rstrip('。')}。")
    rem_en = info.remove_en or info.remove
    rem_jp = info.remove or info.remove_en
    if rem_en:
        en_parts.append(f"Remove in this shot: {rem_en.rstrip('。.')}; keep the surrounding environment.")
    if rem_jp:
        jp_parts.append(f"このカットで消すもの: {rem_jp.rstrip('。')}。周囲の環境は残す。")
    en = ("[CUT] " + " ".join(en_parts)) if en_parts else ""
    jp = ("[カット] " + " ".join(jp_parts)) if jp_parts else ""
    return en, jp


def assemble(info: CutInfo, profile: SceneProfile | None,
             staging: str | None = None, genzu_trust: str = "rough") -> Prompt:
    # genzu_trust: "rough"=修正パス（原図に狂いがある前提・尚善） /
    #              "high"=忠実清書（原図の幾何が正・SP2の3Dレイアウト原図）
    faithful = genzu_trust == "high"
    en_blocks = [GLOBAL_TRUST_EN if faithful else GLOBAL_EN]
    jp_blocks = [GLOBAL_TRUST_JP if faithful else GLOBAL_JP]
    if staging:
        # staging がある時はコンテ由来の situation を落とす（stagingが上位互換＝OCR誤読の混入も防ぐ）
        info = replace(info, situation="", situation_en="")
    if staging:
        # 画角・場面の言語記述（人間指定 or scene_understanding 生成）。
        # 画像参照では構図を拘束できない（SP2実測）ため、これが構図の主チャンネル。
        # 日本語のままでも通る（黒江さんの手書きプロンプトで実証済み）。
        en_blocks.append("[SHOT — specified by the art director, TOP PRIORITY] " + staging.strip())
        jp_blocks.append("[画角・場面（指定・最優先）] " + staging.strip())
    if profile:
        en_blocks.append(profile.block_en())
        jp_blocks.append(profile.block_jp())
    elif info.place:
        # プロファイル未整備でも place だけは渡す（最低限の B 層）
        en_blocks.append(
            f"[SCENE] Setting: {info.place} — {info.era or DEFAULT_ERA_EN}. "
            "This names the location for context only — it does not license adding "
            "anything the layout does not show.")
        jp_blocks.append(
            f"[シーン] 舞台: {info.place}（{info.era or DEFAULT_ERA_JP}）。"
            "これは場所の文脈情報であり、原図に無いものを描く根拠にはならない。")
    c_en, c_jp = _cut_block(info)
    if c_en:
        en_blocks.append(c_en)
    if c_jp:
        jp_blocks.append(c_jp)
    return Prompt(en="\n\n".join(en_blocks), jp="\n\n".join(jp_blocks), info=info)


def build(board: str, scene: str, registry: SceneRegistry | None = None,
          cut: str = "", staging: str | None = None, genzu_trust: str = "rough") -> Prompt:
    """表口: ボード名 + シーン名から EN/JP プロンプトの対を組み立てる。"""
    registry = registry or SceneRegistry.load()
    info = cut_info_from_board(board, scene, registry, cut=cut)
    prof = registry.resolve(board, scene)
    return assemble(info, prof, staging=staging, genzu_trust=genzu_trust)


def build_from_info(info: CutInfo, registry: SceneRegistry | None = None,
                    staging: str | None = None, genzu_trust: str = "rough") -> Prompt:
    """充足済み CutInfo（cut_scene_info_ep7.csv の行など）からプロンプトを組む。"""
    registry = registry or SceneRegistry.load()
    prof = next((p for p in registry.profiles if p.key == info.scene_key), None)
    return assemble(info, prof, staging=staging, genzu_trust=genzu_trust)


def _norm_cut(label: str) -> str:
    """カット番号キー（前ゼロを落とし枝番は保持）。例 '015'->'15', '016A'->'16A'。"""
    m = re.match(r"0*(\d+)([A-Za-z]?)$", (label or "").strip())
    return (m.group(1) + m.group(2).upper()) if m else (label or "").strip()


def load_cut_info(csv_path: str) -> dict[str, CutInfo]:
    """cut_scene_info CSV を cut 番号キーの CutInfo 辞書として読む（存在しなければ空）。"""
    if not csv_path or not os.path.exists(csv_path):
        return {}
    out = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            out[_norm_cut(row.get("cut", ""))] = CutInfo.from_row(row)
    return out


def build_for_cut(cut: str, board: str, scene: str,
                  registry: SceneRegistry | None = None,
                  cut_info_map: dict[str, CutInfo] | None = None,
                  staging: str | None = None, genzu_trust: str = "rough") -> Prompt:
    """カット番号があれば cut_scene_info の充足済み行（situation/remove 込み）を優先。
    無ければ board/scene から機械生成（situation/remove は空）。
    staging=画角・場面の言語記述（あれば最優先ブロックとして挿入）。
    genzu_trust="high"=原図の幾何を正とする忠実清書 / "rough"=修正パス。"""
    registry = registry or SceneRegistry.load()
    if cut_info_map:
        info = cut_info_map.get(_norm_cut(cut))
        if info:
            return build_from_info(info, registry, staging=staging, genzu_trust=genzu_trust)
    return build(board, scene, registry=registry, cut=cut, staging=staging,
                 genzu_trust=genzu_trust)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _gen_info(args) -> None:
    registry = SceneRegistry.load(args.profiles_dir)
    with open(args.csv, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if args.assignee:
        rows = [r for r in rows if r.get("assignee") == args.assignee]
    out_rows = []
    for r in rows:
        info = cut_info_from_board(r.get("board", ""), r.get("scene", ""),
                                   registry, cut=r.get("cut", ""))
        out_rows.append(info.to_row())
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CUT_INFO_FIELDS)
        w.writeheader()
        w.writerows(out_rows)
    filled = sum(1 for r in out_rows if r["scene_key"])
    print(f"wrote {args.out}: {len(out_rows)} cuts "
          f"({filled} matched a scene profile, "
          f"{len(out_rows) - filled} unmatched / no board)")


def _show(args) -> None:
    registry = SceneRegistry.load(args.profiles_dir)
    with open(args.csv, encoding="utf-8-sig") as f:
        rows = {r.get("cut"): r for r in csv.DictReader(f)}
    r = rows.get(str(args.cut))
    if not r:
        raise SystemExit(f"cut {args.cut} not found in {args.csv}")
    p = build(r.get("board", ""), r.get("scene", ""), registry, cut=str(args.cut))
    print(f"# cut {args.cut}  scene={r.get('scene')!r}  board={r.get('board')!r}\n")
    print("=== EN (model input) ===\n" + p.en)
    print("\n=== JP (review) ===\n" + p.jp)


def main(argv=None) -> None:
    import argparse
    ap = argparse.ArgumentParser(prog="genzu_fix.prompt",
                                 description="カット別プロンプトの組み立て・確認")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen-info", help="cut_board_map から cut_scene_info CSV を機械生成")
    g.add_argument("--csv", default="runs/cut_board_map_ep7.csv")
    g.add_argument("--assignee", default=None, help="担当で絞る（例 GKV）")
    g.add_argument("--out", default="runs/cut_scene_info_ep7.csv")
    g.add_argument("--profiles-dir", default=None)
    g.set_defaults(func=_gen_info)

    s = sub.add_parser("show", help="1カットの EN/JP プロンプトを表示")
    s.add_argument("--cut", required=True)
    s.add_argument("--csv", default="runs/cut_board_map_ep7.csv")
    s.add_argument("--profiles-dir", default=None)
    s.set_defaults(func=_show)

    a = ap.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
