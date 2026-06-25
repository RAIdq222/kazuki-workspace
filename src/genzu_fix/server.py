"""作業コンソール（ローカルWebアプリ）。

ダッシュボードを「報告」から「作業プラットフォーム」へ。ブラウザだけで
カットごとに: 原図/結果プレビュー → PSDを開く → プロンプト編集 → 生成/リテイク → OK判定。

- タブ単位 = 「作品 ＞ 話数」（プロジェクト）。＋ボタンでフォルダを指定して新規追加。
- 既定プロジェクトは起動引数の cut_board_map CSV（ep7）。新規はフォルダ走査でカット表を作る。
- 状態は <out>/console_state.json、プロジェクト登録は <out>/projects.json に永続。

起動:
    pip install flask
    set PYTHONPATH=src
    python -m genzu_fix.server --genzu-dir "...\\00.原図" --out "...\\10.生成結果" \\
        --boards-dir "<美術ボード展開先>" --port 8765
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import threading
import time

from . import batch, psd_export, naming

CFG = {}
STATE = {}
PROJECTS = {}               # key -> project dict
STATE_LOCK = threading.Lock()
PROJ_LOCK = threading.Lock()
JOBS = {}
JOBS_LOCK = threading.Lock()

WORK_NAMES = {"shz": "尚善"}


def _state_path():
    return os.path.join(CFG["out"], "console_state.json")


def _projects_path():
    return os.path.join(CFG["out"], "projects.json")


def _save_state():
    os.makedirs(CFG["out"], exist_ok=True)
    with STATE_LOCK:
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump(STATE, f, ensure_ascii=False, indent=2)


def _load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def _index_dir(d, exts):
    idx = {}
    if d and os.path.isdir(d):
        for root, _, files in os.walk(d):
            for fn in files:
                if fn.lower().endswith(exts):
                    idx.setdefault(fn, os.path.join(root, fn))
    return idx


def _units_from_csv(csv_path):
    units = {}
    if not (csv_path and os.path.exists(csv_path)):
        return units
    with open(csv_path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            fn = r["filename"]
            uid = os.path.splitext(fn)[0]
            u = units.setdefault(uid, {"id": uid, "filename": fn, "cuts": [],
                                       "assignee": r.get("assignee", ""),
                                       "scene": r.get("scene", ""), "board": r.get("board", "")})
            if r["cut"] not in u["cuts"]:
                u["cuts"].append(r["cut"])
    return units


def _units_from_folder(genzu_dir):
    """フォルダ走査でカット表を作る（scene/assignee はサブフォルダ名から）。"""
    units = {}
    gd = os.path.abspath(genzu_dir)
    for root, _, files in os.walk(gd):
        for fn in files:
            if not fn.lower().endswith(".psd"):
                continue
            uid = os.path.splitext(fn)[0]
            info = naming.parse_cut_codes(fn)
            cuts = info.get("cuts") or [uid]
            rel = os.path.relpath(os.path.join(root, fn), gd)
            parts = rel.split(os.sep)
            scene = next((p for p in parts[:-1] if re.search(r"c\d", p)), "")
            parent = parts[-2] if len(parts) >= 2 else ""
            assignee = parent if (parent and not re.search(r"c\d", parent)) else "(直下)"
            units[uid] = {"id": uid, "filename": fn, "cuts": cuts,
                          "assignee": assignee, "scene": scene, "board": ""}
    return units


def _make_project(key, work, ep, genzu_dir, boards_dir=None, csv_path=None, source="scan"):
    if source == "csv":
        units = _units_from_csv(csv_path)
    else:
        units = _units_from_folder(genzu_dir)
    board_idx = _index_dir(boards_dir, (".png", ".jpg", ".jpeg"))
    boards_opts = sorted(board_idx.keys())
    if not boards_opts and CFG.get("boards_json") and os.path.exists(CFG["boards_json"]):
        boards_opts = _load_json(CFG["boards_json"], [])
    return {
        "key": key, "work": work, "ep": ep, "group": f"{work} #{ep}",
        "genzu_dir": genzu_dir, "boards_dir": boards_dir, "csv": csv_path, "source": source,
        "units": units, "psd_idx": _index_dir(genzu_dir, (".psd",)),
        "board_idx": board_idx, "boards_opts": boards_opts,
    }


def _save_projects():
    recs = [{"key": p["key"], "work": p["work"], "ep": p["ep"], "genzu_dir": p["genzu_dir"],
             "boards_dir": p["boards_dir"], "csv": p["csv"], "source": p["source"]}
            for p in PROJECTS.values()]
    os.makedirs(CFG["out"], exist_ok=True)
    with open(_projects_path(), "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=2)


def _find_unit(uid):
    for p in PROJECTS.values():
        if uid in p["units"]:
            return p, p["units"][uid]
    return None, None


def _unit_dir(uid):
    return os.path.join(CFG["out"], uid)


def _result_path(uid):
    p = os.path.join(_unit_dir(uid), "gen_raw.png")
    return p if os.path.exists(p) else None


def _genzu_preview(uid, psd_path):
    out = os.path.join(_unit_dir(uid), "visible.png")
    if not os.path.exists(out) and psd_path:
        os.makedirs(_unit_dir(uid), exist_ok=True)
        try:
            psd_export.export_background_layer(psd_path, out, include_book=CFG["include_book"])
        except Exception:
            return None
    return out if os.path.exists(out) else None


def _effective_prompt(proj, u):
    st = STATE.get(u["id"], {})
    if st.get("prompt"):
        return st["prompt"]
    board = st.get("board", u["board"])
    use_board = bool(proj.get("boards_dir") and board)
    return batch.build_prompt(board, u["scene"], None, board_as_image=use_board)


def _open_local(path):
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _run_generate(uid):
    def log(m):
        with JOBS_LOCK:
            JOBS[uid]["log"].append(m)
    proj, u = _find_unit(uid)
    if not u:
        with JOBS_LOCK:
            JOBS[uid].update(status="error", error="unit not found")
        return
    psd = proj["psd_idx"].get(u["filename"])
    if not psd:
        with JOBS_LOCK:
            JOBS[uid].update(status="error", error="原図PSDが見つかりません")
        return
    st = STATE.setdefault(uid, {})
    board = st.get("board", u["board"])
    board_path = proj["board_idx"].get(board) if (proj.get("boards_dir") and board) else None
    try:
        log("prep→生成→finish 実行中…")
        batch.process_cut(psd, board, u["scene"], _unit_dir(uid), st.get("prompt") or None,
                          CFG["resolution"], CFG["quality"], CFG["model"], CFG["image_flag"],
                          dry=False, include_book=CFG["include_book"],
                          header_top=CFG["header_top"], board_path=board_path)
        with STATE_LOCK:
            if st.get("generated_once"):
                st["retakes"] = st.get("retakes", 0) + 1
            st["generated_once"] = True
            st["status"] = "done"
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

    def unit_view(proj, u):
        uid = u["id"]
        st = STATE.get(uid, {})
        return {"id": uid, "cuts": u["cuts"], "assignee": u["assignee"], "scene": u["scene"],
                "board": st.get("board", u["board"]), "group": proj["group"], "project": proj["key"],
                "has_psd": u["filename"] in proj["psd_idx"],
                "status": st.get("status", "todo"),
                "has_result": _result_path(uid) is not None,
                "prompt_edited": bool(st.get("prompt")), "retakes": st.get("retakes", 0)}

    @app.get("/")
    def index():
        return Response(PAGE, mimetype="text/html")

    @app.get("/api/projects")
    def api_projects():
        return jsonify([{"key": p["key"], "group": p["group"], "count": len(p["units"]),
                         "boards_opts": p["boards_opts"]} for p in PROJECTS.values()])

    @app.post("/api/projects")
    def api_add_project():
        b = request.json or {}
        work = b.get("work", "").strip() or "作品"
        ep = b.get("ep", "").strip() or "00"
        gd = b.get("genzu_dir", "").strip()
        bd = b.get("boards_dir", "").strip() or None
        if not gd or not os.path.isdir(gd):
            return jsonify({"error": "原図フォルダが見つかりません: " + gd}), 400
        key = f"{work}#{ep}"
        with PROJ_LOCK:
            PROJECTS[key] = _make_project(key, work, ep, gd, bd, source="scan")
            _save_projects()
        return jsonify({"ok": True, "key": key, "count": len(PROJECTS[key]["units"])})

    @app.post("/api/projects/<key>/rescan")
    def api_rescan(key):
        p = PROJECTS.get(key)
        if not p:
            return jsonify({"error": "not found"}), 404
        with PROJ_LOCK:
            PROJECTS[key] = _make_project(key, p["work"], p["ep"], p["genzu_dir"],
                                          p["boards_dir"], p["csv"], p["source"])
        return jsonify({"ok": True, "count": len(PROJECTS[key]["units"])})

    @app.get("/api/units")
    def api_units():
        out = []
        for p in PROJECTS.values():
            out += [unit_view(p, u) for u in p["units"].values()]
        return jsonify(out)

    @app.get("/api/unit/<uid>")
    def api_unit(uid):
        proj, u = _find_unit(uid)
        if not u:
            return jsonify({"error": "not found"}), 404
        return jsonify({**unit_view(proj, u), "filename": u["filename"],
                        "prompt": _effective_prompt(proj, u),
                        "boards_opts": proj["boards_opts"]})

    @app.post("/api/unit/<uid>/prompt")
    def api_prompt(uid):
        STATE.setdefault(uid, {})["prompt"] = (request.json or {}).get("prompt", "").strip() or None
        _save_state()
        return jsonify({"ok": True})

    @app.post("/api/unit/<uid>/board")
    def api_board(uid):
        STATE.setdefault(uid, {})["board"] = (request.json or {}).get("board", "")
        _save_state()
        return jsonify({"ok": True})

    @app.post("/api/unit/<uid>/accept")
    def api_accept(uid):
        STATE.setdefault(uid, {})["status"] = (request.json or {}).get("value", "accepted")
        _save_state()
        return jsonify({"ok": True})

    @app.post("/api/unit/<uid>/open")
    def api_open(uid):
        proj, u = _find_unit(uid)
        if not u:
            return jsonify({"error": "not found"}), 404
        psd = proj["psd_idx"].get(u["filename"])
        if not psd:
            return jsonify({"error": "PSDが見つかりません"}), 404
        try:
            _open_local(os.path.abspath(psd))
            return jsonify({"ok": True})
        except Exception as e:  # noqa
            return jsonify({"error": str(e)}), 500

    @app.post("/api/unit/<uid>/generate")
    def api_generate(uid):
        proj, u = _find_unit(uid)
        if not u:
            return jsonify({"error": "not found"}), 404
        with JOBS_LOCK:
            if JOBS.get(uid, {}).get("status") == "running":
                return jsonify({"error": "already running"}), 409
            JOBS[uid] = {"status": "running", "log": [], "error": None, "ts": time.time()}
        STATE.setdefault(uid, {})["status"] = "generating"
        _save_state()
        threading.Thread(target=_run_generate, args=(uid,), daemon=True).start()
        return jsonify({"ok": True})

    @app.get("/api/unit/<uid>/job")
    def api_job(uid):
        with JOBS_LOCK:
            return jsonify(dict(JOBS.get(uid, {"status": "idle", "log": [], "error": None})))

    @app.get("/img/<uid>/<which>")
    def img(uid, which):
        proj, u = _find_unit(uid)
        if not u:
            return "", 404
        if which == "genzu":
            p = _genzu_preview(uid, proj["psd_idx"].get(u["filename"]))
        elif which == "result":
            p = _result_path(uid)
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
 .tabs{display:flex;gap:4px;padding:8px 12px 0;align-items:center;flex-wrap:wrap}
 .tab{padding:7px 16px;border:1px solid #ddd;border-bottom:none;border-radius:8px 8px 0 0;background:#eef0f3;cursor:pointer;font-size:13px}
 .tab.active{background:#fff;font-weight:700;border-color:#1a5fb4;color:#1a5fb4}
 .tab.add{background:#1a5fb4;color:#fff;border-color:#1a5fb4;border-radius:8px}
 .toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:8px 12px;font-size:12px}
 .summary{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
 .pill{padding:2px 9px;border-radius:10px;font-size:12px;background:#eef0f3}
 .pill.ok{background:#dff3e6;color:#0a5} .pill.ng{background:#fde2e2;color:#d1242f}
 .pbar{height:8px;width:160px;background:#e6e8eb;border-radius:5px;overflow:hidden}
 .pbar>i{display:block;height:100%;background:#1a7f37}
 .grow{flex:1}
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
 .thumbs figure{margin:0;flex:1} .thumbs figcaption{font-size:10px;color:#888}
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
 #modal{position:fixed;inset:0;background:rgba(0,0,0,.4);display:none;align-items:center;justify-content:center;z-index:60}
 #modal .box{background:#fff;padding:18px;border-radius:10px;width:520px;max-width:94vw}
 #modal label{display:block;font-size:12px;margin:8px 0 2px;color:#444}
 #modal input{width:100%;padding:6px;font-size:13px}
</style></head><body>
<header>
 <div class="tabs" id="tabs"></div>
 <div class="toolbar">
   担当 <select id="fAssignee" style="width:auto"><option value="">全部</option></select>
   状態 <select id="fStatus" style="width:auto"><option value="">全部</option><option>todo</option><option>generating</option><option>done</option><option>accepted</option><option>reject</option></select>
   <label><input type="checkbox" id="fResult"> 未生成のみ</label>
   <span class="grow"></span>
   <span class="summary" id="summary"></span>
   <button onclick="rescan()">フォルダ再取得</button>
   <button onclick="refresh()">更新</button>
 </div>
</header>
<main><div class="grid" id="grid"></div></main>
<div id="lb" onclick="this.style.display='none'"><img id="lbimg"></div>
<div id="modal"><div class="box">
  <h3 style="margin:0 0 6px">作品・話数を追加（フォルダから取得）</h3>
  <label>作品名</label><input id="mWork" placeholder="尚善">
  <label>話数</label><input id="mEp" placeholder="08">
  <label>原図フォルダのフルパス（中を再帰走査）</label><input id="mGenzu" placeholder="C:\\...\\00.原図">
  <label>美術ボードフォルダのフルパス（任意）</label><input id="mBoards" placeholder="C:\\...\\美術ボード">
  <div class="bar" style="margin-top:12px"><button class="primary" onclick="addProject()">追加</button>
   <button onclick="document.getElementById('modal').style.display='none'">キャンセル</button>
   <span id="mMsg" class="muted"></span></div>
</div></div>
<script>
let UNITS=[],PROJECTS=[],GROUP=null,BOARDS=[];
const $=s=>document.querySelector(s);
const esc=s=>(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;');
async function post(u,b){return (await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})})).json();}
function lb(src){$('#lbimg').src=src;$('#lb').style.display='flex';}
async function refresh(){
  PROJECTS=await (await fetch('/api/projects')).json();
  UNITS=await (await fetch('/api/units')).json();
  const groups=PROJECTS.map(p=>p.group);
  if(!GROUP||!groups.includes(GROUP)) GROUP=groups[0];
  const cur=PROJECTS.find(p=>p.group===GROUP); BOARDS=cur?cur.boards_opts:[];
  $('#tabs').innerHTML=groups.map(g=>`<div class="tab ${g===GROUP?'active':''}" data-g="${g}">${esc(g)}</div>`).join('')
    +'<div class="tab add" id="addTab">＋ 作品・話数</div>';
  document.querySelectorAll('.tab[data-g]').forEach(t=>t.onclick=()=>{GROUP=t.dataset.g;refresh();});
  $('#addTab').onclick=()=>{$('#modal').style.display='flex';};
  const a=new Set(UNITS.filter(u=>u.group===GROUP).map(u=>u.assignee));
  const sel=$('#fAssignee'),c=sel.value;
  sel.innerHTML='<option value="">全部</option>'+[...a].sort().map(x=>`<option ${x===c?'selected':''}>${x}</option>`).join('');
  render();
}
function render(){
  const fa=$('#fAssignee').value,fs=$('#fStatus').value,fr=$('#fResult').checked;
  const all=UNITS.filter(u=>u.group===GROUP);
  const us=all.filter(u=>(!fa||u.assignee===fa)&&(!fs||u.status===fs)&&(!fr||!u.has_result));
  const gen=all.filter(u=>u.has_result).length, ok=all.filter(u=>u.status==='accepted').length, ng=all.filter(u=>u.status==='reject').length;
  const pct=all.length?Math.round(ok/all.length*100):0;
  $('#summary').innerHTML=`<span class="pill">全${all.length}</span><span class="pill">生成済 ${gen}</span>`
    +`<span class="pill ok">OK ${ok}</span><span class="pill ng">要修正 ${ng}</span>`
    +`<span class="pill">未生成 ${all.length-gen}</span>`
    +`<div class="pbar"><i style="width:${pct}%"></i></div><span class="muted">${pct}% OK</span>`;
  $('#grid').innerHTML=us.map(card).join('');
}
function card(u){
  const t=Date.now();
  const opts='<option value="">— ボード未選択 —</option>'+BOARDS.map(b=>`<option ${b===u.board?'selected':''}>${esc(b)}</option>`).join('');
  return `<div class="card ${u.status}" id="card_${u.id}">
   <div class="chead"><span class="cut">c${u.cuts.join(',')}</span>
     <span class="who ${u.assignee==='GKV'?'gkv':'other'}">${u.assignee}</span>
     <span class="b ${u.status}">${u.status}</span>${u.retakes?`<span class="muted">RT${u.retakes}</span>`:''}
     ${u.has_psd?'':'<span class="muted">PSD無</span>'}<span class="scene">${esc(u.scene)}</span></div>
   <div class="thumbs">
     <figure><figcaption>原図 ${u.has_psd?`<a href="#" onclick="openPsd('${u.id}');return false">[PSDを開く]</a>`:''}</figcaption>
       ${u.has_psd?`<img loading="lazy" src="/img/${u.id}/genzu" onclick="lb(this.src)" onerror="this.outerHTML='<div class=ph>原図なし</div>'">`:'<div class="ph">PSD未検出</div>'}</figure>
     <figure><figcaption>生成結果</figcaption>${u.has_result?`<img loading="lazy" src="/img/${u.id}/result?t=${t}" onclick="lb(this.src)">`:'<div class="ph">未生成</div>'}</figure>
   </div>
   <select onchange="setBoard('${u.id}',this.value)">${opts}</select>
   <details><summary>プロンプト${u.prompt_edited?'（編集済）':''}</summary>
     <textarea id="pr_${u.id}" placeholder="（自動生成。編集して保存で上書き）"></textarea>
     <div class="bar"><button onclick="savePrompt('${u.id}')">保存</button>
       <button onclick="loadPrompt('${u.id}')">自動表示</button>
       <button onclick="resetPrompt('${u.id}')">自動に戻す</button></div></details>
   <div class="bar"><button class="primary" onclick="gen('${u.id}')">${u.has_result?'リテイク':'生成'}</button>
     <button class="ok" onclick="accept('${u.id}','accepted')">OK</button>
     <button class="ng" onclick="accept('${u.id}','reject')">要修正</button></div>
   <div class="log" id="log_${u.id}" style="display:none"></div></div>`;
}
async function openPsd(id){const r=await post('/api/unit/'+id+'/open',{}); if(r.error)slog(id,'開けません: '+r.error); else slog(id,'PSDを開きました');}
async function loadPrompt(id){const d=await (await fetch('/api/unit/'+id)).json(); const t=document.getElementById('pr_'+id); if(t)t.value=d.prompt;}
async function savePrompt(id){const t=document.getElementById('pr_'+id); await post('/api/unit/'+id+'/prompt',{prompt:t?t.value:''}); slog(id,'保存しました');}
async function resetPrompt(id){await post('/api/unit/'+id+'/prompt',{prompt:''}); const t=document.getElementById('pr_'+id); if(t)t.value=''; slog(id,'自動に戻しました');}
async function setBoard(id,v){await post('/api/unit/'+id+'/board',{board:v}); slog(id,'ボード保存');}
async function accept(id,v){await post('/api/unit/'+id+'/accept',{value:v}); const u=UNITS.find(x=>x.id===id); if(u)u.status=v; render();}
function slog(id,m){const l=document.getElementById('log_'+id); if(l){l.style.display='block';l.textContent=m;}}
async function gen(id){
  const t=document.getElementById('pr_'+id); if(t&&t.value.trim()) await post('/api/unit/'+id+'/prompt',{prompt:t.value});
  const r=await post('/api/unit/'+id+'/generate',{}); if(r.error){slog(id,'エラー: '+r.error);return;}
  const u=UNITS.find(x=>x.id===id); if(u)u.status='generating'; slog(id,'生成開始…(数分)');
  const c=document.getElementById('card_'+id); c&&c.querySelectorAll('button').forEach(b=>b.disabled=true);
  const poll=setInterval(async()=>{const j=await (await fetch('/api/unit/'+id+'/job')).json();
    slog(id,(j.log||[]).join('\n'));
    if(j.status==='done'||j.status==='error'){clearInterval(poll); await refresh();}},2500);
}
async function rescan(){const p=PROJECTS.find(x=>x.group===GROUP); if(!p)return; const r=await post('/api/projects/'+encodeURIComponent(p.key)+'/rescan',{}); await refresh();}
async function addProject(){
  $('#mMsg').textContent='追加中…';
  const r=await post('/api/projects',{work:$('#mWork').value,ep:$('#mEp').value,genzu_dir:$('#mGenzu').value,boards_dir:$('#mBoards').value});
  if(r.error){$('#mMsg').textContent='エラー: '+r.error;return;}
  $('#modal').style.display='none'; GROUP=null; await refresh();
}
$('#fAssignee').onchange=render;$('#fStatus').onchange=render;$('#fResult').onchange=render;
refresh();
</script></body></html>"""


