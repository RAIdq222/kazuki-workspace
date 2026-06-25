"""作業コンソール（ローカルWebアプリ・MVP）。

ダッシュボードを「報告」から「作業プラットフォーム」へ。ブラウザだけで
カットごとに: 原図/結果プレビュー → プロンプト編集 → 生成/リテイク → OK判定 を回す。

起動（黒江さんのWindows / 原図とHiggsfield CLIがあるマシンで）:
    pip install flask
    set PYTHONPATH=src
    python -m genzu_fix.server ^
        --genzu-dir "...\\00.原図" --out "...\\10.生成結果" ^
        --boards-dir "<美術ボード展開先>" --port 8765
    → ブラウザで http://127.0.0.1:8765

設計:
- 処理単位は「原図PSD（ファイル）」。束カット(016_026)は1単位。cut_board_map から集約。
- 状態は <out>/console_state.json に永続化（prompt/status/retakes/board）。
- 生成はバックグラウンドスレッドで process_cut を実行（Higgsfield CLIを叩く）。UIはポーリング。
- 画像は <out>/<unit>/ の visible.png(原図) / gen_raw.png(生成) を配信。
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import threading
import time

from . import batch, psd_export

# ---- グローバル設定（main で確定）----
CFG = {}
STATE = {}
STATE_LOCK = threading.Lock()
JOBS = {}            # unit_id -> {"status","log","error","ts"}
JOBS_LOCK = threading.Lock()


def _state_path():
    return os.path.join(CFG["out"], "console_state.json")


def _load_state():
    p = _state_path()
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_state():
    os.makedirs(CFG["out"], exist_ok=True)
    with STATE_LOCK:
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump(STATE, f, ensure_ascii=False, indent=2)


def _build_units():
    """cut_board_map を原図ファイル単位に集約して units を返す。"""
    units = {}
    with open(CFG["csv"], encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            fn = r["filename"]
            uid = os.path.splitext(fn)[0]
            u = units.setdefault(uid, {
                "id": uid, "filename": fn, "cuts": [], "assignee": r["assignee"],
                "scene": r["scene"], "board": r["board"],
            })
            if r["cut"] not in u["cuts"]:
                u["cuts"].append(r["cut"])
    return units


def _psd_index():
    idx = {}
    for root, _, files in os.walk(CFG["genzu_dir"]):
        for fn in files:
            if fn.lower().endswith(".psd"):
                idx.setdefault(fn, os.path.join(root, fn))
    return idx


def _board_index():
    idx = {}
    if CFG.get("boards_dir"):
        for root, _, files in os.walk(CFG["boards_dir"]):
            for fn in files:
                idx.setdefault(fn, os.path.join(root, fn))
    return idx


def _unit_dir(uid):
    return os.path.join(CFG["out"], uid)


def _result_path(uid):
    p = os.path.join(_unit_dir(uid), "gen_raw.png")
    return p if os.path.exists(p) else None


def _genzu_preview(uid, psd_path):
    """原図プレビュー(visible.png)を必要なら生成して返す。"""
    out = os.path.join(_unit_dir(uid), "visible.png")
    if not os.path.exists(out) and psd_path:
        os.makedirs(_unit_dir(uid), exist_ok=True)
        try:
            psd_export.export_background_layer(psd_path, out, include_book=CFG["include_book"])
        except Exception:
            return None
    return out if os.path.exists(out) else None


def _effective_prompt(u):
    st = STATE.get(u["id"], {})
    if st.get("prompt"):
        return st["prompt"]
    board = STATE.get(u["id"], {}).get("board", u["board"])
    use_board = bool(CFG.get("boards_dir") and board)
    return batch.build_prompt(board, u["scene"], None, board_as_image=use_board)


def _run_generate(uid, units, psd_idx, board_idx):
    """バックグラウンド生成。"""
    def log(m):
        with JOBS_LOCK:
            JOBS[uid]["log"].append(m)
    u = units[uid]
    psd = psd_idx.get(u["filename"])
    if not psd:
        with JOBS_LOCK:
            JOBS[uid].update(status="error", error="原図PSDが見つかりません")
        return
    st = STATE.setdefault(uid, {})
    board = st.get("board", u["board"])
    board_path = board_idx.get(board) if (CFG.get("boards_dir") and board) else None
    prompt_override = st.get("prompt") or None
    try:
        log("prep→生成→finish 実行中…")
        batch.process_cut(
            psd, board, u["scene"], _unit_dir(uid), prompt_override,
            CFG["resolution"], CFG["quality"], CFG["model"], CFG["image_flag"],
            dry=False, include_book=CFG["include_book"],
            header_top=CFG["header_top"], board_path=board_path)
        with STATE_LOCK:
            st["status"] = "done"
            st["retakes"] = st.get("retakes", 0) + (1 if st.get("generated_once") else 0)
            st["generated_once"] = True
            st["last_run"] = time.time()
        _save_state()
        with JOBS_LOCK:
            JOBS[uid].update(status="done")
        log("完了")
    except Exception as e:  # noqa
        with JOBS_LOCK:
            JOBS[uid].update(status="error", error=str(e)[:300])
        log("失敗: " + str(e)[:200])


def create_app():
    from flask import Flask, jsonify, request, send_file, Response
    app = Flask(__name__)
    units = _build_units()
    psd_idx = _psd_index()
    board_idx = _board_index()
    boards_opts = []
    if CFG.get("boards_json") and os.path.exists(CFG["boards_json"]):
        boards_opts = json.load(open(CFG["boards_json"], encoding="utf-8"))

    def unit_view(u):
        uid = u["id"]
        st = STATE.get(uid, {})
        import re as _re
        m = _re.search(r"([a-zA-Z]+)_(\d+)_", u["filename"])
        work_code = m.group(1) if m else "?"
        ep = m.group(2) if m else "?"
        work = {"shz": "尚善"}.get(work_code, work_code)
        return {
            "id": uid, "cuts": u["cuts"], "assignee": u["assignee"], "scene": u["scene"],
            "board": st.get("board", u["board"]),
            "work": work, "ep": ep, "group": f"{work} #{ep}",
            "has_psd": u["filename"] in psd_idx,
            "status": st.get("status", "todo"),
            "has_result": _result_path(uid) is not None,
            "prompt_edited": bool(st.get("prompt")),
            "retakes": st.get("retakes", 0),
        }

    @app.get("/")
    def index():
        return Response(PAGE, mimetype="text/html")

    @app.get("/api/units")
    def api_units():
        return jsonify([unit_view(u) for u in units.values()])

    @app.get("/api/unit/<uid>")
    def api_unit(uid):
        u = units.get(uid)
        if not u:
            return jsonify({"error": "not found"}), 404
        st = STATE.get(uid, {})
        return jsonify({
            **unit_view(u),
            "filename": u["filename"],
            "prompt": _effective_prompt(u),
            "default_prompt": batch.build_prompt(
                st.get("board", u["board"]), u["scene"], None,
                board_as_image=bool(CFG.get("boards_dir") and st.get("board", u["board"]))),
            "boards_opts": boards_opts,
        })

    @app.post("/api/unit/<uid>/prompt")
    def api_prompt(uid):
        st = STATE.setdefault(uid, {})
        st["prompt"] = (request.json or {}).get("prompt", "").strip() or None
        _save_state()
        return jsonify({"ok": True})

    @app.post("/api/unit/<uid>/board")
    def api_board(uid):
        st = STATE.setdefault(uid, {})
        st["board"] = (request.json or {}).get("board", "")
        _save_state()
        return jsonify({"ok": True})

    @app.post("/api/unit/<uid>/accept")
    def api_accept(uid):
        st = STATE.setdefault(uid, {})
        st["status"] = (request.json or {}).get("value", "accepted")
        _save_state()
        return jsonify({"ok": True})

    @app.post("/api/unit/<uid>/generate")
    def api_generate(uid):
        if uid not in units:
            return jsonify({"error": "not found"}), 404
        with JOBS_LOCK:
            if JOBS.get(uid, {}).get("status") == "running":
                return jsonify({"error": "already running"}), 409
            JOBS[uid] = {"status": "running", "log": [], "error": None, "ts": time.time()}
        STATE.setdefault(uid, {})["status"] = "generating"
        _save_state()
        threading.Thread(target=_run_generate, args=(uid, units, psd_idx, board_idx),
                         daemon=True).start()
        return jsonify({"ok": True})

    @app.get("/api/unit/<uid>/job")
    def api_job(uid):
        with JOBS_LOCK:
            j = JOBS.get(uid, {"status": "idle", "log": [], "error": None})
            return jsonify(dict(j))

    @app.get("/img/<uid>/<which>")
    def img(uid, which):
        u = units.get(uid)
        if not u:
            return "", 404
        if which == "genzu":
            p = _genzu_preview(uid, psd_idx.get(u["filename"]))
        elif which == "result":
            p = _result_path(uid)
        elif which == "board":
            p = board_idx.get(STATE.get(uid, {}).get("board", u["board"]))
        else:
            p = None
        if not p or not os.path.exists(p):
            return "", 404
        return send_file(os.path.abspath(p))

    return app


PAGE = r"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>原図修正コンソール</title>
<style>
 *{box-sizing:border-box}
 body{margin:0;font-family:system-ui,"Hiragino Kaku Gothic ProN",Meiryo,sans-serif;color:#222;background:#f6f7f9}
 header{position:sticky;top:0;background:#fff;border-bottom:1px solid #ddd;z-index:5}
 .tabs{display:flex;gap:4px;padding:8px 12px 0}
 .tab{padding:7px 16px;border:1px solid #ddd;border-bottom:none;border-radius:8px 8px 0 0;background:#eef0f3;cursor:pointer;font-size:13px}
 .tab.active{background:#fff;font-weight:700;border-color:#1a5fb4;color:#1a5fb4}
 .toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:8px 12px;font-size:12px}
 .toolbar .grow{flex:1}
 main{padding:12px}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px}
 .card{background:#fff;border:1px solid #ddd;border-radius:10px;padding:10px;display:flex;flex-direction:column;gap:6px}
 .card.reject{border-color:#d1242f} .card.accepted{border-color:#1a7f37}
 .chead{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
 .cut{font-weight:700} .scene{color:#888;font-size:11px;width:100%}
 .who{display:inline-block;padding:1px 7px;border-radius:8px;color:#fff;font-size:10px}
 .gkv{background:#d1242f} .other{background:#1a5fb4}
 .b{display:inline-block;padding:1px 7px;border-radius:8px;font-size:11px;color:#fff}
 .todo{background:#9aa0a6}.generating{background:#bf8700}.done{background:#1a7f37}.accepted{background:#0a5}.reject{background:#d1242f}
 .thumbs{display:flex;gap:6px}
 .thumbs figure{margin:0;flex:1}
 .thumbs figcaption{font-size:10px;color:#888}
 .thumbs img{width:100%;height:150px;object-fit:contain;border:1px solid #eee;background:#fff;cursor:zoom-in}
 .ph{height:150px;border:1px dashed #ddd;display:flex;align-items:center;justify-content:center;color:#bbb;font-size:11px}
 select{font-size:11px;padding:3px;max-width:100%;width:100%}
 details summary{cursor:pointer;font-size:12px;color:#1a5fb4}
 textarea{width:100%;height:120px;font-size:11px;font-family:ui-monospace,monospace;margin-top:4px}
 .bar{display:flex;gap:5px;flex-wrap:wrap}
 button{font-size:12px;padding:5px 9px;border:1px solid #ccc;border-radius:6px;background:#fff;cursor:pointer}
 button.primary{background:#1a5fb4;color:#fff;border-color:#1a5fb4}
 button.ok{background:#1a7f37;color:#fff;border-color:#1a7f37}
 button.ng{background:#d1242f;color:#fff;border-color:#d1242f}
 button:disabled{opacity:.5;cursor:default}
 .log{white-space:pre-wrap;font-size:10px;color:#666;background:#fafafa;border:1px solid #eee;padding:4px;max-height:64px;overflow:auto}
 .muted{color:#999;font-size:11px}
 #lb{position:fixed;inset:0;background:rgba(0,0,0,.85);display:none;align-items:center;justify-content:center;z-index:50}
 #lb img{max-width:96vw;max-height:96vh}
</style></head><body>
<header>
 <div class="tabs" id="tabs"></div>
 <div class="toolbar">
   担当 <select id="fAssignee" style="width:auto"><option value="">全部</option></select>
   状態 <select id="fStatus" style="width:auto"><option value="">全部</option><option>todo</option><option>generating</option><option>done</option><option>accepted</option><option>reject</option></select>
   <label><input type="checkbox" id="fResult"> 未生成のみ</label>
   <span class="grow"></span>
   <span id="counts" class="muted"></span>
   <button onclick="refresh()">更新</button>
 </div>
</header>
<main><div class="grid" id="grid"></div></main>
<div id="lb" onclick="this.style.display='none'"><img id="lbimg"></div>
<script>
let UNITS=[], GROUP=null, BOARDS=[];
const $=s=>document.querySelector(s);
const esc=s=>(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;');
async function post(url,b){return (await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})})).json();}
function lb(src){$('#lbimg').src=src;$('#lb').style.display='flex';}

async function refresh(){
  UNITS=await (await fetch('/api/units')).json();
  if(!BOARDS.length && UNITS.length){const d=await (await fetch('/api/unit/'+UNITS[0].id)).json(); BOARDS=d.boards_opts||[];}
  // tabs = 作品 #話数
  const groups=[...new Set(UNITS.map(u=>u.group))];
  if(!GROUP||!groups.includes(GROUP)) GROUP=groups[0];
  $('#tabs').innerHTML=groups.map(g=>`<div class="tab ${g===GROUP?'active':''}" data-g="${g}">${g}</div>`).join('');
  document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{GROUP=t.dataset.g;render();});
  const a=new Set(UNITS.map(u=>u.assignee));
  const sel=$('#fAssignee'),cur=sel.value;
  sel.innerHTML='<option value="">全部</option>'+[...a].sort().map(x=>`<option ${x===cur?'selected':''}>${x}</option>`).join('');
  render();
}
function render(){
  const fa=$('#fAssignee').value, fs=$('#fStatus').value, fr=$('#fResult').checked;
  const us=UNITS.filter(u=>u.group===GROUP&&(!fa||u.assignee===fa)&&(!fs||u.status===fs)&&(!fr||!u.has_result));
  $('#counts').textContent=`${us.length}件 / 生成済 ${us.filter(u=>u.has_result).length} / OK ${us.filter(u=>u.status==='accepted').length}`;
  $('#grid').innerHTML=us.map(card).join('');
}
function card(u){
  const t=Date.now();
  const boardOpts='<option value="">— ボード未選択 —</option>'+BOARDS.map(b=>`<option ${b===u.board?'selected':''}>${esc(b)}</option>`).join('');
  return `<div class="card ${u.status}" id="card_${u.id}" data-id="${u.id}">
   <div class="chead"><span class="cut">c${u.cuts.join(',')}</span>
     <span class="who ${u.assignee==='GKV'?'gkv':'other'}">${u.assignee}</span>
     <span class="b ${u.status}">${u.status}</span>
     ${u.retakes?`<span class="muted">RT${u.retakes}</span>`:''}
     ${u.has_psd?'':'<span class="muted">PSD無</span>'}
     <span class="scene">${esc(u.scene)}</span></div>
   <div class="thumbs">
     <figure><figcaption>原図</figcaption>${u.has_psd?`<img loading="lazy" src="/img/${u.id}/genzu" onclick="lb(this.src)" onerror="this.outerHTML='<div class=ph>原図なし</div>'">`:'<div class="ph">PSD未検出</div>'}</figure>
     <figure><figcaption>生成結果</figcaption>${u.has_result?`<img loading="lazy" src="/img/${u.id}/result?t=${t}" onclick="lb(this.src)">`:'<div class="ph">未生成</div>'}</figure>
   </div>
   <select onchange="setBoard('${u.id}',this.value)">${boardOpts}</select>
   <details><summary>プロンプト${u.prompt_edited?'（編集済）':''}</summary>
     <textarea id="pr_${u.id}" placeholder="（自動生成。編集して保存で上書き）"></textarea>
     <div class="bar"><button onclick="savePrompt('${u.id}')">保存</button>
       <button onclick="loadPrompt('${u.id}')">読込/自動表示</button>
       <button onclick="resetPrompt('${u.id}')">自動に戻す</button></div>
   </details>
   <div class="bar">
     <button class="primary" onclick="gen('${u.id}')">${u.has_result?'リテイク':'生成'}</button>
     <button class="ok" onclick="accept('${u.id}','accepted')">OK</button>
     <button class="ng" onclick="accept('${u.id}','reject')">要修正</button>
   </div>
   <div class="log" id="log_${u.id}" style="display:none"></div></div>`;
}
async function loadPrompt(id){const d=await (await fetch('/api/unit/'+id)).json(); const t=document.getElementById('pr_'+id); if(t)t.value=d.prompt;}
async function savePrompt(id){const t=document.getElementById('pr_'+id); await post('/api/unit/'+id+'/prompt',{prompt:t?t.value:''}); slog(id,'プロンプト保存');}
async function resetPrompt(id){await post('/api/unit/'+id+'/prompt',{prompt:''}); const t=document.getElementById('pr_'+id); if(t)t.value=''; slog(id,'自動に戻しました');}
async function setBoard(id,v){await post('/api/unit/'+id+'/board',{board:v}); slog(id,'ボード保存');}
async function accept(id,v){await post('/api/unit/'+id+'/accept',{value:v}); const u=UNITS.find(x=>x.id===id); if(u)u.status=v; render();}
function slog(id,m){const l=document.getElementById('log_'+id); if(l){l.style.display='block';l.textContent=m;}}
async function gen(id){
  const t=document.getElementById('pr_'+id); if(t&&t.value.trim()) await post('/api/unit/'+id+'/prompt',{prompt:t.value});
  const r=await post('/api/unit/'+id+'/generate',{}); if(r.error){slog(id,'エラー: '+r.error);return;}
  const u=UNITS.find(x=>x.id===id); if(u)u.status='generating';
  slog(id,'生成開始…(数分)');
  const card=document.getElementById('card_'+id); card&&card.querySelectorAll('button').forEach(b=>b.disabled=true);
  const poll=setInterval(async()=>{
    const j=await (await fetch('/api/unit/'+id+'/job')).json();
    slog(id,(j.log||[]).join('\n'));
    if(j.status==='done'||j.status==='error'){clearInterval(poll); await refresh();}
  },2500);
}
$('#fAssignee').onchange=render; $('#fStatus').onchange=render; $('#fResult').onchange=render;
refresh();
</script></body></html>"""


