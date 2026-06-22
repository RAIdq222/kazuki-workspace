"""生成結果のセルフチェック（検品）。

背景美術原図として成立しているかを判定し、合否とリテイク要否を出す。
「作りっぱなし」を防ぐための工程。検品結果は台帳に書き、ダッシュボードに出す。

チェック項目:
- has_content  : 真っ白/真っ黒でなく、線がある（プログラム判定）
- monochrome   : 白黒線画になっている（色が残っていない）（プログラム判定）
- no_subject   : 人物だけでなく「主体に付随するもの」も残っていない ← 背景美術として重要（AI視覚判定）
                 例: 人物・動物、その持ち物/得物(剣・槍・棒)・小道具・荷物、人物由来の影やエフェクト。
                 背景に元から在る固定物(建物・灯籠・据え置きの什器等)は対象外＝残してよい。
                 ※BGか付随物かの線引きは作品ごとに美術側と要相談。
- text_removed : 管理情報・手書き指示・ラベルが消えている（AI視覚判定）
- framing_kept : 画角・構図が原図と一致（AI視覚判定）

プログラム判定だけ自動で行い、視覚判定は vision_verdicts(dict) として外から渡す
（本番は GPT/Claude 等の視覚モデル呼び出しで自動化する＝AI充足判定）。
"""
from __future__ import annotations
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
