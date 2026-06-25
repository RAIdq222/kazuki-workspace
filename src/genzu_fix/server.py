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
        return {
            "id": uid, "cuts": u["cuts"], "assignee": u["assignee"], "scene": u["scene"],
            "board": st.get("board", u["board"]),
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
 body{margin:0;font-family:system-ui,"Hiragino Kaku Gothic ProN",Meiryo,sans-serif;color:#222;display:flex;height:100vh}
 #list{width:340px;border-right:1px solid #ddd;overflow:auto;flex:none}
 #detail{flex:1;overflow:auto;padding:16px}
 h1{font-size:15px;margin:10px 12px}
 .filters{padding:0 12px 8px;font-size:12px}
 .row{padding:8px 12px;border-bottom:1px solid #eee;cursor:pointer;font-size:13px}
 .row:hover{background:#f4f8ff} .row.sel{background:#e8f0ff}
 .row .cut{font-weight:700} .who{display:inline-block;padding:1px 6px;border-radius:8px;color:#fff;font-size:10px;margin-left:4px}
 .gkv{background:#d1242f} .other{background:#1a5fb4}
 .b{display:inline-block;padding:1px 7px;border-radius:8px;font-size:11px;color:#fff}
 .todo{background:#9aa0a6}.generating{background:#bf8700}.done{background:#1a7f37}.accepted{background:#0a5}.reject{background:#d1242f}
 .imgs{display:flex;gap:14px;flex-wrap:wrap;margin:10px 0}
 .imgs figure{margin:0} .imgs img{max-width:440px;max-height:340px;border:1px solid #ddd;background:#fff;display:block}
 figcaption{font-size:12px;color:#666;margin-bottom:4px}
 textarea{width:100%;height:150px;font-size:12px;font-family:ui-monospace,monospace}
 .bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0}
 button{font-size:13px;padding:7px 13px;border:1px solid #ccc;border-radius:6px;background:#fff;cursor:pointer}
 button.primary{background:#1a5fb4;color:#fff;border-color:#1a5fb4}
 button.ok{background:#1a7f37;color:#fff;border-color:#1a7f37}
 button.ng{background:#d1242f;color:#fff;border-color:#d1242f}
 select{font-size:12px;padding:4px;max-width:300px} .muted{color:#888;font-size:12px}
 #log{white-space:pre-wrap;font-size:11px;color:#555;background:#fafafa;border:1px solid #eee;padding:6px;margin-top:8px;max-height:120px;overflow:auto}
</style></head><body>
<div id="list"><h1>原図修正コンソール</h1>
 <div class="filters">担当 <select id="fAssignee"><option value="">全部</option></select>
  状態 <select id="fStatus"><option value="">全部</option><option>todo</option><option>generating</option><option>done</option><option>accepted</option><option>reject</option></select></div>
 <div id="rows"></div></div>
<div id="detail"><div class="muted">左からカットを選択</div></div>
<script>
let UNITS=[], CUR=null, POLL=null;
const $=s=>document.querySelector(s);
async function loadUnits(){
  UNITS=await (await fetch('/api/units')).json();
  const a=new Set(UNITS.map(u=>u.assignee)); const sel=$('#fAssignee');
  sel.innerHTML='<option value="">全部</option>'+[...a].sort().map(x=>`<option>${x}</option>`).join('');
  renderList();
}
function renderList(){
  const fa=$('#fAssignee').value, fs=$('#fStatus').value;
  const rows=UNITS.filter(u=>(!fa||u.assignee===fa)&&(!fs||u.status===fs));
  $('#rows').innerHTML=rows.map(u=>`<div class="row ${CUR===u.id?'sel':''}" data-id="${u.id}">
    <span class="cut">c${u.cuts.join(',')}</span>
    <span class="who ${u.assignee==='GKV'?'gkv':'other'}">${u.assignee}</span>
    <span class="b ${u.status}">${u.status}</span>
    ${u.has_result?'🖼️':''}${u.prompt_edited?'✎':''}${u.has_psd?'':' <span class="muted">PSD無</span>'}
    <div class="muted">${u.scene}</div></div>`).join('');
  document.querySelectorAll('.row').forEach(r=>r.onclick=()=>openUnit(r.dataset.id));
}
$('#fAssignee').onchange=renderList; $('#fStatus').onchange=renderList;
async function openUnit(id){
  CUR=id; renderList();
  const u=await (await fetch('/api/unit/'+id)).json();
  $('#detail').innerHTML=`
   <div class="bar"><b>c${u.cuts.join(',')}</b> <span class="who ${u.assignee==='GKV'?'gkv':'other'}">${u.assignee}</span>
     <span class="b ${u.status}">${u.status}</span> <span class="muted">${u.scene} / ${u.filename}</span>
     ${u.retakes?`<span class="muted">リテイク${u.retakes}</span>`:''}</div>
   <div class="bar">美術ボード:
     <select id="board"><option value="">— 未選択 —</option>${u.boards_opts.map(b=>`<option ${b===u.board?'selected':''}>${b}</option>`).join('')}</select></div>
   <div class="imgs">
     <figure><figcaption>原図(背景レイヤー)</figcaption><img src="/img/${id}/genzu?t=${Date.now()}" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'muted',textContent:'原図プレビュー無し(PSD未検出?)'}))"></figure>
     <figure><figcaption>生成結果</figcaption><img id="resImg" src="/img/${id}/result?t=${Date.now()}" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'muted',textContent:'未生成'}))"></figure>
   </div>
   <div><b>プロンプト</b> <span class="muted">${u.prompt_edited?'(編集済)':'(自動生成)'}</span></div>
   <textarea id="prompt">${u.prompt.replace(/</g,'&lt;')}</textarea>
   <div class="bar">
     <button onclick="savePrompt('${id}')">プロンプト保存</button>
     <button onclick="resetPrompt('${id}')">自動に戻す</button>
     <button class="primary" id="genBtn" onclick="gen('${id}')">${u.has_result?'リテイク実行':'生成実行'}</button>
     <button class="ok" onclick="accept('${id}','accepted')">OK</button>
     <button class="ng" onclick="accept('${id}','reject')">要修正</button>
   </div>
   <div class="muted">原図をPhotoshopで直したら、保存後に「リテイク実行」で読み直して再生成されます。</div>
   <div id="log"></div>`;
  $('#board').onchange=async e=>{await post('/api/unit/'+id+'/board',{board:e.target.value}); openUnit(id);};
  if(POLL){clearInterval(POLL);POLL=null;}
}
async function post(url,body){return (await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})})).json();}
async function savePrompt(id){await post('/api/unit/'+id+'/prompt',{prompt:$('#prompt').value}); flash('保存しました');}
async function resetPrompt(id){await post('/api/unit/'+id+'/prompt',{prompt:''}); openUnit(id);}
async function accept(id,v){await post('/api/unit/'+id+'/accept',{value:v}); await loadUnits(); openUnit(id);}
function flash(m){const l=$('#log'); if(l) l.textContent=m;}
async function gen(id){
  await savePrompt(id);
  const r=await post('/api/unit/'+id+'/generate',{});
  if(r.error){flash('エラー: '+r.error);return;}
  $('#genBtn').disabled=true; flash('生成開始…(数分かかります)');
  POLL=setInterval(async()=>{
    const j=await (await fetch('/api/unit/'+id+'/job')).json();
    flash((j.log||[]).join('\n'));
    if(j.status==='done'){clearInterval(POLL);POLL=null;$('#genBtn').disabled=false;
      $('#resImg')&&($('#resImg').src='/img/'+id+'/result?t='+Date.now()); await loadUnits(); openUnit(id);}
    if(j.status==='error'){clearInterval(POLL);POLL=null;$('#genBtn').disabled=false; flash('失敗: '+(j.error||'')); await loadUnits();}
  },2500);
}
loadUnits();
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