def main(argv=None):
    p = argparse.ArgumentParser(prog="genzu_fix.server", description="原図修正コンソール(MVP)")
    p.add_argument("--genzu-dir", required=True)
    p.add_argument("--out", default="work/console")
    p.add_argument("--csv", default="runs/cut_board_map_ep7.csv")
    p.add_argument("--boards-dir", default=None)
    p.add_argument("--boards-json", default="runs/boards_ep7.json")
    p.add_argument("--resolution", default="2k")
    p.add_argument("--quality", default="high")
    p.add_argument("--model", default="gpt_image_2")
    p.add_argument("--image-flag", default="--image")
    p.add_argument("--include-book", action="store_true")
    p.add_argument("--header-top", type=int, default=None)
    p.add_argument("--port", type=int, default=8765)
    a = p.parse_args(argv)
    CFG.update(dict(
        genzu_dir=a.genzu_dir, out=a.out, csv=a.csv, boards_dir=a.boards_dir,
        boards_json=a.boards_json, resolution=a.resolution, quality=a.quality,
        model=a.model, image_flag=a.image_flag, include_book=a.include_book,
        header_top=a.header_top))
    global STATE
    STATE = _load_state()
    app = create_app()
    print(f"原図修正コンソール: http://127.0.0.1:{a.port}  (out={a.out})")
    app.run(host="127.0.0.1", port=a.port, threaded=True)


if __name__ == "__main__":
    main()
