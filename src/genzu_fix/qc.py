"""生成結果のセルフチェック（検品）。

背景美術原図として成立しているかを判定し、合否とリテイク要否を出す。
「作りっぱなし」を防ぐための工程。検品結果は台帳に書き、ダッシュボードに出す。

チェック項目:
- has_content  : 真っ白/真っ黒でなく、線がある（プログラム判定）
- monochrome   : 白黒線画になっている（色が残っていない）（プログラム判定）
- no_subject   : 「主体（キャラ）に属するもの」が残っていない ← 背景美術として重要（AI視覚判定）
                 消す＝主体に属するもの: 人物・動物そのもの、人物が持つ/身につける/連れている物
                   (持っている本・得物・荷物・装備)、人物由来の影やエフェクト。
                 残す＝環境に属するもの: その場所の一部である物。可動か固定かは無関係
                   (例: 棚に並ぶ本は残す／人物が持つ本は消す)。
                 ※「主体に属する/環境に属する」の判断は絵コンテ・美術ボードの文脈が要る場合が多い。
                 ※注意: 主体が画面下を覆う構図(膝上等)では、隠れた背景は原図に描かれていない。
                   消した跡を生成で“補完”すると捏造になる。BGonly素材やボード/コンテに基づくべき。
- text_removed : 管理情報・手書き指示・ラベルが消えている（AI視覚判定）
- framing_kept : 画角・構図が原図と一致（AI視覚判定）

プログラム判定だけ自動で行い、視覚判定は vision_verdicts(dict) として外から渡す
（本番は GPT/Claude 等の視覚モデル呼び出しで自動化する＝AI充足判定）。
"""
from __future__ import annotations
import os
import re
from dataclasses import dataclass, field, asdict


@dataclass
class QCResult:
    checks: dict = field(default_factory=dict)   # 各項目 True/False/None(未判定)
    verdict: str = "unknown"                      # pass / needs_retake / human / unknown
    reasons: list = field(default_factory=list)


def check_monochrome(path: str, sat_threshold: int = 18) -> bool:
    """平均彩度が低ければ白黒とみなす。"""
    from PIL import Image
    im = Image.open(path).convert("RGB").resize((256, 256))
    hsv = im.convert("HSV")
    s = hsv.split()[1]
    mean_s = sum(s.getdata()) / (256 * 256)
    return mean_s < sat_threshold


def check_has_content(path: str, lo: float = 0.005, hi: float = 0.7) -> bool:
    """インク被覆率が妥当な範囲（真っ白でも真っ黒でもない）か。"""
    from PIL import Image
    im = Image.open(path).convert("L").resize((256, 256))
    dark = sum(1 for p in im.getdata() if p < 200) / (256 * 256)
    return lo < dark < hi


# 視覚判定が必要な項目（本番は vision モデルで自動化）
VISION_KEYS = ("no_subject", "text_removed", "framing_kept")


def evaluate(image_path: str, vision_verdicts: dict | None = None) -> QCResult:
    vv = vision_verdicts or {}
    checks = {
        "has_content": check_has_content(image_path),
        "monochrome": check_monochrome(image_path),
    }
    for k in VISION_KEYS:
        checks[k] = vv.get(k)  # True/False/None

    reasons = []
    verdict = "pass"
    if not checks["has_content"]:
        verdict = "human"; reasons.append("中身が異常（空白/破綻）")
    else:
        if checks["no_subject"] is False:
            verdict = "needs_retake"
            reasons.append("人物・付随物（持ち物/小道具/影など）が残っている（背景美術NG）")
        if not checks["monochrome"]:
            verdict = "needs_retake"; reasons.append("色が残っている")
        if checks["text_removed"] is False:
            verdict = "needs_retake"; reasons.append("文字/指示が残っている")
        if checks["framing_kept"] is False:
            verdict = "needs_retake"; reasons.append("画角が変わった")
    return QCResult(checks=checks, verdict=verdict, reasons=reasons)


# --- 視覚判定（opt-in）。原図(before)と生成結果(after)を Claude に見せて3項目を判定する。
#     ANTHROPIC_API_KEY が要る。失敗時は {} を返し、プログラム判定だけで評価される。 ---
_VISION_MODEL = os.environ.get("QC_VISION_MODEL", "claude-sonnet-5")


def _b64_downscaled(path: str, maxside: int = 1024) -> str:
    from PIL import Image
    import base64
    import io
    im = Image.open(path).convert("RGB")
    if max(im.size) > maxside:
        s = maxside / max(im.size)
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def vision_check(genzu_path: str, result_path: str, model: str | None = None,
                 timeout: int = 120) -> dict:
    """原図と生成結果を見比べ {no_subject, text_removed, framing_kept} を True/False で返す。
    キー未取得は None。API未設定/失敗時は {}（＝プログラム判定のみで評価）。"""
    import json as _json
    import urllib.request
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {}
    prompt = (
        "アニメ背景美術の検品です。IMAGE1=ラフ原図(入力)、IMAGE2=生成された白黒線画(結果)。"
        "結果について次をJSONで判定してください（true/false、確信が持てなければ null）。"
        '{"no_subject": 人物やその持ち物/影が結果に残っていない=true, '
        '"text_removed": 手書き指示・ラベル・管理ヘッダー・タップ穴が消えている=true, '
        '"framing_kept": 構図・画角が原図と一致している=true}。JSONのみ返す。')
    body = {
        "model": model or _VISION_MODEL, "max_tokens": 300,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "IMAGE1 (原図):"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": _b64_downscaled(genzu_path)}},
            {"type": "text", "text": "IMAGE2 (生成結果):"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": _b64_downscaled(result_path)}},
            {"type": "text", "text": prompt}]}]}
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=_json.dumps(body).encode(),
        headers={"content-type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = _json.loads(r.read())
        text = "".join(b.get("text", "") for b in data.get("content", []))
        m = re.search(r"\{.*\}", text, re.S)
        obj = _json.loads(m.group(0)) if m else {}
    except Exception:
        return {}
    return {k: obj.get(k) for k in VISION_KEYS if k in obj}