def main(argv=None):
    p = argparse.ArgumentParser(prog="genzu_fix.server", description="原図修正コンソール")
    p.add_argument("--genzu-dir", required=True)
    p.add_argument("--out", default="work/console")
    p.add_argument("--csv", default="runs/cut_board_map_ep7.csv")
    p.add_argument("--boards-dir", default=None)
    p.add_argument("--boards-json", default="runs/boards_ep7.json")
    p.add_argument("--work", default="尚善")
    p.add_argument("--ep", default="07")
    p.add_argument("--resolution", default="2k")
    p.add_argument("--quality", default="high")
    p.add_argument("--model", default="gpt_image_2")
    p.add_argument("--image-flag", default="--image")
    p.add_argument("--include-book", action="store_true")
    p.add_argument("--header-top", type=int, default=None)
    p.add_argument("--port", type=int, default=8765)
    a = p.parse_args(argv)
    CFG.update(dict(out=a.out, csv=a.csv, boards_json=a.boards_json,
                    resolution=a.resolution, quality=a.quality, model=a.model,
                    image_flag=a.image_flag, include_book=a.include_book, header_top=a.header_top))
    global STATE
    STATE = _load_json(_state_path(), {})
    # 既定プロジェクト（起動引数のCSV）
    dkey = f"{a.work}#{a.ep}"
    PROJECTS[dkey] = _make_project(dkey, a.work, a.ep, a.genzu_dir, a.boards_dir, a.csv, source="csv")
    # 永続化された追加プロジェクトを復元
    for rec in _load_json(_projects_path(), []):
        if rec["key"] not in PROJECTS and os.path.isdir(rec.get("genzu_dir", "")):
            PROJECTS[rec["key"]] = _make_project(rec["key"], rec["work"], rec["ep"],
                                                 rec["genzu_dir"], rec.get("boards_dir"),
                                                 rec.get("csv"), rec.get("source", "scan"))
    _save_projects()
    app = create_app()
    print(f"原図修正コンソール: http://127.0.0.1:{a.port}  (out={a.out})")
    app.run(host="127.0.0.1", port=a.port, threaded=True)


if __name__ == "__main__":
    main()
