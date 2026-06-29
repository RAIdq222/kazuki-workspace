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
import unicodedata

from . import batch, psd_export, naming

CFG = {}
STATE = {}
PROJECTS = {}               # key -> project dict
STATE_LOCK = threading.Lock()
PROJ_LOCK = threading.Lock()
JOBS = {}
JOBS_LOCK = threading.Lock()
OVERVIEWS = {}              # "<work>#<ep>" -> {synopsis, scenes, note}

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


# 美術ボードとして拾う拡張子（PSD/TIFF も含める＝表示時にPNG化）。
_BOARD_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".psd", ".psb", ".tif", ".tiff")


def _norm_board(name):
    """ボード名を表記ゆれ込みで照合するための正規化キー（拡張子無視・全半角統一・空白除去）。"""
    stem = os.path.splitext(name or "")[0]
    return "".join(unicodedata.normalize("NFKC", stem).lower().split())


def _board_src(proj, name):
    """ボード名 → 実ファイルパス。完全一致 → 正規化一致（拡張子/全半角/空白ゆれを吸収）。"""
    if not name or not proj:
        return None
    idx = proj.get("board_idx") or {}
    if name in idx:
        return idx[name]
    return (proj.get("board_norm") or {}).get(_norm_board(name))


def _board_png(proj, name):
    """ブラウザ表示用PNGパスを返す。PSD/TIFF は out/_board_cache/ にPNG化してキャッシュ。"""
    src = _board_src(proj, name)
    if not src or not os.path.exists(src):
        return None
    ext = os.path.splitext(src)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".webp"):
        return src
    cache = os.path.join(CFG.get("out", "."), "_board_cache")
    os.makedirs(cache, exist_ok=True)
    out = os.path.join(cache, _norm_board(name) + ".png")
    if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(src):
        return out
    try:
        if ext in (".psd", ".psb"):
            psd_export.export_visible_to_png(src, out, bg=(255, 255, 255))
        else:  # tif/tiff
            from PIL import Image
            Image.open(src).convert("RGB").save(out)
    except Exception:
        return None
    return out if os.path.exists(out) else None


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
    board_idx = _index_dir(boards_dir, _BOARD_EXTS)
    # 正規化キー（拡張子/全半角/空白ゆれ吸収）→ パス。PSDを先に書きPNG等を後で上書き＝軽いPNG優先。
    board_norm = {}
    for fn, path in sorted(board_idx.items(),
                           key=lambda kv: 0 if kv[0].lower().endswith((".psd", ".psb", ".tif", ".tiff")) else 1):
        board_norm[_norm_board(fn)] = path
    boards_opts = sorted(board_idx.keys())
    if not boards_opts and CFG.get("boards_json") and os.path.exists(CFG["boards_json"]):
        boards_opts = _load_json(CFG["boards_json"], [])
    if boards_dir:
        print(f"[boards] {boards_dir}: {len(board_idx)} 枚 索引（{key}）")
    return {
        "key": key, "work": work, "ep": ep, "group": f"{work} #{ep}",
        "genzu_dir": genzu_dir, "boards_dir": boards_dir, "csv": csv_path, "source": source,
        "units": units, "psd_idx": _index_dir(genzu_dir, (".psd",)),
        "board_idx": board_idx, "board_norm": board_norm, "boards_opts": boards_opts,
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
    # restored_full.png は原図画角へ戻した最終結果＝原図と画角一致（比較スライダーが揃う）。
    # 無ければ生成直後の gen_raw.png にフォールバック。
    d = _unit_dir(uid)
    for n in ("restored_full.png", "gen_raw.png"):
        p = os.path.join(d, n)
        if os.path.exists(p):
            return p
    return None


def _genzu_preview(uid, psd_path, source="base", force=False):
    out = os.path.join(_unit_dir(uid), "visible.png")
    if (force or not os.path.exists(out)) and psd_path:
        os.makedirs(_unit_dir(uid), exist_ok=True)
        try:
            if source == "visible":
                psd_export.export_visible_to_png(psd_path, out, drop_text=False)
            else:
                psd_export.export_background_layer(psd_path, out, include_book=CFG["include_book"])
        except Exception:
            return None
    return out if os.path.exists(out) else None


def _effective_prompt(proj, u):
    st = STATE.get(u["id"], {})
    if st.get("prompt"):
        return st["prompt"]
    board = st.get("board", u["board"])
    cut = (u["cuts"][0] if u.get("cuts") else "")
    # プロンプトは genzu_fix.prompt（3層）に委譲（great-edisonの設計と統合）。
    # 表示と生成を一致させるため cut_info_map（situation/remove）も渡す。
    en, _ = batch.build_prompt_pair(board, u["scene"], None, cut=cut,
                                    cut_info_map=CFG.get("cut_info_map"))
    return en


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
    board_path = _board_png(proj, board) if (proj.get("boards_dir") and board) else None
    try:
        log("prep→生成→finish 実行中…")
        batch.process_cut(psd, board, u["scene"], _unit_dir(uid), st.get("prompt") or None,
                          CFG["resolution"], CFG["quality"], CFG["model"], CFG["image_flag"],
                          dry=False, include_book=CFG["include_book"],
                          header_top=CFG["header_top"], board_path=board_path,
                          genzu_source=st.get("genzu_source", "base"),
                          cut_num=(u["cuts"][0] if u.get("cuts") else ""),
                          cut_info_map=CFG.get("cut_info_map"))
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
        with JOBS_LOCK:
            running = JOBS.get(uid, {}).get("status") == "running"
        return {"id": uid, "cuts": u["cuts"], "assignee": u["assignee"], "scene": u["scene"],
                "board": st.get("board", u["board"]), "group": proj["group"], "project": proj["key"],
                "work": proj["work"], "ep": proj["ep"],
                "has_psd": u["filename"] in proj["psd_idx"],
                "status": st.get("status", "todo"), "running": running,
                "genzu_source": st.get("genzu_source", "base"),
                "has_result": _result_path(uid) is not None,
                "prompt_edited": bool(st.get("prompt")), "retakes": st.get("retakes", 0)}

    @app.get("/")
    def index():
        return Response(PAGE, mimetype="text/html")

    @app.get("/api/projects")
    def api_projects():
        return jsonify([{"key": p["key"], "group": p["group"], "work": p["work"], "ep": p["ep"],
                         "count": len(p["units"]), "boards_opts": p["boards_opts"],
                         "has_board_files": bool(p["board_idx"])}
                        for p in PROJECTS.values()])

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

    @app.get("/api/overview")
    def api_overview():
        key = request.args.get("key", "")
        proj = PROJECTS.get(key) or next(
            (p for p in PROJECTS.values() if p["group"] == key), None)
        if not proj:
            return jsonify({"error": "not found"}), 404
        ov = OVERVIEWS.get(proj["key"]) or OVERVIEWS.get(proj["group"]) or {}
        # 美術ボードの「登場回数」= そのボードが当たっているカット数で集計（多い順）。
        from collections import Counter
        cnt = Counter()
        for u in proj["units"].values():
            b = STATE.get(u["id"], {}).get("board", u["board"])
            if b:
                cnt[b] += len(u["cuts"]) or 1
        boards = [{"board": b, "cuts": n, "has_img": _board_src(proj, b) is not None}
                  for b, n in cnt.most_common()]
        return jsonify({"key": proj["key"], "synopsis": ov.get("synopsis", ""),
                        "scenes": ov.get("scenes", []), "note": ov.get("note", ""),
                        "boards": boards})

    @app.get("/board-img")
    def board_img():
        proj = PROJECTS.get(request.args.get("key", ""))
        p = _board_png(proj, request.args.get("name", "")) if proj else None
        if not p or not os.path.exists(p):
            return "", 404
        return send_file(os.path.abspath(p))

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

    @app.post("/api/unit/<uid>/recapture")
    def api_recapture(uid):
        proj, u = _find_unit(uid)
        if not u:
            return jsonify({"error": "not found"}), 404
        source = (request.json or {}).get("source", "base")
        STATE.setdefault(uid, {})["genzu_source"] = source
        _save_state()
        psd = proj["psd_idx"].get(u["filename"])
        p = _genzu_preview(uid, psd, source=source, force=True)
        if not p:
            return jsonify({"error": "原図の取得に失敗（PSD未検出?）"}), 400
        return jsonify({"ok": True, "source": source})

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
            src = STATE.get(uid, {}).get("genzu_source", "base")
            p = _genzu_preview(uid, proj["psd_idx"].get(u["filename"]), source=src)
        elif which == "result":
            p = _result_path(uid)
        elif which == "board":
            board = STATE.get(uid, {}).get("board", u["board"])
            p = _board_png(proj, board) if board else None
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
 .tabs{display:flex;gap:4px;padding:6px 12px 0;align-items:center;flex-wrap:wrap}
 .tabs.eps{padding-top:2px}
 .tab{padding:6px 14px;border:1px solid #ddd;border-radius:8px 8px 0 0;background:#eef0f3;cursor:pointer;font-size:13px}
 .tabs.works .tab.active{background:#1a5fb4;color:#fff;font-weight:700;border-color:#1a5fb4}
 .tabs.eps .tab.active{background:#fff;font-weight:700;border-color:#1a5fb4;color:#1a5fb4}
 .tab.add{background:#e8f0ff;color:#1a5fb4;border-color:#bcd}
 .toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:8px 12px;font-size:12px;border-top:1px solid #eee}
 .summary{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
 .pill{padding:2px 9px;border-radius:10px;font-size:12px;background:#eef0f3}
 .pill.ok{background:#dff3e6;color:#0a5} .pill.ng{background:#fde2e2;color:#d1242f} .pill.run{background:#fff3d6;color:#a36a00}
 .pbar{height:8px;width:140px;background:#e6e8eb;border-radius:5px;overflow:hidden}
 .pbar>i{display:block;height:100%;background:#1a7f37}
 .grow{flex:1}
 main{padding:12px}
 .ovbox{background:#fff;border:1px solid #ddd;border-radius:10px;padding:10px 12px;margin-bottom:12px}
 .ovbox summary{font-weight:700;color:#1a5fb4;cursor:pointer}
 .ovbox .synopsis{margin:8px 0;font-size:13px;line-height:1.6}
 .ovbox .scenes{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
 .ovbox .scenes span{background:#eef2f8;border-radius:6px;padding:2px 8px;font-size:11px;color:#345}
 .ovbox .mbtitle{font-size:12px;color:#666;margin:6px 0 4px}
 .mboards{display:flex;flex-wrap:wrap;gap:10px}
 .mboards figure{margin:0;width:140px} .mboards figcaption{font-size:10px;color:#555;margin-top:2px;line-height:1.3}
 .mboards img{width:140px;height:90px;object-fit:cover;border:1px solid #ddd;border-radius:6px;cursor:zoom-in;background:#fafafa}
 .mboards .noimg{width:140px;height:90px;border:1px dashed #ccc;border-radius:6px;display:flex;align-items:center;justify-content:center;color:#bbb;font-size:10px;text-align:center;padding:4px}
 .ovbox .note{font-size:10px;color:#999;margin-top:8px}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px}
 .card{background:#fff;border:1px solid #ddd;border-radius:10px;padding:10px;display:flex;flex-direction:column;gap:6px}
 .card.reject{border-color:#d1242f} .card.accepted{border-color:#1a7f37} .card.running{border-color:#bf8700;box-shadow:0 0 0 2px #ffe6a8}
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
 .prog{height:6px;background:#ffe6a8;border-radius:4px;overflow:hidden;display:none}
 .prog.on{display:block} .prog>i{display:block;height:100%;width:40%;background:#bf8700;animation:slide 1.1s infinite}
 @keyframes slide{0%{margin-left:-40%}100%{margin-left:100%}}
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
 .ov{position:fixed;inset:0;background:rgba(0,0,0,.5);display:none;align-items:center;justify-content:center;z-index:60}
 .ov .box{background:#fff;padding:16px;border-radius:10px;max-width:96vw;max-height:96vh;overflow:auto}
 #lb{z-index:70} #lb .box{background:none;padding:0} #lb img{max-width:94vw;max-height:90vh}
 #bpop{position:fixed;z-index:80;display:none;pointer-events:none;background:#fff;border:1px solid #888;border-radius:6px;padding:3px;box-shadow:0 4px 16px rgba(0,0,0,.3)}
 #bpop img{display:block;max-width:300px;max-height:220px} #bpop .cap{font-size:10px;color:#666;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 #gmodal .box{width:auto} #gmodal img{max-width:80vw;max-height:72vh;border:1px solid #ddd}
 #cmp .box{background:#fff;width:auto;max-width:96vw}
 .cmptabs button.on{background:#1a5fb4;color:#fff;border-color:#1a5fb4}
 .cmpSide{display:flex;gap:10px} .cmpSide figure{margin:0;text-align:center}
 .cmpSide figcaption{font-size:11px;color:#666;margin-bottom:3px}
 .cmpSide img{max-width:44vw;max-height:80vh;object-fit:contain;border:1px solid #eee;background:#fff;cursor:zoom-in}
 .cmpSlider{position:relative;display:inline-block;line-height:0;cursor:ew-resize;user-select:none;touch-action:none;border:1px solid #eee}
 .cmpSlider .cmpimg{display:block;max-width:90vw;max-height:82vh}
 .cmpSlider .cmptop{position:absolute;top:0;left:0;width:100%;height:100%;object-fit:contain}
 .cmpOverlay{position:relative;display:inline-block;line-height:0;border:1px solid #eee;background:#fff}
 .cmpOverlay .cmpimg{display:block;max-width:90vw;max-height:76vh}
 .cmpOverlay .cmptop{position:absolute;top:0;left:0;width:100%;height:100%;object-fit:contain}
 .cmpops{display:flex;align-items:center;gap:8px;margin-top:8px;font-size:12px}
 .cmpops input[type=range]{flex:1}
 .cmpdiv{position:absolute;top:0;bottom:0;width:0;border-left:2px solid #fff;box-shadow:0 0 0 1px rgba(0,0,0,.45);pointer-events:none}
 .cmpdiv::after{content:"◂▸";position:absolute;top:50%;left:-11px;transform:translateY(-50%);background:#1a5fb4;color:#fff;font-size:10px;padding:2px 3px;border-radius:3px}
 .cmptag{position:absolute;top:6px;font-size:11px;color:#fff;background:rgba(0,0,0,.55);padding:1px 6px;border-radius:4px;pointer-events:none}
 #modal .box{width:540px} #modal label{display:block;font-size:12px;margin:8px 0 2px;color:#444} #modal input{width:100%;padding:6px;font-size:13px}
</style></head><body>
<header>
 <div class="tabs works" id="works"></div>
 <div class="tabs eps" id="eps"></div>
 <div class="toolbar">
   担当 <select id="fAssignee" style="width:auto"><option value="">全部</option></select>
   状態 <select id="fStatus" style="width:auto"><option value="">全部</option><option>todo</option><option>generating</option><option>done</option><option>accepted</option><option>reject</option></select>
   <label><input type="checkbox" id="fResult"> 未生成のみ</label>
   <span class="grow"></span>
   <span class="summary" id="summary"></span>
   <button onclick="rescan()">フォルダ再取得</button><button onclick="refresh()">更新</button>
 </div>
</header>
<main><section id="ovbox"></section><div class="grid" id="grid"></div></main>

<div class="ov" id="lb" onclick="this.style.display='none'"><div class="box"><img id="lbimg"></div></div>
<div id="bpop"><img id="bpopImg"><div class="cap" id="bpopCap"></div></div>

<div class="ov" id="cmp" onclick="if(event.target===this)this.style.display='none'"><div class="box">
  <div class="bar" style="margin-bottom:8px;align-items:center">
    <b id="cmpTitle"></b><span class="grow"></span>
    <span class="cmptabs"><button id="cmpBside" onclick="setCmpMode('side')">横並び</button>
      <button id="cmpBslide" onclick="setCmpMode('slider')">スライダー比較</button>
      <button id="cmpBover" onclick="setCmpMode('overlay')">重ね合わせ</button></span>
    <button onclick="swapCmp()" title="原図↔生成結果を入れ替え">⇄ 入替</button>
    <button onclick="document.getElementById('cmp').style.display='none'">閉じる</button></div>
  <div id="cmpSide" class="cmpSide">
    <figure><figcaption id="cmpCapA">原図（前）</figcaption><img id="cmpSideA" onclick="lb(this.src)"></figure>
    <figure><figcaption id="cmpCapB">生成結果（後）</figcaption><img id="cmpSideB" onclick="lb(this.src)"></figure></div>
  <div id="cmpSlider" class="cmpSlider" style="display:none">
    <img id="cmpImgB" class="cmpimg">
    <img id="cmpImgA" class="cmpimg cmptop">
    <span class="cmptag" id="cmpTagL" style="left:6px">原図</span><span class="cmptag" id="cmpTagR" style="right:6px">生成結果</span>
    <div id="cmpDiv" class="cmpdiv"></div></div>
  <div id="cmpOverlay" class="cmpOverlay" style="display:none">
    <img id="cmpOvB" class="cmpimg"><img id="cmpOvA" class="cmpimg cmptop"></div>
  <div id="cmpOpsRow" class="cmpops" style="display:none">透過
    <input type="range" id="cmpOpacity" min="0" max="100" value="50" oninput="cmpOpac(this.value)">
    <span id="cmpOpacVal">50%</span><span class="muted" id="cmpOpacTag"></span></div>
  <div class="muted" style="margin-top:6px">スライダー: 画像上でマウス左右で境界移動。重ね合わせ: 透過スライダーで原図と生成結果を重ねて確認。</div>
</div></div>

<div class="ov" id="gmodal"><div class="box">
  <div class="bar" style="margin-bottom:8px"><b id="gTitle"></b><span class="grow"></span>
    <button onclick="document.getElementById('gmodal').style.display='none'">閉じる</button></div>
  <img id="gImg">
  <div class="bar" style="margin-top:10px;align-items:center">原図ソース:
    <label><input type="radio" name="gsrc" value="base"> 自動検出(Base)</label>
    <label><input type="radio" name="gsrc" value="visible"> 見たまま(visible)</label>
    <button class="primary" onclick="recapture()">この設定で取得しなおす</button>
    <span id="gMsg" class="muted"></span></div>
  <div class="muted">PhotoshopでPSDを直して保存→ここで「取得しなおす」。Baseは背景レイヤー自動検出、visibleは表示中の全レイヤー合成。</div>
</div></div>

<div class="ov" id="modal"><div class="box">
  <h3 style="margin:0 0 6px" id="mTitle">作品・話数を追加（フォルダから取得）</h3>
  <label>作品名</label><input id="mWork" placeholder="尚善">
  <label>話数</label><input id="mEp" placeholder="08">
  <label>原図フォルダのフルパス（中を再帰走査）</label><input id="mGenzu" placeholder="C:\\...\\00.原図">
  <label>美術ボードフォルダのフルパス（任意）</label><input id="mBoards" placeholder="C:\\...\\美術ボード">
  <div class="bar" style="margin-top:12px"><button class="primary" onclick="addProject()">追加</button>
   <button onclick="document.getElementById('modal').style.display='none'">キャンセル</button>
   <span id="mMsg" class="muted"></span></div>
</div></div>
<script>
let UNITS=[],PROJECTS=[],WORK=null,GROUP=null,BOARDS=[],GCUR=null,BOARDFILES=false;
let CMPMODE=(function(){try{return localStorage.getItem('cmpmode')||'side'}catch(e){return 'side'}})();
let CMPSWAP=false,CMPSRC={g:'',r:''};
const RUN=new Set();
const $=s=>document.querySelector(s);
const esc=s=>(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;');
async function post(u,b){return (await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})})).json();}
function lb(src){const im=$('#lbimg');im.onerror=null;im.src=src;$('#lb').style.display='flex';}
function unit(id){return UNITS.find(u=>u.id===id);}
// 生成前後比較（通常=横並び / スライダー比較）
function setCmpMode(m){CMPMODE=m;try{localStorage.setItem('cmpmode',m)}catch(e){}
  const side=m==='side',slider=m==='slider',over=m==='overlay';
  $('#cmpSide').style.display=side?'flex':'none';
  $('#cmpSlider').style.display=slider?'inline-block':'none';
  $('#cmpOverlay').style.display=over?'inline-block':'none';
  $('#cmpOpsRow').style.display=over?'flex':'none';
  $('#cmpBside').classList.toggle('on',side);$('#cmpBslide').classList.toggle('on',slider);
  $('#cmpBover').classList.toggle('on',over);
  if(slider)setSplit(50);
  if(over)cmpOpac($('#cmpOpacity').value);}
function cmpOpac(v){$('#cmpOvA').style.opacity=(v/100);$('#cmpOpacVal').textContent=v+'%';}
function setSplit(pct){pct=Math.max(0,Math.min(100,pct));
  $('#cmpImgA').style.clipPath='inset(0 '+(100-pct)+'% 0 0)';$('#cmpDiv').style.left=pct+'%';}
function cmpMove(e){const r=$('#cmpSlider').getBoundingClientRect();
  if(r.width)setSplit((e.clientX-r.left)/r.width*100);}
function applyCmp(){const g=CMPSRC.g,r=CMPSRC.r,left=CMPSWAP?r:g,right=CMPSWAP?g:r;
  $('#cmpSideA').src=left;$('#cmpSideB').src=right;$('#cmpImgA').src=left;$('#cmpImgB').src=right;
  $('#cmpOvB').src=left;$('#cmpOvA').src=right;
  const la=CMPSWAP?'生成結果（後）':'原図（前）',lb2=CMPSWAP?'原図（前）':'生成結果（後）';
  $('#cmpCapA').textContent=la;$('#cmpCapB').textContent=lb2;
  $('#cmpTagL').textContent=CMPSWAP?'生成結果':'原図';$('#cmpTagR').textContent=CMPSWAP?'原図':'生成結果';
  $('#cmpOpacTag').textContent='下:'+(CMPSWAP?'生成結果':'原図')+' ／ 上:'+(CMPSWAP?'原図':'生成結果');}
function swapCmp(){CMPSWAP=!CMPSWAP;applyCmp();}
function openCmp(id){const u=unit(id);if(!u)return;
  if(!u.has_result){lb('/img/'+id+'/genzu?t='+Date.now());return;}
  $('#cmpTitle').textContent='生成前後比較 c'+u.cuts.join(',');
  const t=Date.now();CMPSRC={g:'/img/'+id+'/genzu?t='+t,r:'/img/'+id+'/result?t='+t};
  applyCmp();setCmpMode(CMPMODE);$('#cmp').style.display='flex';}
function showBoard(id){const u=unit(id);
  if(!u.board){slog(id,'ボード未選択（プルダウンで選択）');return;}
  if(!BOARDFILES){alert('美術ボード画像の場所が未設定です（起動時に --boards-dir を指定）。\n選択中のボード: '+u.board);return;}
  const im=$('#lbimg');im.onerror=()=>{im.onerror=null;$('#lb').style.display='none';alert('ボード画像が見つかりません: '+u.board);};
  im.src='/img/'+id+'/board?t='+Date.now();$('#lb').style.display='flex';}
function boardHover(id,e){const u=unit(id);const p=$('#bpop');
  if(!u||!u.board||!BOARDFILES){p.style.display='none';return;}
  if($('#bpopImg').dataset.id!==id){$('#bpopImg').dataset.id=id;$('#bpopImg').src='/img/'+id+'/board?t='+Date.now();$('#bpopCap').textContent=u.board;}
  const pad=14,w=320,vw=window.innerWidth;
  p.style.left=Math.min(e.clientX+pad,vw-w)+'px';p.style.top=(e.clientY+pad)+'px';p.style.display='block';}
function boardOut(){$('#bpop').style.display='none';}
async function refresh(){
  PROJECTS=await (await fetch('/api/projects')).json();
  UNITS=await (await fetch('/api/units')).json();
  UNITS.forEach(u=>{if(u.running)RUN.add(u.id);});
  const works=[...new Set(PROJECTS.map(p=>p.work))];
  if(!WORK||!works.includes(WORK)) WORK=works[0];
  const eps=PROJECTS.filter(p=>p.work===WORK);
  if(!GROUP||!eps.some(p=>p.group===GROUP)) GROUP=eps[0]&&eps[0].group;
  $('#works').innerHTML=works.map(w=>`<div class="tab ${w===WORK?'active':''}" data-w="${esc(w)}">${esc(w)}</div>`).join('')
    +'<div class="tab add" onclick="openAdd(\'\')">＋作品</div>';
  $('#eps').innerHTML=eps.map(p=>`<div class="tab ${p.group===GROUP?'active':''}" data-g="${esc(p.group)}">#${esc(p.ep)}</div>`).join('')
    +`<div class="tab add" onclick="openAdd('${esc(WORK)}')">＋話数</div>`;
  document.querySelectorAll('#works .tab[data-w]').forEach(t=>t.onclick=()=>{WORK=t.dataset.w;GROUP=null;refresh();});
  document.querySelectorAll('#eps .tab[data-g]').forEach(t=>t.onclick=()=>{GROUP=t.dataset.g;refresh();});
  const cur=PROJECTS.find(p=>p.group===GROUP); BOARDS=cur?cur.boards_opts:[]; BOARDFILES=cur?!!cur.has_board_files:false;
  const a=new Set(UNITS.filter(u=>u.group===GROUP).map(u=>u.assignee));
  const sel=$('#fAssignee'),c=sel.value;
  sel.innerHTML='<option value="">全部</option>'+[...a].sort().map(x=>`<option ${x===c?'selected':''}>${x}</option>`).join('');
  renderOverview(cur);
  render();
}
async function renderOverview(cur){
  const box=$('#ovbox'); if(!cur){box.innerHTML='';return;}
  let o; try{o=await (await fetch('/api/overview?key='+encodeURIComponent(cur.key))).json();}catch(e){box.innerHTML='';return;}
  if(o.error){box.innerHTML='';return;}
  const scenes=(o.scenes||[]).map(s=>`<span>${esc(s.label)} <b>c${esc(s.cuts)}</b></span>`).join('');
  const top=(o.boards||[]).slice(0,8);
  const mb=top.map(b=>{
    const u='/board-img?key='+encodeURIComponent(cur.key)+'&name='+encodeURIComponent(b.board);
    const cap=esc(b.board)+' ×'+b.cuts;
    return `<figure>${b.has_img?`<img loading="lazy" src="${u}" onclick="lb('${u}')">`:`<div class="noimg">${esc(b.board)}</div>`}<figcaption>${cap}</figcaption></figure>`;
  }).join('');
  box.innerHTML=`<details class="ovbox" open><summary>話数概要 — ${esc(cur.group)}</summary>
    ${o.synopsis?`<p class="synopsis">${esc(o.synopsis)}</p>`:'<p class="synopsis muted">（あらすじ未登録）</p>'}
    ${scenes?`<div class="scenes">${scenes}</div>`:''}
    <div class="mbtitle">主要シーンの美術ボード（登場カット数が多い順）</div>
    ${mb?`<div class="mboards">${mb}</div>`:'<div class="muted">ボード未割当 / 画像なし</div>'}
    ${o.note?`<div class="note">${esc(o.note)}</div>`:''}</details>`;
}
function render(){
  const fa=$('#fAssignee').value,fs=$('#fStatus').value,fr=$('#fResult').checked;
  const all=UNITS.filter(u=>u.group===GROUP);
  const us=all.filter(u=>(!fa||u.assignee===fa)&&(!fs||u.status===fs)&&(!fr||!u.has_result));
  const gen=all.filter(u=>u.has_result).length, ok=all.filter(u=>u.status==='accepted').length, ng=all.filter(u=>u.status==='reject').length;
  const pct=all.length?Math.round(ok/all.length*100):0;
  const running=[...RUN].map(unit).filter(u=>u&&u.group===GROUP);
  $('#summary').innerHTML=(running.length?`<span class="pill run">⏳生成中 ${running.length}: c${running.map(u=>u.cuts.join(',')).join(' / c')}</span>`:'')
    +`<span class="pill">全${all.length}</span><span class="pill">生成済 ${gen}</span>`
    +`<span class="pill ok">OK ${ok}</span><span class="pill ng">要修正 ${ng}</span><span class="pill">未生成 ${all.length-gen}</span>`
    +`<div class="pbar"><i style="width:${pct}%"></i></div><span class="muted">${pct}% OK</span>`;
  $('#grid').innerHTML=us.map(card).join('');
  us.forEach(u=>{if(RUN.has(u.id))markRunning(u.id,true);});
}
function card(u){
  const t=Date.now();
  const opts='<option value="">— ボード未選択 —</option>'+BOARDS.map(b=>`<option ${b===u.board?'selected':''}>${esc(b)}</option>`).join('');
  return `<div class="card ${u.status} ${RUN.has(u.id)?'running':''}" id="card_${u.id}">
   <div class="chead"><span class="cut">c${u.cuts.join(',')}</span>
     <span class="who ${u.assignee==='GKV'?'gkv':'other'}">${u.assignee}</span>
     <span class="b ${u.status}">${u.status}</span>${u.retakes?`<span class="muted">RT${u.retakes}</span>`:''}
     ${u.has_psd?'':'<span class="muted">PSD無</span>'}<span class="scene">${esc(u.scene)}</span></div>
   <div class="thumbs">
     <figure><figcaption>原図[${u.genzu_source}] ${u.has_psd?`<a href="#" onclick="openPsd('${u.id}');return false">PSDを開く</a> · <a href="#" onclick="openGenzu('${u.id}');return false">拡大/取り直し</a>`:''}</figcaption>
       ${u.has_psd?`<img loading="lazy" src="/img/${u.id}/genzu" onclick="openGenzu('${u.id}')" onerror="this.outerHTML='<div class=ph>原図なし</div>'">`:'<div class="ph">PSD未検出</div>'}</figure>
     <figure><figcaption>生成結果 ${u.has_result?`<a href="#" onclick="openCmp('${u.id}');return false">前後比較</a>`:''}</figcaption>${u.has_result?`<img loading="lazy" src="/img/${u.id}/result?t=${t}" onclick="openCmp('${u.id}')">`:'<div class="ph">未生成</div>'}</figure>
   </div>
   <div class="prog ${RUN.has(u.id)?'on':''}" id="prog_${u.id}"><i></i></div>
   <div class="bar"><select style="flex:1;width:auto" onchange="setBoard('${u.id}',this.value)">${opts}</select>
     <button onclick="showBoard('${u.id}')" onmousemove="boardHover('${u.id}',event)" onmouseleave="boardOut()" title="クリックで拡大／ホバーでプレビュー">ボード表示</button></div>
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
function markRunning(id,on){const c=document.getElementById('card_'+id),p=document.getElementById('prog_'+id);
  if(c)c.classList.toggle('running',on); if(p)p.classList.toggle('on',on);}
function openGenzu(id){const u=unit(id); GCUR=id; $('#gTitle').textContent='原図 c'+u.cuts.join(',');
  $('#gImg').src='/img/'+id+'/genzu?t='+Date.now();
  document.querySelectorAll('input[name=gsrc]').forEach(r=>r.checked=(r.value===u.genzu_source));
  $('#gMsg').textContent=''; $('#gmodal').style.display='flex';}
async function recapture(){const src=document.querySelector('input[name=gsrc]:checked').value; $('#gMsg').textContent='取得中…';
  const r=await post('/api/unit/'+GCUR+'/recapture',{source:src}); if(r.error){$('#gMsg').textContent='エラー: '+r.error;return;}
  $('#gImg').src='/img/'+GCUR+'/genzu?t='+Date.now(); $('#gMsg').textContent='取得しました（'+src+'）'; await refresh();}
async function openPsd(id){const r=await post('/api/unit/'+id+'/open',{}); slog(id,r.error?('開けません: '+r.error):'PSDを開きました');}
async function loadPrompt(id){const d=await (await fetch('/api/unit/'+id)).json(); const t=document.getElementById('pr_'+id); if(t)t.value=d.prompt;}
async function savePrompt(id){const t=document.getElementById('pr_'+id); await post('/api/unit/'+id+'/prompt',{prompt:t?t.value:''}); slog(id,'保存しました');}
async function resetPrompt(id){await post('/api/unit/'+id+'/prompt',{prompt:''}); const t=document.getElementById('pr_'+id); if(t)t.value=''; slog(id,'自動に戻しました');}
async function setBoard(id,v){await post('/api/unit/'+id+'/board',{board:v}); slog(id,'ボード保存');}
async function accept(id,v){await post('/api/unit/'+id+'/accept',{value:v}); const u=unit(id); if(u)u.status=v; render();}
function slog(id,m){const l=document.getElementById('log_'+id); if(l){l.style.display='block';l.textContent=m;}}
async function gen(id){
  const t=document.getElementById('pr_'+id); if(t&&t.value.trim()) await post('/api/unit/'+id+'/prompt',{prompt:t.value});
  const r=await post('/api/unit/'+id+'/generate',{}); if(r.error){slog(id,'エラー: '+r.error);return;}
  RUN.add(id); markRunning(id,true); const u=unit(id); if(u){u.status='generating';u.running=true;} render(); slog(id,'生成開始…(数分)');
  const c=document.getElementById('card_'+id); c&&c.querySelectorAll('.bar button').forEach(b=>b.disabled=true);
  const poll=setInterval(async()=>{const j=await (await fetch('/api/unit/'+id+'/job')).json();
    slog(id,(j.log||[]).join('\n'));
    if(j.status==='done'||j.status==='error'){clearInterval(poll); RUN.delete(id); await refresh();}},2500);
}
async function rescan(){const p=PROJECTS.find(x=>x.group===GROUP); if(!p)return; await post('/api/projects/'+encodeURIComponent(p.key)+'/rescan',{}); await refresh();}
function openAdd(work){$('#mWork').value=work||''; $('#mEp').value=''; $('#mGenzu').value=''; $('#mBoards').value='';
  $('#mTitle').textContent=work?(work+' に話数を追加'):'作品・話数を追加'; $('#mMsg').textContent=''; $('#modal').style.display='flex';}
async function addProject(){$('#mMsg').textContent='追加中…';
  const r=await post('/api/projects',{work:$('#mWork').value,ep:$('#mEp').value,genzu_dir:$('#mGenzu').value,boards_dir:$('#mBoards').value});
  if(r.error){$('#mMsg').textContent='エラー: '+r.error;return;}
  $('#modal').style.display='none'; WORK=$('#mWork').value||WORK; GROUP=null; await refresh();}
$('#fAssignee').onchange=render;$('#fStatus').onchange=render;$('#fResult').onchange=render;
$('#cmpSlider').addEventListener('pointermove',cmpMove);
document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('#cmp').style.display='none';$('#lb').style.display='none';$('#gmodal').style.display='none';}});
refresh();
</script></body></html>"""


def main(argv=None):
    p = argparse.ArgumentParser(prog="genzu_fix.server", description="原図修正コンソール")
    p.add_argument("--genzu-dir", required=True)
    p.add_argument("--out", default="work/console")
    p.add_argument("--csv", default="runs/cut_board_map_ep7.csv")
    p.add_argument("--boards-dir", default=None)
    p.add_argument("--boards-json", default="runs/boards_ep7.json")
    p.add_argument("--overview-json", default="runs/ep_overview.json")
    p.add_argument("--work", default="尚善")
    p.add_argument("--ep", default="07")
    p.add_argument("--resolution", default="2k")
    p.add_argument("--quality", default="high")
    p.add_argument("--model", default="gpt_image_2")
    p.add_argument("--image-flag", default="--image")
    p.add_argument("--include-book", action="store_true")
    p.add_argument("--header-top", type=int, default=None)
    p.add_argument("--cut-info", default="runs/cut_scene_info_ep7.csv")
    p.add_argument("--port", type=int, default=8765)
    a = p.parse_args(argv)
    # カット別 situation/remove（great-edisonの3層プロンプトCUT層）。在ればプロンプトに反映。
    cut_info_map = {}
    try:
        cut_info_map = batch.promptlib.load_cut_info(a.cut_info)
    except Exception:
        pass
    CFG.update(dict(out=a.out, csv=a.csv, boards_json=a.boards_json,
                    resolution=a.resolution, quality=a.quality, model=a.model,
                    image_flag=a.image_flag, include_book=a.include_book,
                    header_top=a.header_top, cut_info_map=cut_info_map))
    OVERVIEWS.update(_load_json(a.overview_json, {}))
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
