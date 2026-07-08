"""335シーンをGeminiで埋め込み → agent APIでBLOB書き込み → セマンティック検索を実測。"""
import base64, json, struct, math, time, subprocess, tempfile, os

APP = "https://summer-bell-707.higgsfield.app"
TOKEN = open("/home/user/kazuki-workspace/work/agent_token.txt").read().strip()
GKEY = open("/home/user/kazuki-workspace/work/gemini_api_key.txt").read().strip()
GURL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents"
MODEL = "gemini-embedding-001@768"

def http(url, method="GET", body=None, headers=None, retries=3):
    for attempt in range(retries):
        cmd = ["curl", "-sS", "-m", "120", "-X", method, url,
               "-H", "Content-Type: application/json",
               "-w", "\n%{http_code}"]
        for k, v in (headers or {}).items():
            cmd += ["-H", f"{k}: {v}"]
        tmp = None
        if body is not None:
            tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
            json.dump(body, tmp); tmp.close()
            cmd += ["--data-binary", f"@{tmp.name}"]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=150).stdout
            payload, _, code = out.rpartition("\n")
            if code.startswith("2"):
                return json.loads(payload)
            raise RuntimeError(f"HTTP {code}: {payload[:200]}")
        except Exception as e:
            if attempt == retries - 1:
                raise
            print(f"  retry {attempt+1}: {e}")
            time.sleep(2 ** (attempt + 1))
        finally:
            if tmp:
                os.unlink(tmp.name)

def embed_batch(texts, task):
    body = {"requests": [{"model": "models/gemini-embedding-001",
                          "content": {"parts": [{"text": t}]},
                          "taskType": task, "outputDimensionality": 768}
                         for t in texts]}
    for wait in (0, 70, 70, 70, 140, 140, 300, 300):
        if wait:
            print(f"  429/quota: {wait}s待って再試行")
            time.sleep(wait)
        try:
            res = http(GURL, "POST", body, {"x-goog-api-key": GKEY}, retries=1)
            break
        except RuntimeError as e:
            if "429" not in str(e):
                raise
    else:
        raise RuntimeError("quota exceeded: 再試行し尽くした")
    vecs = []
    for e in res["embeddings"]:
        v = e["values"]
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        vecs.append([x / n for x in v])
    return vecs

def pack_b64(vec, urlsafe=False):
    raw = struct.pack("<768f", *vec)
    return (base64.urlsafe_b64encode if urlsafe else base64.b64encode)(raw).decode()

# 1) export
exp = http(f"{APP}/api/agent/scenes/export", headers={"Authorization": f"Bearer {TOKEN}"})
scenes = exp["scenes"] if isinstance(exp, dict) else exp
print(f"export: {len(scenes)}件")

def doc_text(s):
    return (f"{s['caption']}（場所:{s['place']}／行動:{s['action']}／表情:{s['expression']}"
            f"／構図:{s['shot']}／時間帯:{s['time_of_day']}）")

# 2) embed + 3) write, 100件ずつ（登録済みはスキップ＝再開可能）
todo = [s for s in scenes if s.get("embedding_model") != MODEL]
print(f"未登録: {len(todo)}件")
total_updated = 0
for i in range(0, len(todo), 100):
    chunk = todo[i:i+100]
    vecs = embed_batch([doc_text(s) for s in chunk], "RETRIEVAL_DOCUMENT")
    body = {"model": MODEL,
            "vectors": [{"id": s["id"], "vec_b64": pack_b64(v)} for s, v in zip(chunk, vecs)]}
    res = http(f"{APP}/api/agent/scenes/vectors", "POST", body,
               {"Authorization": f"Bearer {TOKEN}"})
    total_updated += res.get("updated", 0)
    print(f"batch {i//100 + 1}: embedded={len(vecs)} updated={res.get('updated')} missing={res.get('missing_ids')}")
    time.sleep(1)
print(f"TOTAL updated: {total_updated}")

# 4) semantic search live test
QUERIES = ["怒っている顔", "座ってる天使ちゃん", "食べ物のアップ", "家にいるシーン",
           "寝てる顔", "いただきますしているシーン", "夜の街を歩く後ろ姿", "がっかりして落ち込んでいる"]
qvecs = embed_batch(QUERIES, "RETRIEVAL_QUERY")
for q, v in zip(QUERIES, qvecs):
    from urllib.parse import quote
    res = http(f"{APP}/api/agent/scenes?q={quote(q)}&qvec={pack_b64(v, urlsafe=True)}&limit=5",
               headers={"Authorization": f"Bearer {TOKEN}"})
    items = res.get("scenes") or res.get("results") or res
    print(f"\n=== {q} ===")
    if isinstance(items, list):
        for it in items[:5]:
            print(f"  score={it.get('score')} [{it.get('episode')}] {it.get('place')}/{it.get('action')}/{it.get('expression')}/{it.get('shot')} :: {str(it.get('caption'))[:60]}")
    else:
        print("  unexpected:", str(items)[:300])
