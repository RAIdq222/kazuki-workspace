"""policy評価器 — 診断（validator）とprofile（業務判断の置き場）から生成可否を導出する。

Issue #5 の確定事項:
  - validationは事実、policyは判断。D4〜D7の黒江さん回答はここ（profile）だけが消費する
  - 既定は non-blocking（R12: 業務的不確実性だけを理由に止めない）
  - block は2種を区別: invalid_spec（技術的不整合）/ policy（明示的な人の保留など）
  - 決定は allow / allow_with_disclosure / block。disclosureの中身はreasonsで返す
    （UI側はこれを使って「未確認情報を使用」「原図vsコンテの食い違いを解決済み」等を
    赤字などで人が気づける形に表示する＝D4/D5のアラート要件）

profileはJSON（runs/policy_profiles/<work>_<ep>.json）。値は全て業務判断であり、
コードに埋め込む既定（DEFAULT_PROFILE）はSP2#10のD回答を写しただけの初期値。
"""
from __future__ import annotations

import json
import os

from .canonical import digest, spec_hash

# SP2#10 初期profile（Issue #5 D4〜D7回答の写し。変更は黒江さん判断）
DEFAULT_PROFILE = {
    "profile": "sp2_10",
    "version": "0.1",
    # D5: 同一対象・同一性質の宣言競合はこの順で解決（競合assertion単位。全面trustではない）
    "precedence_on_declaration_conflict": ["human", "genzu", "conte", "board", "model"],
    # ブロック条件（これ以外では止めない）
    "block_on_invalid_spec": True,          # error級診断
    "block_on_human_hold": True,            # 人がblocking_candidateを付けた未決
    # 開示（allow_with_disclosure）のトリガ
    "disclose_on_codes": [
        "SHEET_NOTE_UNTRIAGED", "OUTDATED_REFERENCE", "UNRESOLVED_PRESENT",
        "CRITICAL_UNREVIEWED_INFERENCE", "COVERAGE_UNREVIEWED_MODEL_FULL",
        "REMOVE_WITHOUT_REBUILD_PLAN", "MATERIAL_REV_UNKNOWN", "REBUILD_LINK_CANDIDATE",
    ],
    "disclose_on_unreviewed_inference": True,   # D6: 未確認推論での生成は許可＋開示
    "unresolved_default": "default_preserve_with_disclosure",  # D7
    "sheet_notes_mode": "model_proposes_human_approves",       # D4=b
    "trust_display": "derived_only",            # カット一括trustは表示専用の派生値のみ
    "retake_loop": {"retry_budget": 2, "escalate_on_no_improvement": True},  # T9初期契約
}


def load_profile(path_or_id: str | None = None) -> dict:
    """profileを読む。パス指定→JSON、None/不在→DEFAULT_PROFILE。"""
    if path_or_id and os.path.exists(path_or_id):
        with open(path_or_id, encoding="utf-8") as f:
            return json.load(f)
    return dict(DEFAULT_PROFILE)


def _human_holds(spec: dict) -> list[str]:
    out = []
    for a in spec.get("assertions", []):
        if ((a.get("content") or {}).get("kind") == "knowledge"
                and (a.get("criticality") or {}).get("value") == "blocking_candidate"
                and ((a.get("criticality") or {}).get("set_by") or {}).get("kind") == "human"
                and (a.get("review") or {}).get("state") != "rejected"):
            out.append(a.get("id"))
    return sorted(out)


def _unreviewed_inferences(spec: dict) -> list[str]:
    out = []
    for a in spec.get("assertions", []):
        if ((a.get("provenance") or {}).get("derivation_mode") in ("interpreted", "inferred")
                and (a.get("review") or {}).get("state") == "unreviewed"):
            out.append(a.get("id"))
    return sorted(out)


def evaluate(spec: dict, validation_report: dict, profile: dict | None = None) -> dict:
    """policy_evaluation_report を返す。validationの再計算はしない（入力の鮮度は呼び手が保証。
    ただしhash不一致は検出してblockする＝古い診断で判断しない）。"""
    profile = profile or DEFAULT_PROFILE
    report = {
        "policy_ref": f"{profile.get('profile')}@{profile.get('version')}",
        "validation_report_hash": digest(validation_report),
        "spec_hash": spec_hash(spec),
        "decision": "allow",
        "reasons": [],
    }
    if validation_report.get("validated_spec_hash") != report["spec_hash"]:
        report.update(decision="block", block_kind="invalid_spec",
                      reasons=["VALIDATION_STALE: 診断が現在のspecを指していない"])
        return report

    diags = validation_report.get("diagnostics", [])
    errors = sorted({d["code"] for d in diags if d.get("technical_level") == "error"})
    if errors and profile.get("block_on_invalid_spec", True):
        report.update(decision="block", block_kind="invalid_spec", reasons=errors)
        return report

    holds = _human_holds(spec)
    if holds and profile.get("block_on_human_hold", True):
        report.update(decision="block", block_kind="policy",
                      reasons=[f"HUMAN_HOLD:{i}" for i in holds])
        return report

    reasons = []
    disclose_codes = set(profile.get("disclose_on_codes", []))
    reasons += sorted({d["code"] for d in diags if d["code"] in disclose_codes})
    if profile.get("disclose_on_unreviewed_inference", True):
        inf = _unreviewed_inferences(spec)
        if inf:
            reasons.append("UNREVIEWED_INFERENCE_USED:" + ",".join(inf))
    if reasons:
        report.update(decision="allow_with_disclosure", reasons=reasons)
    return report
