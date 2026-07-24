"""決定論バリデータ（T2 v0.2）— EditSpecの技術診断。policy非依存・冪等・安定ソート。

原則:
  - 同じspecには常に同じ診断を返す（LLM不使用・時刻不使用）
  - 診断は観測事実のみ。technical_levelは固定で、生成可否の判断はpolicy.pyへ
  - モデルの認識・解釈（赤書きの合理性等）はassertionとして表現され、ここでは扱わない
    （扱うのは「未トリアージ」「未審査」「低confidence状態」といった構造上の事実まで）

診断コード台帳はIssue #5 T2 v0.2で固定（19件）。levelは error / warning / note。
"""
from __future__ import annotations

from .canonical import assertion_content_hash, spec_hash

VALIDATOR_VERSION = "0.2.0"

# --- 語彙（T1 v0.3 コア閉集合） ---
OPERATIONS = {
    "preserve_geometry", "refine_linework", "repair_geometry",
    "remove", "reconstruct_occluded", "add_from_reference",
}
EVIDENCE_REQUIRED_OPS = {"repair_geometry", "reconstruct_occluded", "add_from_reference"}
PRESENCE_OPS = {"remove", "add_from_reference", "reconstruct_occluded"}
GEOMETRY_OPS = {"preserve_geometry", "repair_geometry"}

DECLARATION_TYPES = {
    "camera_position", "camera_direction", "camera_angle", "framing",
    "relation", "keep_empty", "keep_sparse",
}
EXCLUSIVE_DECLS = {"camera_position", "camera_direction", "camera_angle", "framing"}
RELATION_INVERSE = {
    "in_front_of": "behind", "behind": "in_front_of",
    "left_of": "right_of", "right_of": "left_of",
    "above": "below", "below": "above",
}
DERIVATION_MODES = {"direct_import", "deterministic_transform", "interpreted", "inferred"}
REVIEW_STATES = {"unreviewed", "approved", "rejected"}
CONTENT_KINDS = {"edit", "declaration", "knowledge"}
SUBJECT_SCOPES = {"element", "view", "relation", "region", "canvas"}


def _d(code, level, message, related=(), paths=()):
    return {"code": code, "technical_level": level, "message": message,
            "related_ids": sorted(related), "paths": sorted(paths)}


def _is_ext(name) -> bool:
    return isinstance(name, str) and name.startswith("x_")


