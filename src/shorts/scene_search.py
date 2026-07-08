"""シーンライブラリのセマンティック検索CLI（生成フロー用）。

クエリをローカルで Gemini 埋め込み（RETRIEVAL_QUERY・768次元・L2正規化）し、
ダッシュボードの agent API に qvec として渡してコサイン検索する。
Worker の egress 制限（エージェント文脈は外部API不可）を迂回する正規ルート。

使い方:
    python3 -m src.shorts.scene_search "いただきますしているシーン" --limit 5
    python3 -m src.shorts.scene_search "怒っている顔" --place 部屋 --min-quality 3

前提: work/agent_token.txt と work/gemini_api_key.txt（どちらもgit管理外）。
埋め込みモデルはアプリ側の CURRENT_EMBEDDING_MODEL と一致させること
（現在: gemini-embedding-001@768）。
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import struct
import subprocess
import tempfile
from urllib.parse import quote

APP = "https://summer-bell-707.higgsfield.app"
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/"
              "models/gemini-embedding-001:embedContent")
DIM = 768


def _read(path: str) -> str:
    return open(os.path.join(ROOT, path)).read().strip()


def _curl_json(url: str, method: str = "GET", body: dict | None = None,
               headers: dict | None = None) -> dict:
    cmd = ["curl", "-sS", "-m", "60", "-X", method, url,
           "-H", "Content-Type: application/json", "-w", "\n%{http_code}"]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    tmp = None
    try:
        if body is not None:
            tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
            json.dump(body, tmp)
            tmp.close()
            cmd += ["--data-binary", f"@{tmp.name}"]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=90).stdout
        payload, _, code = out.rpartition("\n")
        if not code.startswith("2"):
            raise RuntimeError(f"HTTP {code}: {payload[:300]}")
        return json.loads(payload)
    finally:
        if tmp:
            os.unlink(tmp.name)


def embed_query(text: str) -> list[float]:
    res = _curl_json(GEMINI_URL, "POST",
                     {"model": "models/gemini-embedding-001",
                      "content": {"parts": [{"text": text}]},
                      "taskType": "RETRIEVAL_QUERY",
                      "outputDimensionality": DIM},
                     {"x-goog-api-key": _read("work/gemini_api_key.txt")})
    vec = res["embedding"]["values"]
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def search(query: str, limit: int = 5, place: str | None = None,
           action: str | None = None, min_quality: int | None = None) -> list[dict]:
    qvec = base64.urlsafe_b64encode(struct.pack(f"<{DIM}f", *embed_query(query))).decode()
    url = f"{APP}/api/agent/scenes?q={quote(query)}&qvec={qvec}&limit={limit}"
    if place:
        url += f"&place={quote(place)}"
    if action:
        url += f"&action={quote(action)}"
    if min_quality:
        url += f"&min_quality={min_quality}"
    res = _curl_json(url, headers={
        "Authorization": f"Bearer {_read('work/agent_token.txt')}"})
    return res.get("scenes") or res.get("results") or []


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("query", help="自然文クエリ（例: 寝てる顔）")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--place", default=None)
    ap.add_argument("--action", default=None)
    ap.add_argument("--min-quality", type=int, default=None)
    ap.add_argument("--json", action="store_true", help="生JSONで出力")
    args = ap.parse_args()

    items = search(args.query, args.limit, args.place, args.action, args.min_quality)
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=1))
        return
    if not items:
        print("0件（セマンティック足切り0.3未満か、ファセット不一致）")
        return
    for it in items:
        print(f"score={it.get('score')} [{it.get('episode')}] "
              f"{it.get('place')}/{it.get('action')}/{it.get('expression')}/{it.get('shot')} "
              f"q{it.get('quality')} t={it.get('t_start')}s media={it.get('frame_media_id')}\n"
              f"  {it.get('caption')}")


if __name__ == "__main__":
    main()
