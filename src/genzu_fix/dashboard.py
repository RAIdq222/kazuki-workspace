"""作業結果ダッシュボード生成。

カット番号順に「原図 / 使った美術ボード / プロンプト / 生成結果 / 状態 / 更新日時」を
一覧化した自己完結HTML（外部依存なし）を出力する。

データ源:
- 生成台帳 `runs/ledger.jsonl`（実際に生成したラン。リテイクは複数行）。
- 任意で「カット一覧」（原図ファイル群）。渡すと未生成カットも行として表示する。

カットの単位は原図ファイル（cut フィールド = 原図stem, 例 shz_07_268）。
同じ cut に複数ランがあればリテイクとして最新を主表示し、回数を出す。
"""
from __future__ import annotations
import html
import json
import os
from datetime import datetime

from . import ledger as ledger_mod
from .naming import parse_cut_codes


def _cut_sort_key(cut: str):
    """'shz_07_091_101_116' → (7, 91, '...') のように番号順で並べるキー。"""
    info = parse_cut_codes(cut + "_genzu") if "genzu" not in cut else parse_cut_codes(cut)
    ep = int(info["ep"]) if info["ep"].isdigit() else 0
    cuts = info["cuts"]
    if cuts:
        m = "".join(c for c in cuts[0] if c.isdigit())
        first = int(m) if m else 0
        suffix = "".join(c for c in cuts[0] if not c.isdigit())
    else:
        first, suffix = 0, ""
    return (ep, first, suffix, cut)


def build_rows(ledger_rows: list[dict], cuts: list[dict] | None = None) -> list[dict]:
    """台帳とカット一覧を cut 単位に統合して、表示用の行リストを返す。"""
    by_cut: dict[str, dict] = {}

    # まずカット一覧（未生成も含めたい場合）
    for c in (cuts or []):
        cut = c.get("cut") or c.get("genzu_file", "")
        by_cut.setdefault(cut, {
            "cut": cut,
            "genzu_file": c.get("genzu_file", cut),
            "planned_board": c.get("board", ""),
            "scene": c.get("scene", ""),
            "runs": [],
        })

    # 台帳のランを cut にぶら下げる
    for r in ledger_rows:
        cut = r.get("cut", "")
        row = by_cut.setdefault(cut, {
            "cut": cut, "genzu_file": r.get("genzu_file", cut),
            "planned_board": "", "scene": "", "runs": [],
        })
        row["runs"].append(r)

    rows = list(by_cut.values())
    for row in rows:
        row["runs"].sort(key=lambda r: r.get("created_at", 0))
    rows.sort(key=lambda x: _cut_sort_key(x["cut"]))
    return rows


def _status(row: dict) -> tuple[str, str]:
    n = len(row["runs"])
    if n == 0:
        return ("未生成", "todo")
    if n == 1:
        return ("生成済", "done")
    return (f"リテイク{n - 1}回", "retake")


def _short(s: str, n: int = 90) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + "…"


def _basename(path: str) -> str:
    return os.path.basename(path) if path else ""


def _si_val(v) -> str:
    """scene_info の値を1行表示用に整形（リストは・区切り）。"""
    if isinstance(v, (list, tuple)):
        return " / ".join(str(x) for x in v)
    return str(v)


def render_html(rows: list[dict], title: str = "背景原図 修正ダッシュボード") -> str:
    head = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s</title>
