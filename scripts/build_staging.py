"""scene_understanding SP2版 — カット別「画角・場面の記述(staging)」の自動下書き。

黒江さんが c005/c008/c010 で手書きして構図を通した記述（カメラ位置・向き・写るもの・
写らないもの）を、**コンテの前後カット＋原図画像**から自動で下書きする。
出力はコンソールが staging_map として読み、詳細画面の記述欄に下書きとして入る
（人が直して保存すれば手動版が優先される）。

各カットについてモデルに渡すもの:
  1. 原図Base（Book込み・背景のみ）… 何が描かれているか
  2. 原図visible（セル込み・見たまま）… キャラの位置＝配置の根拠
  3. コンテの前後±3カットの Action/Dialog … シナリオの流れからの画角推論
  4. 場所・時刻（scene_ranges 由来）

使い方（ローカル・ANTHROPIC_API_KEY 必須）:
  set PYTHONPATH=src
  python scripts/build_staging.py --genzu-dir "C:\\...\\00.原図" ^
      --conte runs/conte_v2_sp2_10.csv --ranges runs/scene_ranges_sp2_10.csv ^
      --out runs/staging_sp2_10.csv --limit 5          ← まず5本試走→良ければ --limit 0 で全数
  （--resume で out にあるカットをスキップ＝続きから）
  git add runs/staging_sp2_10.csv && git commit -m "data: SP2#10 staging下書き" && git push origin main
"""
from __future__ import annotations
import argparse
import base64
import csv
import io
import json
import os
import re
import sys
import tempfile
import urllib.request

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from genzu_fix import psd_export, naming

_MODEL = os.environ.get("STAGING_MODEL", "claude-opus-4-8")

_SYSTEM = (
    "あなたはアニメ背景美術の演出助手。原図（背景レイアウト）から、そのカットの"
    "「画角・場面の記述」を書く。この記述は画像生成AIに構図を伝える唯一のチャンネルとして"
    "使われる（画像参照では構図が伝わらないことが実証済み）。"
)


def _b64(im) -> str:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def _render(psd_path: str, kind: str, maxside: int = 1024):
    from PIL import Image
    tmp = os.path.join(tempfile.gettempdir(), "_staging_prev.png")
    if kind == "base":
        psd_export.export_background_layer(psd_path, tmp, include_book=True)
    else:
        psd_export.export_visible_to_png(psd_path, tmp, drop_text=False)
    im = Image.open(tmp)
    if max(im.size) > maxside:
        s = maxside / max(im.size)
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    return im


def _conte_context(rows: list[dict], n: int, span: int = 3) -> str:
    out = []
    for r in rows:
        m = re.match(r"0*(\d+)", (r.get("cut") or ""))
        if not m:
            continue
        k = int(m.group(1))
        if n - span <= k <= n + span:
            mark = "★" if k == n else " "
            act = (r.get("action") or "").replace("\n", "／")[:80]
            dia = (r.get("dialogue") or "").replace("\n", "／")[:60]
            out.append(f"{mark}cut{k}: {act}" + (f"｜台詞: {dia}" if dia else ""))
    return "\n".join(out) or "（コンテ情報なし）"