def _bbox_overlap(r1, r2) -> bool:
    """bbox_pct [x0,y0,x1,y1] 同士の重なり。bbox以外の表現はここでは判定しない。"""
    if not r1 or not r2 or r1.get("kind") != "bbox_pct" or r2.get("kind") != "bbox_pct":
        return False
    a, b = r1.get("value") or [], r2.get("value") or []
    if len(a) != 4 or len(b) != 4:
        return False
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def validate(spec: dict) -> dict:
    """spec → validation_report（policy非依存）。"""
    diags: list[dict] = []
    materials = {m.get("id"): m for m in spec.get("materials", []) if isinstance(m, dict)}
    elements = {e.get("id"): e for e in spec.get("elements", []) if isinstance(e, dict)}
    spaces = {s.get("id"): s for s in spec.get("coordinate_spaces", []) if isinstance(s, dict)}
    assertions = [a for a in spec.get("assertions", []) if isinstance(a, dict)]

    # --- 層1: 構文・参照整合 ---
    for name, table in (("materials", materials), ("elements", elements),
                        ("coordinate_spaces", spaces)):
        ids = [x.get("id") for x in spec.get(name, []) if isinstance(x, dict)]
        for i in {i for i in ids if ids.count(i) > 1}:
            diags.append(_d("ID_DUPLICATE", "error", f"{name}のid重複: {i}", related=[i]))
    aids = [a.get("id") for a in assertions]
    for i in {i for i in aids if aids.count(i) > 1}:
        diags.append(_d("ID_DUPLICATE", "error", f"assertionのid重複: {i}", related=[i]))

    def check_ref(ref_obj, owner_id, kinds=("material", "element", "assertion")):
        """{ref, revision} 参照の存在とrevision整合。"""
        if not isinstance(ref_obj, dict) or "ref" not in ref_obj:
            diags.append(_d("SCHEMA_VIOLATION", "error",
                            f"参照は{{ref, revision}}形式: {ref_obj!r}", related=[owner_id]))
            return
        rid = ref_obj["ref"]
        target = None
        if "material" in kinds and rid in materials:
            target = materials[rid]
        elif "element" in kinds and rid in elements:
            target = elements[rid]
        elif "assertion" in kinds:
            target = next((a for a in assertions if a.get("id") == rid), None)
        if target is None and rid not in spaces:
            diags.append(_d("REF_NOT_FOUND", "error", f"参照先が無い: {rid}",
                            related=[owner_id, str(rid)]))
            return
        pinned = ref_obj.get("revision")
        cur = (target or spaces.get(rid, {})).get("revision", 1)
        if pinned is not None and isinstance(cur, int) and isinstance(pinned, int) and cur > pinned:
            diags.append(_d("OUTDATED_REFERENCE", "warning",
                            f"{rid} は revision {cur} が存在（参照は {pinned} を固定）",
                            related=[owner_id, str(rid)]))

    base = spec.get("base") or {}
    cs = base.get("coordinate_space_id")
    if isinstance(cs, dict):
        if (cs.get("ref")) not in spaces:
            diags.append(_d("COORD_SPACE_UNRESOLVED", "error",
                            f"base.coordinate_space_id 参照不能: {cs.get('ref')!r}"))
    elif cs is not None and cs not in spaces:
        diags.append(_d("COORD_SPACE_UNRESOLVED", "error",
                        f"base.coordinate_space_id 参照不能: {cs!r}"))

    for mid, m in materials.items():
        if (m.get("rev") or "unknown") == "unknown":
            diags.append(_d("MATERIAL_REV_UNKNOWN", "note", f"資料rev不明: {mid}", related=[mid]))
        if m.get("kind") != "genzu_base" and not m.get("space_ref"):
            diags.append(_d("MATERIAL_SPACE_REF_MISSING", "note",
                            f"資料にspace_ref未定義: {mid}", related=[mid]))

    v = spec.get("validation")
    if isinstance(v, dict) and not v.get("validator_version"):
        diags.append(_d("VALIDATION_FIELD_HANDWRITTEN", "error",
                        "spec内validationにvalidator_versionが無い（手書きの疑い）"))

    # --- 層1続き＋層2: assertion単位の検査 ---
    for a in assertions:
        aid = a.get("id", "?")
        subj = a.get("subject") or {}
        cont = a.get("content") or {}
        prov = a.get("provenance") or {}
        review = a.get("review") or {}

        for field in ("id", "revision", "subject", "content", "provenance", "review"):
            if not a.get(field):
                diags.append(_d("SCHEMA_VIOLATION", "error", f"必須field欠落: {field}", related=[aid]))
        if subj.get("scope") not in SUBJECT_SCOPES:
            diags.append(_d("SCHEMA_VIOLATION", "error",
                            f"subject.scope不正: {subj.get('scope')!r}", related=[aid]))
        if cont.get("kind") not in CONTENT_KINDS:
            diags.append(_d("SCHEMA_VIOLATION", "error",
                            f"content.kind不正: {cont.get('kind')!r}", related=[aid]))
        if subj.get("scope") == "element" and not subj.get("target"):
            diags.append(_d("SCHEMA_VIOLATION", "error", "scope=elementにtarget無し", related=[aid]))
        if subj.get("scope") == "relation" and len(subj.get("ref") or []) != 2:
            diags.append(_d("SCHEMA_VIOLATION", "error", "scope=relationはref 2件必須", related=[aid]))

        if subj.get("target"):
            check_ref(subj["target"], aid, kinds=("element",))
        for r in subj.get("ref") or []:
            check_ref(r, aid, kinds=("element",))
        for r in prov.get("evidence_refs") or []:
            check_ref(r, aid)
        region = subj.get("region")
        if isinstance(region, dict) and isinstance(region.get("space"), dict):
            check_ref(region["space"], aid, kinds=())

        # content種別ごとの語彙
        if cont.get("kind") == "edit":
            op = cont.get("operation")
            if op in OPERATIONS:
                pass
            elif _is_ext(op):
                diags.append(_d("UNKNOWN_EXTENSION_NOT_EVALUATED", "note",
                                f"拡張操作 {op}（評価されない）", related=[aid]))
            else:
                diags.append(_d("SCHEMA_VIOLATION", "error", f"操作不明: {op!r}", related=[aid]))
            if op in EVIDENCE_REQUIRED_OPS and not (prov.get("evidence_refs")):
                diags.append(_d("MISSING_EVIDENCE", "error",
                                f"{op} に権威資料のevidenceが無い", related=[aid]))
            rref = (cont.get("params") or {}).get("rebuild_ref")
            if rref:
                check_ref(rref, aid, kinds=("assertion",))
        elif cont.get("kind") == "declaration":
            dtype = (cont.get("declaration") or {}).get("type")
            if dtype in DECLARATION_TYPES:
                if dtype in ("keep_empty", "keep_sparse") and not subj.get("region"):
                    diags.append(_d("SCHEMA_VIOLATION", "error",
                                    f"{dtype} はsubject.region必須", related=[aid]))
            elif _is_ext(dtype):
                diags.append(_d("UNKNOWN_EXTENSION_NOT_EVALUATED", "note",
                                f"拡張宣言 {dtype}（評価されない）", related=[aid]))
            else:
                diags.append(_d("SCHEMA_VIOLATION", "error", f"宣言型不明: {dtype!r}", related=[aid]))
        elif cont.get("kind") == "knowledge":
            crit = (a.get("criticality") or {}).get("value", "")
            diags.append(_d("UNRESOLVED_PRESENT", "note",
                            f"未決定の記録あり（criticality={crit or '未指定'}）", related=[aid]))

        # provenance / confidence
        mode = prov.get("derivation_mode")
        if mode not in DERIVATION_MODES:
            diags.append(_d("SCHEMA_VIOLATION", "error",
                            f"derivation_mode不正: {mode!r}", related=[aid]))
        elif mode in ("interpreted", "inferred") and not a.get("confidence"):
            diags.append(_d("SCHEMA_VIOLATION", "error",
                            f"{mode} はconfidence必須", related=[aid]))

        # review / 承認の鮮度
        st = review.get("state")
        if st not in REVIEW_STATES:
            diags.append(_d("SCHEMA_VIOLATION", "error", f"review.state不正: {st!r}", related=[aid]))
        if st == "approved":
            cur_hash = assertion_content_hash(a)
            if (review.get("approved_hash") not in (None, cur_hash)
                    or (review.get("approved_revision") is not None
                        and review.get("approved_revision") != a.get("revision"))):
                diags.append(_d("STALE_APPROVAL", "error",
                                "承認が現在の内容を指していない（hash/revision不一致）", related=[aid]))

        if ((a.get("criticality") or {}).get("value") in ("major", "blocking_candidate")
                and mode in ("interpreted", "inferred") and st == "unreviewed"):
            diags.append(_d("CRITICAL_UNREVIEWED_INFERENCE", "warning",
                            "重要度の高い推論が未審査", related=[aid]))

    live = [a for a in assertions if (a.get("review") or {}).get("state") != "rejected"]

    # --- 層3: 意味矛盾 ---
    # 排他宣言の不一致（非rejected同士）
    for dtype in sorted(EXCLUSIVE_DECLS):
        decls = [a for a in live
                 if (a.get("content") or {}).get("kind") == "declaration"
                 and ((a.get("content") or {}).get("declaration") or {}).get("type") == dtype
                 and (a.get("subject") or {}).get("scope") == "view"]
        values = {assertion_content_hash(a): a for a in decls}
        vals = [((a.get("content") or {}).get("declaration") or {}).get("value") for a in decls]
        uniq = [v for i, v in enumerate(vals) if v not in vals[:i]]
        if len(uniq) > 1:
            diags.append(_d("SAME_DECLARATION_DISAGREES", "error",
                            f"{dtype}: 排他宣言の不一致 {uniq!r}",
                            related=[a.get('id') for a in decls]))
        _ = values

    # 操作の衝突（同一target・効果領域）
    by_target: dict[str, list] = {}
    for a in live:
        if (a.get("content") or {}).get("kind") != "edit":
            continue
        t = ((a.get("subject") or {}).get("target") or {}).get("ref")
        if t:
            by_target.setdefault(t, []).append(a)
    for t, group in sorted(by_target.items()):
        ops = {(a.get("content") or {}).get("operation"): a for a in group}
        pres = sorted(o for o in ops if o in PRESENCE_OPS)
        geom = sorted(o for o in ops if o in GEOMETRY_OPS)
        if len(pres) > 1:
            diags.append(_d("OPERATION_CONFLICT", "error",
                            f"target {t}: presence操作の排他違反 {pres}",
                            related=[ops[o].get("id") for o in pres]))
        if len(geom) > 1:
            diags.append(_d("OPERATION_CONFLICT", "error",
                            f"target {t}: geometry操作の排他違反 {geom}",
                            related=[ops[o].get("id") for o in geom]))
        if "remove" in ops and "refine_linework" in ops:
            diags.append(_d("OPERATION_CONFLICT", "error",
                            f"target {t}: remove と refine_linework は両立しない",
                            related=[ops["remove"].get("id"), ops["refine_linework"].get("id")]))

    # relationの逆関係矛盾・循環
    rels = {}
    for a in live:
        c = a.get("content") or {}
        if c.get("kind") == "declaration" and (c.get("declaration") or {}).get("type") == "relation":
            refs = [(r or {}).get("ref") for r in (a.get("subject") or {}).get("ref") or []]
            val = (c.get("declaration") or {}).get("value")
            if len(refs) == 2 and val:
                rels.setdefault((refs[0], refs[1]), []).append((val, a.get("id")))
    for (x, y), pairs in sorted(rels.items()):
        for val, aid in pairs:
            inv = RELATION_INVERSE.get(val)
            if not inv:
                continue
            for val2, aid2 in pairs:
                if val2 == inv:
                    diags.append(_d("RELATION_CONTRADICTION", "error",
                                    f"{x}-{y}: {val} と {val2} が同時に主張されている",
                                    related=[aid, aid2]))
            for val2, aid2 in rels.get((y, x), []):
                if val2 == val and val in RELATION_INVERSE:
                    diags.append(_d("RELATION_CONTRADICTION", "error",
                                    f"{x}/{y}: {val} が双方向に主張されている（循環）",
                                    related=[aid, aid2]))

    # keep_empty と add/reconstruct の領域衝突（bbox_pctのみ判定）
    keeps = [a for a in live if ((a.get("content") or {}).get("declaration") or {}).get("type")
             in ("keep_empty",)]
    adders = [a for a in live if (a.get("content") or {}).get("operation")
              in ("add_from_reference", "reconstruct_occluded")]
    for k in keeps:
        for ad in adders:
            if _bbox_overlap((k.get("subject") or {}).get("region"),
                             (ad.get("subject") or {}).get("region")):
                diags.append(_d("KEEP_EMPTY_VIOLATED_BY_SPEC", "error",
                                "keep_empty領域とadd/reconstructが衝突",
                                related=[k.get("id"), ad.get("id")]))

    # remove の跡地方針
    recon_by_bbox = [(a, (a.get("subject") or {}).get("region")) for a in adders
                     if (a.get("content") or {}).get("operation") == "reconstruct_occluded"]
    for a in live:
        if (a.get("content") or {}).get("operation") != "remove":
            continue
        aid = a.get("id")
        params = (a.get("content") or {}).get("params") or {}
        if params.get("rebuild_ref"):
            continue
        region = (a.get("subject") or {}).get("region")
        covered = any(_bbox_overlap(region, kr) for kr in
                      [(k.get("subject") or {}).get("region") for k in keeps])
        overlapping = [r for r, rr in recon_by_bbox if _bbox_overlap(region, rr)]
        if overlapping:
            diags.append(_d("REBUILD_LINK_CANDIDATE", "note",
                            "region重複するreconstructあり — rebuild_refで明示リンク推奨",
                            related=[aid] + [r.get("id") for r in overlapping]))
        if not covered and not overlapping:
            diags.append(_d("REMOVE_WITHOUT_REBUILD_PLAN", "note",
                            "removeに跡地方針（rebuild_ref/keep_empty/reconstruct）が無い",
                            related=[aid]))

    # --- 層4: 被覆・欠損・未トリアージ ---
    covs = spec.get("coverage") or []
    model_full_unreviewed = any(
        isinstance(c, dict) and c.get("scope") == "full"
        and (c.get("by") or {}).get("kind") == "model"
        and (c.get("review") or {}).get("state") != "approved" for c in covs)
    has_view_decl = any((a.get("subject") or {}).get("scope") == "view" for a in live)
    if model_full_unreviewed and not elements and has_view_decl:
        diags.append(_d("COVERAGE_UNREVIEWED_MODEL_FULL", "warning",
                        "model主張のfull coverageが未承認・要素ゼロ・視点宣言あり（基底が空の疑い）"))

    referenced_materials = {(r or {}).get("ref")
                            for a in assertions
                            for r in ((a.get("provenance") or {}).get("evidence_refs") or [])}
    for mid, m in sorted(materials.items()):
        if m.get("kind") == "sheet_note" and mid not in referenced_materials:
            diags.append(_d("SHEET_NOTE_UNTRIAGED", "warning",
                            f"赤書き資料 {mid} を参照・トリアージするassertionが無い", related=[mid]))

    diags.sort(key=lambda d: (d["code"], d["related_ids"], d["message"]))
    return {"validator_version": VALIDATOR_VERSION,
            "validated_spec_hash": spec_hash(spec),
            "diagnostics": diags}
