"""EditSpec — 「何をどう修正するか」のモデル非依存データモデル（Issue #5 設計の実装）。

3層分離の中核: ①修正内容の決定（本モジュールが記録） ②プロンプト符号化（別モジュール・
D1手本待ち） ③評価（T3。qc.pyの後継）。生成側とQC側が**同じspec**を読む。

構成:
  canonical.py  正準JSON化とハッシュ（rfc8785-subset/1 + SHA-256）
  validator.py  決定論バリデータ（T2 v0.2。policy非依存の技術診断のみ）
  policy.py     policy評価器（診断＋profileから生成可否を導出。業務判断はここだけが消費）

規範（Issue #5で確定）:
  - validation は観測事実のみ。生成可否は policy が決める（allow / allow_with_disclosure / block）
  - 業務的不確実性だけを理由に既定では止めない（R12）。block は invalid_spec と明示的な人の保留のみ
  - モデルの認識・解釈（赤書きの読み等）は assertion であり、validator の客観診断に昇格させない
  - カット一括の genzu_trust は再導入しない。原図の正しさは性質ごとの assertion で表す
"""
from .canonical import HASH_SPEC, canonical_json, digest, assertion_content_hash, spec_hash
from .validator import validate, VALIDATOR_VERSION
from .policy import evaluate as policy_evaluate, load_profile, DEFAULT_PROFILE

__all__ = [
    "HASH_SPEC", "canonical_json", "digest", "assertion_content_hash", "spec_hash",
    "validate", "VALIDATOR_VERSION", "policy_evaluate", "load_profile", "DEFAULT_PROFILE",
]