def _ask(key: str, base_im, vis_im, context: str, place: str, time_: str,
         cut: int, timeout: int = 180) -> dict:
    prompt = (
        f"対象: cut {cut}。場所: {place or '不明'}。時刻: {time_ or '不明'}。\n"
        f"IMAGE1=原図（背景のみ・Book込み）。IMAGE2=同じ原図のセル込み（キャラの位置が配置の根拠）。\n"
        f"絵コンテの前後カット:\n{context}\n\n"
        "この材料から、このカットの背景の「画角・場面の記述」を日本語で書いてください。\n"
        "含めるもの: ①カメラの位置と向き（部屋のどこから何に向いているか） ②画面に写るもの"
        "（原図に実在するものだけ。位置関係も） ③写らないもの（誤って描かれやすいもの） "
        "④キャラ由来の配置の根拠があれば（例: 椅子の位置は着席キャラの位置。動かさない）。\n"
        "禁止: 原図に無いものの推測での追加。長文（3〜4文まで）。\n"
        "ヘッダのレンズmm表記（望遠=パースが浅い/広角=強い）とEYE線も画角判断に使ってよい。\n"
        '出力はJSONのみ: {"staging": "記述", "confidence": "high|medium|low", '
        '"notes": "判断の根拠や不確かな点(1文)"}'
    )
    body = {
        "model": _MODEL, "max_tokens": 700,
        "system": _SYSTEM,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "IMAGE1 (原図・背景のみ):"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _b64(base_im)}},
            {"type": "text", "text": "IMAGE2 (セル込み・見たまま):"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _b64(vis_im)}},
            {"type": "text", "text": prompt}]}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
        headers={"content-type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"})
    # 一時エラー(429/500/529=Anthropic側の過負荷)は待って再試行。529は波状に続くことが
    # あるため待ちは長め（30/60/120/240s）。それでも駄目なら諦めて次のカットへ
    # （--resume で後から埋められる）。
    data = None
    waits = (30, 60, 120, 240)
    for attempt in range(len(waits) + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if attempt < len(waits) and e.code in (429, 500, 502, 503, 529):
                w = waits[attempt]
                print(f"    [retry] HTTP {e.code} → {w}s待って再試行 {attempt + 1}/{len(waits)}")
                import time as _time
                _time.sleep(w)
                continue
            raise
    text = "".join(b.get("text", "") for b in data.get("content", []))
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {"staging": "", "confidence": "low",
                                             "notes": f"JSON解析失敗: {text[:100]}"}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="build_staging", description="stagingの自動下書き")
    p.add_argument("--genzu-dir", required=True)
    p.add_argument("--conte", required=True, help="conte consolidate のCSV")
    p.add_argument("--ranges", required=True, help="scene_ranges CSV（場所/時刻）")
    p.add_argument("--out", required=True)
    p.add_argument("--limit", type=int, default=5, help="先頭N本だけ（試走用）。0=全数")
    p.add_argument("--resume", action="store_true", help="outに既にあるカットをスキップ")
    p.add_argument("--model", default="", help="モデルID上書き（529が続く時は claude-sonnet-5 等へ切替）")
    a = p.parse_args(argv)
    if a.model:
        global _MODEL
        _MODEL = a.model

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("[!] ANTHROPIC_API_KEY が未設定です")
        return 1
    with open(a.conte, encoding="utf-8-sig") as f:
        conte_rows = list(csv.DictReader(f))
    with open(a.ranges, encoding="utf-8-sig") as f:
        ranges = [dict(r, start=int(r["start"]), end=int(r["end"])) for r in csv.DictReader(f)]

    done = set()
    rows_out = []
    if a.resume and os.path.exists(a.out):
        with open(a.out, encoding="utf-8-sig") as f:
            rows_out = list(csv.DictReader(f))
            done = {r["cut"] for r in rows_out}

    psds = []
    for root, _, files in os.walk(a.genzu_dir):
        for fn in sorted(files):
            if fn.lower().endswith(".psd"):
                psds.append(os.path.join(root, fn))
    psds.sort(key=lambda x: os.path.basename(x))

    n_run = 0
    for path in psds:
        info = naming.parse_cut_codes(os.path.basename(path))
        cuts = info.get("cuts") or []
        if not cuts:
            continue
        m = re.match(r"0*(\d+)", cuts[0])
        if not m:
            continue
        n = int(m.group(1))
        if str(n) in done:
            continue
        if a.limit and n_run >= a.limit:
            break
        rng = next((r for r in ranges if r["start"] <= n <= r["end"]), {})
        try:
            base_im = _render(path, "base")
            vis_im = _render(path, "visible")
            res = _ask(key, base_im, vis_im, _conte_context(conte_rows, n),
                       rng.get("place", ""), rng.get("time", ""), n)
        except Exception as e:  # noqa 1本の失敗で全体を止めない
            print(f"  [warn] cut{n}: {str(e)[:120]}")
            continue
        rows_out.append({"cut": str(n), "staging": res.get("staging", ""),
                         "confidence": res.get("confidence", ""),
                         "notes": res.get("notes", "")})
        n_run += 1
        print(f"  cut{n} [{res.get('confidence','?')}] {res.get('staging','')[:70]}")
        # 逐次保存（途中で止めても成果が残る）
        with open(a.out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["cut", "staging", "confidence", "notes"])
            w.writeheader()
            for r in sorted(rows_out, key=lambda r: int(r["cut"])):
                w.writerow(r)
    print(f"書き出し: {a.out}  {len(rows_out)}カット（今回 {n_run}本）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