<style>
 body{font-family:system-ui,"Hiragino Kaku Gothic ProN",Meiryo,sans-serif;margin:24px;color:#222}
 h1{font-size:20px} .meta{color:#666;font-size:12px;margin-bottom:16px}
 table{border-collapse:collapse;width:100%%} th,td{border:1px solid #ddd;padding:8px;vertical-align:top;font-size:13px}
 th{background:#f4f4f4;position:sticky;top:0;text-align:left}
 tr:nth-child(even){background:#fafafa}
 img{max-width:160px;max-height:110px;display:block;border:1px solid #eee;background:#fff}
 .b{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;color:#fff}
 .todo{background:#9aa0a6} .done{background:#1a7f37} .retake{background:#bf8700}
 .cut{font-weight:700;white-space:nowrap} .prompt{max-width:240px;color:#444}
 .si{font-size:11px;color:#333;max-width:240px} .si b{color:#1a5fb4}
 .full{white-space:pre-wrap;font-size:11px;color:#444;max-width:260px;margin-top:4px}
 details summary{cursor:pointer;color:#1a5fb4}
 .file{font-family:ui-monospace,monospace;font-size:11px;color:#555;word-break:break-all}
 .thumbs{display:flex;gap:6px;flex-wrap:wrap}
 .pass{background:#1a7f37} .needs_retake{background:#d1242f} .human{background:#8250df} .unknown{background:#9aa0a6}
 .qc{font-size:11px;color:#555} .qc .b{color:#fff}
</style></head><body>""" % html.escape(title)

    done = sum(1 for r in rows if r["runs"])
    meta = (f'<h1>{html.escape(title)}</h1>'
            f'<div class="meta">全{len(rows)}カット / 生成済 {done} / 未生成 {len(rows) - done}'
            f' ・ 生成 {datetime.now().strftime("%Y-%m-%d %H:%M")}</div>')

    th = ("<tr><th>カット</th><th>原図</th><th>美術ボード</th>"
          "<th>抽出情報（コンテ/注記）</th><th>プロンプト</th>"
          "<th>生成結果</th><th>状態</th><th>検品</th><th>更新</th></tr>")

    body = []
    for row in rows:
        label, cls = _status(row)
        runs = row["runs"]
        latest = runs[-1] if runs else {}
        boards = latest.get("board_files") or ([row["planned_board"]] if row["planned_board"] else [])
        boards_html = "<br>".join(html.escape(_basename(b)) for b in boards) or "—"
        # 抽出情報（コンテ/原図注記）
        si = latest.get("scene_info") or {}
        if si:
            si_html = "".join(
                f'<div><b>{html.escape(str(k))}</b>: {html.escape(_si_val(v))}</div>'
                for k, v in si.items())
        else:
            si_html = "—"
        # プロンプト全文（折りたたみ）
        full_prompt = latest.get("prompt", "")
        if full_prompt:
            prompt_html = (f'<details><summary>{html.escape(_short(full_prompt, 60))}</summary>'
                           f'<div class="full">{html.escape(full_prompt)}</div></details>')
        else:
            prompt_html = "—"
        # 結果サムネ（リテイクは全部、最新を先頭に）
        thumbs = []
        for r in reversed(runs):
            url = r.get("result_url", "")
            if url:
                thumbs.append(f'<a href="{html.escape(url)}" target="_blank">'
                              f'<img src="{html.escape(url)}" loading="lazy"></a>')
        thumbs_html = f'<div class="thumbs">{"".join(thumbs)}</div>' if thumbs else "—"
        when = (datetime.fromtimestamp(latest["created_at"]).strftime("%m/%d %H:%M")
                if latest.get("created_at") else "—")
        qc = latest.get("qc") or {}
        if qc:
            v = qc.get("verdict", "unknown")
            vlabel = {"pass": "合格", "needs_retake": "要リテイク",
                      "human": "人手送り", "unknown": "未判定"}.get(v, v)
            reasons = "・".join(qc.get("reasons", []))
            qc_html = (f'<span class="b {v}">{html.escape(vlabel)}</span>'
                       + (f'<div class="qc">{html.escape(reasons)}</div>' if reasons else ""))
        else:
            qc_html = "—"
        body.append(
            f'<tr><td class="cut">{html.escape(row["cut"])}</td>'
            f'<td class="file">{html.escape(_basename(row["genzu_file"]))}</td>'
            f'<td>{boards_html}</td>'
            f'<td class="si">{si_html}</td>'
            f'<td class="prompt">{prompt_html}</td>'
            f'<td>{thumbs_html}</td>'
            f'<td><span class="b {cls}">{html.escape(label)}</span></td>'
            f'<td>{qc_html}</td>'
            f'<td>{when}</td></tr>')

    return head + meta + "<table>" + th + "".join(body) + "</table></body></html>"


def generate(out_html: str, ledger_path: str = None, cuts_json: str = None) -> int:
    rows = ledger_mod.load(ledger_path or ledger_mod.LEDGER_PATH)
    cuts = None
    if cuts_json and os.path.exists(cuts_json):
        with open(cuts_json, encoding="utf-8") as f:
            cuts = json.load(f)
    table = build_rows(rows, cuts)
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(render_html(table))
    return len(table)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="作業結果ダッシュボードHTMLを生成")
    p.add_argument("out_html")
    p.add_argument("--ledger", default=None)
    p.add_argument("--cuts", default=None, help="カット一覧JSON（未生成カットも表示）")
    a = p.parse_args()
    n = generate(a.out_html, a.ledger, a.cuts)
    print(f"wrote {a.out_html} ({n} cuts)")
