"""EditSpec バリデータ/policy のテスト — Issue #5 T2 v0.2 で固定した10ケース＋hash検査。

実行: PYTHONPATH=src python tests/editspec_test.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from genzu_fix.editspec import (  # noqa: E402
    assertion_content_hash, canonical_json, policy_evaluate, spec_hash, validate,
)


def base_spec(**over):
    spec = {
        "schema_version": "0.3",
        "id": "SP2-10-999",
        "hash_spec": {"canonicalization": "rfc8785-subset/1", "digest": "sha-256"},
        "materials": [
            {"id": "genzu", "kind": "genzu_base", "ref": "x.psd", "rev": "r1", "revision": 1},
            {"id": "board1", "kind": "board", "ref": "b.psd", "rev": "r1", "revision": 1,
             "space_ref": "board_space"},
        ],
        "coordinate_spaces": [{"id": "cs1", "kind": "full_canvas", "revision": 1}],
        "base": {"kind": "genzu_as_drawn", "material": {"ref": "genzu", "revision": 1},
                 "coordinate_space_id": "cs1"},
        "coverage": [{"scope": "full", "method": "visual_scan",
                      "by": {"kind": "human", "id": "kuroe"}, "review": {"state": "approved"}}],
        "elements": [{"id": "e1", "label": "灯具", "revision": 1},
                     {"id": "e2", "label": "支柱", "revision": 1}],
        "assertions": [],
    }
    spec.update(over)
    return spec


def A(id, **over):
    a = {
        "id": id, "revision": 1,
        "subject": {"scope": "element", "target": {"ref": "e1", "revision": 1}},
        "content": {"kind": "edit", "operation": "preserve_geometry"},
        "provenance": {"created_by": {"kind": "human", "id": "kuroe"},
                       "derivation_mode": "direct_import", "evidence_refs": [], "derivation": []},
        "review": {"state": "unreviewed"},
    }
    for k, v in over.items():
        a[k] = v
    return a


def codes(spec):
    return [d["code"] for d in validate(spec)["diagnostics"]]


def run():
    # hash: 決定性・validation除外・内容依存
    s = base_spec()
    assert spec_hash(s) == spec_hash(dict(s)), "spec_hash非決定"
    s2 = dict(s); s2["validation"] = {"validator_version": "x", "diagnostics": []}
    assert spec_hash(s) == spec_hash(s2), "validationキャッシュがhashに影響"
    a = A("a1")
    h1 = assertion_content_hash(a)
    a2 = A("a1"); a2["content"] = {"kind": "edit", "operation": "refine_linework"}
    assert h1 != assertion_content_hash(a2), "内容差がhashに出ない"
    try:
        canonical_json({"x": 1.5}); raise AssertionError("floatが通った")
    except TypeError:
        pass

    def view_decl(id, angle, mode="interpreted", conf=True, state="unreviewed"):
        a = A(id,
              subject={"scope": "view"},
              content={"kind": "declaration",
                       "declaration": {"type": "camera_angle", "value": {"value": angle}}})
        a["provenance"] = {"created_by": {"kind": "model", "id": "m"},
                           "derivation_mode": mode, "evidence_refs": [], "derivation": []}
        if conf:
            a["confidence"] = {"value": "low", "basis": "self_reported", "by": "m"}
        a["review"] = {"state": state}
        return a

    # (1) c274型: 排他宣言の不一致 → error、policyはblock(invalid_spec)
    s = base_spec(assertions=[view_decl("a1", "low_angle_up"),
                              view_decl("a2", "high_angle_down")])
    cs = codes(s)
    assert "SAME_DECLARATION_DISAGREES" in cs, cs
    rep = policy_evaluate(s, validate(s))
    assert rep["decision"] == "block" and rep["block_kind"] == "invalid_spec", rep

    # rejectedになれば衝突解消
    s = base_spec(assertions=[view_decl("a1", "low_angle_up"),
                              view_decl("a2", "high_angle_down", state="rejected")])
    assert "SAME_DECLARATION_DISAGREES" not in codes(s)

    # (2) 承認後の内容編集 → STALE_APPROVAL
    a = A("a1")
    a["review"] = {"state": "approved", "approved_revision": 1,
                   "approved_hash": assertion_content_hash(a)}
    a["content"] = {"kind": "edit", "operation": "refine_linework"}  # 承認後に書き換え
    s = base_spec(assertions=[a])
    assert "STALE_APPROVAL" in codes(s)

    # (3) model主張full coverage＋要素ゼロ＋視点宣言 → warning
    s = base_spec(elements=[],
                  coverage=[{"scope": "full", "method": "visual_scan",
                             "by": {"kind": "model", "id": "m"}, "review": {"state": "unreviewed"}}],
                  assertions=[view_decl("a1", "low_angle_up")])
    assert "COVERAGE_UNREVIEWED_MODEL_FULL" in codes(s)

    # (4) sheet_note未トリアージ → warning、policyは開示つき許可
    s = base_spec()
    s["materials"].append({"id": "note1", "kind": "sheet_note", "ref": "赤書き", "rev": "r1",
                           "revision": 1, "space_ref": "sheet"})
    assert "SHEET_NOTE_UNTRIAGED" in codes(s)
    rep = policy_evaluate(s, validate(s))
    assert rep["decision"] == "allow_with_disclosure" and "SHEET_NOTE_UNTRIAGED" in rep["reasons"], rep

    # (5) add に evidence無し → error
    s = base_spec(assertions=[A("a1", content={"kind": "edit", "operation": "add_from_reference",
                                               "params": {"reference": "board1"}})])
    assert "MISSING_EVIDENCE" in codes(s)

    # (6) 未知 x_宣言 → note扱い・SCHEMA violationにしない
    a = A("a1", subject={"scope": "view"},
          content={"kind": "declaration", "declaration": {"type": "x_kuroe_fisheye", "value": {}}})
    s = base_spec(assertions=[a])
    cs = codes(s)
    assert "UNKNOWN_EXTENSION_NOT_EVALUATED" in cs and "SCHEMA_VIOLATION" not in cs, cs

    # (7) preserve + refine 同一target → 両立（衝突なし）
    s = base_spec(assertions=[A("a1"), A("a2", content={"kind": "edit",
                                                        "operation": "refine_linework"})])
    assert "OPERATION_CONFLICT" not in codes(s)

    # (8) preserve + repair → 衝突 / remove + refine → 衝突
    rep_a = A("a2", content={"kind": "edit", "operation": "repair_geometry"})
    rep_a["provenance"]["evidence_refs"] = [{"ref": "board1", "revision": 1}]
    s = base_spec(assertions=[A("a1"), rep_a])
    assert "OPERATION_CONFLICT" in codes(s)
    s = base_spec(assertions=[A("a1", content={"kind": "edit", "operation": "remove"}),
                              A("a2", content={"kind": "edit", "operation": "refine_linework"})])
    assert "OPERATION_CONFLICT" in codes(s)

    # (9) remove + rebuild_ref付きreconstructペア → 跡地note無し
    rec = A("a2", subject={"scope": "element", "target": {"ref": "e2", "revision": 1},
                           "region": {"kind": "bbox_pct", "value": [10, 10, 30, 30]}},
            content={"kind": "edit", "operation": "reconstruct_occluded"})
    rec["provenance"]["evidence_refs"] = [{"ref": "board1", "revision": 1}]
    rm = A("a1", subject={"scope": "element", "target": {"ref": "e1", "revision": 1},
                          "region": {"kind": "bbox_pct", "value": [12, 12, 28, 28]}},
           content={"kind": "edit", "operation": "remove",
                    "params": {"rebuild_ref": {"ref": "a2", "revision": 1}}})
    s = base_spec(assertions=[rm, rec])
    cs = codes(s)
    assert "REMOVE_WITHOUT_REBUILD_PLAN" not in cs and "OPERATION_CONFLICT" not in cs, cs

    # (10) remove単独（跡地方針なし）→ note
    s = base_spec(assertions=[A("a1", content={"kind": "edit", "operation": "remove"})])
    assert "REMOVE_WITHOUT_REBUILD_PLAN" in codes(s)

    # 追加: 冪等・安定ソート / OUTDATED_REFERENCE / human_hold
    s = base_spec(assertions=[view_decl("a1", "low_angle_up")])
    assert validate(s) == validate(s), "非冪等"
    s = base_spec(elements=[{"id": "e1", "label": "灯具", "revision": 3}])
    s["assertions"] = [A("a1")]  # e1@1 を参照 → 後続revisionあり
    assert "OUTDATED_REFERENCE" in codes(s)
    hold = A("a9", subject={"scope": "canvas"},
             content={"kind": "knowledge", "knowledge": "unresolved"},
             criticality={"value": "blocking_candidate", "set_by": {"kind": "human", "id": "kuroe"}})
    s = base_spec(assertions=[hold])
    rep = policy_evaluate(s, validate(s))
    assert rep["decision"] == "block" and rep["block_kind"] == "policy", rep
    # 同じ未決でもmodel起源のcriticalityなら止めない（開示のみ）
    hold_m = A("a9", subject={"scope": "canvas"},
               content={"kind": "knowledge", "knowledge": "unresolved"},
               criticality={"value": "blocking_candidate", "set_by": {"kind": "model", "id": "m"}})
    s = base_spec(assertions=[hold_m])
    rep = policy_evaluate(s, validate(s))
    assert rep["decision"] == "allow_with_disclosure", rep

    print("editspec_test: all OK")


if __name__ == "__main__":
    run()
