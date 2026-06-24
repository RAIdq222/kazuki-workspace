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


def _data_uri(path: str, maxw: int = 280) -> str | None:
    """画像をサムネ化して data URI 文字列にする（HTML自己完結用）。失敗時 None。"""
    import base64
    import io
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        if im.width > maxw:
            im = im.resize((maxw, round(im.height * maxw / im.width)))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=72)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def render_html(rows: list[dict], title: str = "背景原図 修正ダッシュボード",
                thumbs: dict | None = None, board_options: list[str] | None = None) -> str:
    thumbs = thumbs or {}
    board_options = board_options or []
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
 select.board{max-width:240px;font-size:12px;padding:3px}
 select.board.set{background:#eaf5ea;border-color:#1a7f37}
 .toolbar{margin:10px 0;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
 .toolbar button{font-size:13px;padding:6px 12px;cursor:pointer;border:1px solid #ccc;border-radius:6px;background:#fff}
 .toolbar .hint{color:#666;font-size:12px}
 .saved-note{color:#1a7f37;font-size:12px}
</style></head><body>""" % html.escape(title)

    done = sum(1 for r in rows if r["runs"])
    meta = (f'<h1>{html.escape(title)}</h1>'
            f'<div class="meta">全{len(rows)}カット / 生成済 {done} / 未生成 {len(rows) - done}'
            f' ・ 生成 {datetime.now().strftime("%Y-%m-%d %H:%M")}'
            f' ・ 美術ボード候補 {len(board_options)}件</div>'
            '<div class="toolbar">'
            '<button onclick="exportCSV()">美術ボード対応をCSVで書き出し</button>'
            '<button onclick="clearSel()">選択をクリア</button>'
            '<span class="hint">プルダウンで選ぶと自動保存（このブラウザに記憶）。確定したらCSVで書き出してください。</span>'
            '<span id="savednote" class="saved-note"></span>'
            '</div>')

    th = ("<tr><th>カット</th><th>原図</th><th>美術ボード</th>"
          "<th>抽出情報（コンテ/注記）</th><th>プロンプト</th>"
          "<th>生成結果</th><th>状態</th><th>検品</th><th>更新</th></tr>")

    body = []
    for row in rows:
        label, cls = _status(row)
        runs = row["runs"]
        latest = runs[-1] if runs else {}
        # 既存の割当（台帳 or 計画）。プルダウンの初期選択に使う。
        assigned = latest.get("board_files") or ([row["planned_board"]] if row["planned_board"] else [])
        assigned_name = _basename(assigned[0]) if assigned else ""
        opts = ['<option value="">— 未選択 —</option>']
        for b in board_options:
            sel = " selected" if b == assigned_name else ""
            opts.append(f'<option value="{html.escape(b)}"{sel}>{html.escape(b)}</option>')
        cls_set = " set" if assigned_name else ""
        boards_html = (f'<select class="board{cls_set}" data-cut="{html.escape(row["cut"])}" '
                       f'data-default="{html.escape(assigned_name)}">'
                       + "".join(opts) + '</select>')
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
        # 結果サムネ（ローカルが無ければURLで。リテイクは全部、最新を先頭に）
        thumbs_list = []
        for r in reversed(runs):
            url = r.get("result_url", "")
            if url:
                thumbs_list.append(f'<a href="{html.escape(url)}" target="_blank">'
                                   f'<img src="{html.escape(url)}" loading="lazy"></a>')
        # ローカルの登録済み結果があれば埋め込み（オフライン自己完結）
        ct = thumbs.get(row["cut"], {})
        result_uri = _data_uri(ct["result"]) if ct.get("result") else None
        if result_uri:
            thumbs_html = (f'<a href="{result_uri}" target="_blank">'
                           f'<img src="{result_uri}" loading="lazy"></a>')
        else:
            thumbs_html = f'<div class="thumbs">{"".join(thumbs_list)}</div>' if thumbs_list else "—"
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
        # 原図サムネ（埋め込み）
        genzu_uri = _data_uri(ct["genzu"]) if ct.get("genzu") else None
        genzu_cell = (f'<a href="{genzu_uri}" target="_blank"><img src="{genzu_uri}"></a>'
                      if genzu_uri else "") + \
                     f'<div class="file">{html.escape(_basename(row["genzu_file"]))}</div>'
        body.append(
            f'<tr><td class="cut">{html.escape(row["cut"])}</td>'
            f'<td>{genzu_cell}</td>'
            f'<td>{boards_html}</td>'
            f'<td class="si">{si_html}</td>'
            f'<td class="prompt">{prompt_html}</td>'
            f'<td>{thumbs_html}</td>'
            f'<td><span class="b {cls}">{html.escape(label)}</span></td>'
            f'<td>{qc_html}</td>'
            f'<td>{when}</td></tr>')

    script = """
<script>
const LS_KEY = "genzu_board_assign_v1";
function loadSel(){ try{ return JSON.parse(localStorage.getItem(LS_KEY)||"{}"); }catch(e){ return {}; } }
function saveSel(m){ localStorage.setItem(LS_KEY, JSON.stringify(m)); }
function note(t){ const n=document.getElementById("savednote"); n.textContent=t; setTimeout(()=>{n.textContent="";},1500); }
function applySaved(){
  const m=loadSel();
  document.querySelectorAll("select.board").forEach(s=>{
    const cut=s.dataset.cut;
    if(cut in m){ s.value=m[cut]; }            // 保存値があれば優先
    s.classList.toggle("set", !!s.value);
    s.addEventListener("change",()=>{
      const cur=loadSel();
      if(s.value){ cur[cut]=s.value; } else { delete cur[cut]; }
      saveSel(cur); s.classList.toggle("set", !!s.value); note("保存しました ("+cut+")");
    });
  });
}
function exportCSV(){
  const rows=[["cut","board"]];
  document.querySelectorAll("select.board").forEach(s=>{ rows.push([s.dataset.cut, s.value||""]); });
  const csv="\\ufeff"+rows.map(r=>r.map(c=>'"'+String(c).replace(/"/g,'""')+'"').join(",")).join("\\r\\n");
  const blob=new Blob([csv],{type:"text/csv;charset=utf-8"});
  const a=document.createElement("a"); a.href=URL.createObjectURL(blob);
  a.download="cut_board_map.csv"; a.click();
}
function clearSel(){ if(confirm("選択をすべてクリアします。よろしいですか？")){ localStorage.removeItem(LS_KEY); location.reload(); } }
applySaved();
</script>"""
    return head + meta + "<table>" + th + "".join(body) + "</table>" + script + "</body></html>"


def render_genzu_list(index_rows: list[dict], board_options: list[str] | None = None,
                      generated_cuts: set | None = None, defaults: dict | None = None,
                      title: str = "原図一覧（ep7）") -> str:
    """原図インベントリ（カット順）をHTML化。担当(GKV優先)・シーン・状態・美術ボード選択付き。

    index_rows: {cut_num, cut_label, filename, assignee, scene} の配列。
    generated_cuts: 生成済みの cut_label 集合（状態表示用）。
    defaults: {cut_label: board_filename} 既定の美術ボード割当（範囲一括の初期値など）。
              ブラウザの localStorage 手動選択があればそちらを優先する。
    """
    board_options = board_options or []
    generated_cuts = generated_cuts or set()
    defaults = defaults or {}
    assignees = sorted({r["assignee"] for r in index_rows})
    palette = ["#1a5fb4", "#117a65", "#9a6700", "#6f42c1", "#a8329a", "#3a7d3a", "#8a5a00"]
    color = {a: palette[i % len(palette)] for i, a in enumerate(a2 for a2 in assignees if a2 != "GKV")}
    color["GKV"] = "#d1242f"

    head = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>%s</title>
<style>
 body{font-family:system-ui,"Hiragino Kaku Gothic ProN",Meiryo,sans-serif;margin:24px;color:#222}
 h1{font-size:20px} .meta{color:#666;font-size:12px;margin-bottom:10px}
 table{border-collapse:collapse;width:100%%} th,td{border:1px solid #ddd;padding:6px 8px;vertical-align:middle;font-size:13px}
 thead th{background:#f4f4f4;position:sticky;top:0;text-align:left}
 tr.gkv{background:#fff4f4}
 td.cut{font-weight:700;white-space:nowrap}
 .who{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;color:#fff;white-space:nowrap}
 .who.gkv{font-weight:700}
 .file{font-family:ui-monospace,monospace;font-size:11px;color:#555;word-break:break-all}
 .scene{font-size:12px;color:#444;white-space:nowrap}
 .gen{font-size:11px;padding:1px 6px;border-radius:8px}
 .gen.done{background:#1a7f37;color:#fff} .gen.todo{background:#eee;color:#888}
 select.board{max-width:240px;font-size:12px;padding:3px} select.board.set{background:#eaf5ea;border-color:#1a7f37}
 .toolbar{margin:10px 0;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
 .toolbar button{font-size:13px;padding:6px 12px;cursor:pointer;border:1px solid #ccc;border-radius:6px;background:#fff}
 .toolbar button.on{background:#d1242f;color:#fff;border-color:#d1242f}
 .toolbar .hint{color:#666;font-size:12px} .saved-note{color:#1a7f37;font-size:12px}
 .rangebar{margin:6px 0 14px;padding:8px;border:1px solid #cde;border-radius:8px;background:#f4f9ff;
   display:flex;gap:6px;align-items:center;flex-wrap:wrap}
 .rangebar input{width:70px;padding:4px} .rangebar select{max-width:260px;padding:4px}
 .rangebar button{padding:6px 12px;cursor:pointer;border:1px solid #1a5fb4;border-radius:6px;background:#1a5fb4;color:#fff}
</style></head><body>""" % html.escape(title)

    counts = {}
    for r in index_rows:
        counts[r["assignee"]] = counts.get(r["assignee"], 0) + 1
    cnt_str = " / ".join(f"{a}:{counts[a]}" for a in sorted(counts, key=lambda a: (-counts[a], a)))
    board_opts_html = "".join(f'<option value="{html.escape(b)}">{html.escape(b)}</option>'
                              for b in board_options)
    meta = (f'<h1>{html.escape(title)}</h1>'
            f'<div class="meta">原図 {len(index_rows)}行（カット単位・束は展開） ・ '
            f'GKV(外注) {counts.get("GKV",0)}行 ・ 担当内訳 {html.escape(cnt_str)} ・ '
            f'美術ボード候補 {len(board_options)}件 ・ '
            f'{datetime.now().strftime("%Y-%m-%d %H:%M")} 生成</div>'
            '<div class="toolbar">'
            '<button id="gkvtop" onclick="toggleGkvTop()">GKVを上に表示</button>'
            '<button id="gkvonly" onclick="toggleGkvOnly()">GKVのみ表示</button>'
            '<button onclick="resetSort()">カット番号順に戻す</button>'
            '<button onclick="exportCSV()">美術ボード対応をCSVで書き出し</button>'
            '<span class="hint">担当=作画担当フォルダ。GKVは外注（優先確認）。欠番=Bank等で正常。</span>'
            '<span id="savednote" class="saved-note"></span></div>'
            # 範囲一括指定（300カットを1つずつ選ばずに済む）
            '<div class="rangebar"><b>範囲一括指定</b>'
            ' cut <input id="rfrom" type="number" placeholder="から"> 〜'
            ' <input id="rto" type="number" placeholder="まで">'
            f' → <select id="rboard"><option value="">— ボード選択 —</option>{board_opts_html}</select>'
            ' <button onclick="applyRange()">この範囲に適用</button>'
            '<span class="hint">例: 53〜206 に「#6#7森の中（夜）R.png」。空欄ボードを選ぶと範囲をクリア。</span></div>')

    thead = ("<thead><tr><th>カット</th><th>担当</th><th>シーン</th><th>原図ファイル</th>"
             "<th>状態</th><th>美術ボード</th></tr></thead>")
    body = []
    for r in index_rows:
        a = r["assignee"]; is_gkv = (a == "GKV")
        label = r["cut_label"]
        gen = "done" if label in generated_cuts else "todo"
        gen_txt = "生成済" if gen == "done" else "未"
        opts = ['<option value="">— 未選択 —</option>'] + [
            f'<option value="{html.escape(b)}">{html.escape(b)}</option>' for b in board_options]
        sel = (f'<select class="board" data-cut="{html.escape(label)}">' + "".join(opts) + '</select>')
        body.append(
            f'<tr class="{"gkv" if is_gkv else ""}" data-cutnum="{r["cut_num"]}" '
            f'data-assignee="{html.escape(a)}">'
            f'<td class="cut">{html.escape(label)}</td>'
            f'<td><span class="who {"gkv" if is_gkv else ""}" '
            f'style="background:{color.get(a,"#888")}">{html.escape(a)}</span></td>'
            f'<td class="scene">{html.escape(r.get("scene",""))}</td>'
            f'<td class="file">{html.escape(r["filename"])}</td>'
            f'<td><span class="gen {gen}">{gen_txt}</span></td>'
            f'<td>{sel}</td></tr>')

    defaults_json = json.dumps(defaults, ensure_ascii=False)
    script = ("""
<script>
const LS_KEY="genzu_board_assign_v1";
const DEFAULTS=__DEFAULTS__;
function loadSel(){try{return JSON.parse(localStorage.getItem(LS_KEY)||"{}");}catch(e){return {};}}
function saveSel(m){localStorage.setItem(LS_KEY,JSON.stringify(m));}
function note(t){const n=document.getElementById("savednote");n.textContent=t;setTimeout(()=>{n.textContent="";},2000);}
const tbody=()=>document.querySelector("table tbody");
let gkvTop=false, gkvOnly=false;
function applySaved(){
  const m=loadSel(); let seeded=false;
  document.querySelectorAll("select.board").forEach(s=>{
    const cut=s.dataset.cut;
    if(cut in m){ s.value=m[cut]; }                 // 手動選択を最優先
    else if(DEFAULTS[cut]){ s.value=DEFAULTS[cut]; m[cut]=DEFAULTS[cut]; seeded=true; }  // 既定を反映&保存
    s.classList.toggle("set",!!s.value);
    s.addEventListener("change",()=>{const c=loadSel(); if(s.value){c[cut]=s.value;}else{delete c[cut];}
      saveSel(c); s.classList.toggle("set",!!s.value); note("保存しました (cut "+cut+")");});
  });
  if(seeded) saveSel(m);
}
function rows(){return Array.from(document.querySelectorAll("tbody tr"));}
function reorder(){
  const rs=rows();
  rs.sort((a,b)=>{
    if(gkvTop){const ga=a.dataset.assignee==="GKV"?0:1, gb=b.dataset.assignee==="GKV"?0:1; if(ga!==gb)return ga-gb;}
    return (+a.dataset.cutnum)-(+b.dataset.cutnum);
  });
  const t=tbody(); rs.forEach(r=>t.appendChild(r));
}
function applyFilter(){ rows().forEach(r=>{ r.style.display=(gkvOnly && r.dataset.assignee!=="GKV")?"none":""; }); }
function toggleGkvTop(){gkvTop=!gkvTop; document.getElementById("gkvtop").classList.toggle("on",gkvTop); reorder();}
function toggleGkvOnly(){gkvOnly=!gkvOnly; document.getElementById("gkvonly").classList.toggle("on",gkvOnly); applyFilter();}
function resetSort(){gkvTop=false; gkvOnly=false; document.getElementById("gkvtop").classList.remove("on");
  document.getElementById("gkvonly").classList.remove("on"); reorder(); applyFilter();}
function applyRange(){
  const f=parseInt(document.getElementById("rfrom").value,10);
  const t=parseInt(document.getElementById("rto").value,10);
  const board=document.getElementById("rboard").value;
  if(isNaN(f)||isNaN(t)){alert("cut範囲（から・まで）を入力してください");return;}
  const c=loadSel(); let n=0;
  rows().forEach(r=>{const cn=+r.dataset.cutnum;
    if(cn>=Math.min(f,t)&&cn<=Math.max(f,t)){
      const s=r.querySelector("select.board"); s.value=board;
      if(board){c[s.dataset.cut]=board;}else{delete c[s.dataset.cut];}
      s.classList.toggle("set",!!board); n++;}});
  saveSel(c); note(n+"件に適用しました ("+f+"〜"+t+")");
}
function exportCSV(){
  const out=[["cut","assignee","scene","filename","board"]];
  rows().forEach(r=>{const sel=r.querySelector("select.board");
    out.push([r.querySelector(".cut").textContent, r.dataset.assignee,
      r.querySelector(".scene").textContent, r.querySelector(".file").textContent, sel?sel.value:""]);});
  const csv="\\ufeff"+out.map(r=>r.map(c=>'"'+String(c).replace(/"/g,'""')+'"').join(",")).join("\\r\\n");
  const a=document.createElement("a"); a.href=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"}));
  a.download="genzu_board_map.csv"; a.click();
}
applySaved();
</script>""").replace("__DEFAULTS__", defaults_json)
    return (head + meta + "<table>" + thead + "<tbody>" + "".join(body)
            + "</tbody></table>" + script + "</body></html>")


def timestamped_path(path: str, tz_offset_hours: int = 9) -> str:
    """ファイル名に YYYYMMDDHHMM のタイムスタンプを付ける（既定 JST=UTC+9）。
    例: dashboard.html -> dashboard_202606242140.html
    """
    from datetime import datetime, timezone, timedelta
    ts = datetime.now(timezone.utc).astimezone(
        timezone(timedelta(hours=tz_offset_hours))).strftime("%Y%m%d%H%M")
    root, ext = os.path.splitext(path)
    return f"{root}_{ts}{ext}"


def generate(out_html: str, ledger_path: str = None, cuts_json: str = None,
             thumbs_json: str = None, boards_json: str = None,
             timestamp: bool = False) -> tuple[int, str]:
    rows = ledger_mod.load(ledger_path or ledger_mod.LEDGER_PATH)
    cuts = None
    if cuts_json and os.path.exists(cuts_json):
        with open(cuts_json, encoding="utf-8") as f:
            cuts = json.load(f)
    thumbs = None
    if thumbs_json and os.path.exists(thumbs_json):
        with open(thumbs_json, encoding="utf-8") as f:
            thumbs = json.load(f)  # {cut: {"genzu": path, "result": path}}
    board_options = []
    if boards_json and os.path.exists(boards_json):
        with open(boards_json, encoding="utf-8") as f:
            board_options = json.load(f)  # ["board1.png", ...]
    table = build_rows(rows, cuts)
    if timestamp:
        out_html = timestamped_path(out_html)
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(render_html(table, thumbs=thumbs, board_options=board_options))
    return len(table), out_html


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="作業結果ダッシュボードHTMLを生成")
    p.add_argument("out_html")
    p.add_argument("--ledger", default=None)
    p.add_argument("--cuts", default=None, help="カット一覧JSON（未生成カットも表示）")
    p.add_argument("--thumbs", default=None, help="{cut:{genzu,result}} 画像パスJSON（埋め込み）")
    p.add_argument("--boards", default=None, help="美術ボード候補のファイル名JSON（プルダウン選択肢）")
    p.add_argument("--timestamp", action="store_true",
                   help="出力ファイル名に YYYYMMDDHHMM(JST) を付ける")
    a = p.parse_args()
    n, path = generate(a.out_html, a.ledger, a.cuts, a.thumbs, a.boards, a.timestamp)
    print(f"wrote {path} ({n} cuts)")
