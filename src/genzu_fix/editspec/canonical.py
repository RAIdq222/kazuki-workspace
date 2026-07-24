"""正準JSON化とハッシュ — EditSpec の content_hash / spec_hash。

方式 "rfc8785-subset/1" = RFC 8785 (JCS) のサブセット:
  - オブジェクトキーは文字列のみ・昇順、区切りに空白なし、ensure_ascii=False
  - 数値は**整数のみ**（floatは順序・表現の実装差が出るため仕様で禁止。%座標も整数で書く）
  - キーにBMP外の文字を使わない（PythonのソートはUnicodeコードポイント順で、
    JCSのUTF-16コード単位順とはBMP外文字を含むキーで差が出うるため）
この制約下で RFC 8785 と一致する。方式名はspecの hash_spec に記録され、
将来方式を変える場合は名前を変える（黙って挙動を変えない）。
"""
from __future__ import annotations

import hashlib
import json

HASH_SPEC = {"canonicalization": "rfc8785-subset/1", "digest": "sha-256"}


def _check(obj, path="$"):
    if isinstance(obj, bool) or obj is None or isinstance(obj, int):
        return
    if isinstance(obj, float):
        raise TypeError(f"float禁止（rfc8785-subset/1）: {path}={obj!r}。整数で表現する")
    if isinstance(obj, str):
        return
    if isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _check(v, f"{path}[{i}]")
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise TypeError(f"キーは文字列のみ: {path}.{k!r}")
            if any(ord(c) > 0xFFFF for c in k):
                raise ValueError(f"キーにBMP外文字は不可: {path}.{k!r}")
            _check(v, f"{path}.{k}")
        return
    raise TypeError(f"正準化できない型 {type(obj).__name__}: {path}")


def canonical_json(obj) -> str:
    _check(obj)
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def digest(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def assertion_content_hash(a: dict) -> str:
    """承認が指す内容のhash。{subject, content, evidence_refs} をrev限定済みの形で。
    derivation・review・validationは含めない（履歴追記・審査で内容hashは変わらない）。"""
    return digest({
        "subject": a.get("subject"),
        "content": a.get("content"),
        "evidence_refs": (a.get("provenance") or {}).get("evidence_refs", []),
    })


def spec_hash(spec: dict) -> str:
    """spec全体のhash。埋め込みvalidationキャッシュは除外して計算する。"""
    return digest({k: v for k, v in spec.items() if k != "validation"})
