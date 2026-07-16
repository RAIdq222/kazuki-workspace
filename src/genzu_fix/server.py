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
import queue as _queue
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
# 生成ジョブは1本のキュー＋N本のワーカーで捌く（N=同時実行上限＝Higgsfield多重起動を防ぐ）。
GEN_QUEUE = _queue.Queue()
_WORKERS_LOCK = threading.Lock()
_WORKERS_STARTED = False


def _ensure_workers():
    global _WORKERS_STARTED
    with _WORKERS_LOCK:
        if _WORKERS_STARTED:
            return
        n = max(1, int(CFG.get("max_parallel", 3)))
        for _ in range(n):
            threading.Thread(target=_gen_worker, daemon=True).start()
        _WORKERS_STARTED = True


def _gen_worker():
    while True:
        uid = GEN_QUEUE.get()
        try:
            with JOBS_LOCK:
                j = JOBS.get(uid)
                if not j or j.get("status") != "queued":
                    continue  # キャンセル済み等
                j["status"] = "running"
                j["ts"] = time.time()
            _run_generate(uid)
        except Exception as e:  # noqa 念のためワーカーを殺さない
            with JOBS_LOCK:
                if uid in JOBS:
                    JOBS[uid].update(status="error", error=str(e)[:300])
        finally:
            GEN_QUEUE.task_done()

# 作品プレフィックス→和名。runs/works.json（作品レジストリ）から拡張される。
WORK_NAMES = {"shz": "尚善"}
try:
    from .assets import WORK_ALIASES as _WA
    for _k, _vs in _WA.items():
        if _k.isascii():
            _jp = next((v for v in _vs if not v.isascii()), None)
            if _jp:
                WORK_NAMES.setdefault(_k, _jp)
except Exception:  # noqa レジストリ不整合でもコンソールは起動する
    pass


def _state_path():
    return os.path.join(CFG["out"], "console_state.json")


def _projects_path():
    return os.path.join(CFG["out"], "projects.json")


def _save_state_locked():
    """STATE を state ファイルへアトミックに書く。呼び出し側が STATE_LOCK 保持前提。"""
    os.makedirs(CFG["out"], exist_ok=True)
    tmp = _state_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(STATE, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _state_path())  # 途中書きで壊さない（別スレッドの読込/次回起動を守る）


def _save_state():
    with STATE_LOCK:
        _save_state_locked()


def _update_state(uid, **kw):
    """STATE[uid] の変更と保存をロック内でまとめて行う（json.dump 中の同時変更を防ぐ）。"""
    with STATE_LOCK:
        STATE.setdefault(uid, {}).update(kw)
        _save_state_locked()


def _load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:  # 壊れていても起動を止めない
            try:
                os.replace(path, path + ".corrupt")  # 退避して原因を残す
            except OSError:
                pass
            print(f"[warn] {path} を読めませんでした（{e}）。既定値で起動します。")
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
    """フォルダ走査でカット表を作る（scene/assignee はサブフォルダ名から）。

    - 並びは**カット番号順**（フォルダの走査順ではない）。
    - 同名PSDが複数フォルダにある場合は最初に見つかった方を採用し、警告を出す
      （黙って上書きするとカット数が減って見える）。
    """
    units = {}
    dup = []
    n_psd = 0
    gd = os.path.abspath(genzu_dir)
    for root, _, files in os.walk(gd):
        for fn in sorted(files):
            if not fn.lower().endswith(".psd"):
                continue
            n_psd += 1
            uid = os.path.splitext(fn)[0]
            rel = os.path.relpath(os.path.join(root, fn), gd)
            if uid in units:
                dup.append((rel, units[uid]["_rel"]))
                continue
            info = naming.parse_cut_codes(fn)
            cuts = info.get("cuts") or [uid]
            parts = rel.split(os.sep)
            scene = next((p for p in parts[:-1] if re.search(r"c\d", p)), "")
            parent = parts[-2] if len(parts) >= 2 else ""
            assignee = parent if (parent and not re.search(r"c\d", parent)) else "(直下)"
            units[uid] = {"id": uid, "filename": fn, "cuts": cuts,
                          "assignee": assignee, "scene": scene, "board": "", "_rel": rel}

    def cut_key(u):
        m = re.match(r"(\d+)([A-Za-z]*)", (u["cuts"][0] if u["cuts"] else ""))
        return (int(m.group(1)), m.group(2)) if m else (10 ** 9, u["id"])

    ordered = {u["id"]: {k: v for k, v in u.items() if k != "_rel"}
               for u in sorted(units.values(), key=cut_key)}
    print(f"[scan] {gd}: PSD {n_psd}枚 → {len(ordered)}ユニット")
    for a, b in dup:
        print(f"  [warn] 同名PSDが複数あります（採用: {b} / 無視: {a}）")
    return ordered


def _load_board_map(path):
    """cut,board のCSV → {正規化カット番号: ボード名}（前ゼロ落とし・枝番保持）。"""
    out = {}
    if not (path and os.path.exists(path)):
        return out
    import csv as _csv
    with open(path, encoding="utf-8-sig") as f:
        for r in _csv.DictReader(f):
            m = re.match(r"0*(\d+)([A-Za-z]?)", (r.get("cut") or "").strip())
            if m and (r.get("board") or "").strip():
                out[m.group(1) + m.group(2).upper()] = r["board"].strip()
    return out


def _load_staging_map(path):
    """cut,staging,confidence のCSV → {正規化カット番号: {"staging","confidence"}}。
    scene_understanding(build_staging.py)の下書き。手動保存(state.staging)が常に優先。"""
    out = {}
    if not (path and os.path.exists(path)):
        return out
    import csv as _csv
    with open(path, encoding="utf-8-sig") as f:
        for r in _csv.DictReader(f):
            m = re.match(r"0*(\d+)([A-Za-z]?)", (r.get("cut") or "").strip())
            if m and (r.get("staging") or "").strip():
                out[m.group(1) + m.group(2).upper()] = {
                    "staging": r["staging"].strip(),
                    "confidence": (r.get("confidence") or "").strip()}
    return out


def _unit_staging(proj, u, st):
    """このユニットに効く staging を返す (text, source, confidence)。手動 > 自動下書き。"""
    manual = (st.get("staging") or "").strip()
    if manual:
        return manual, "manual", ""
    m = re.match(r"0*(\d+)([A-Za-z]?)", (u["cuts"][0] if u.get("cuts") else ""))
    if m:
        auto = (proj.get("staging_map") or {}).get(m.group(1) + m.group(2).upper())
        if auto:
            return auto["staging"], "auto", auto.get("confidence", "")
    return "", "", ""


def _proj_genzu_trust(proj) -> str:
    """原図信頼度モード。"high"=3Dレイアウト出し等で幾何が正＝忠実清書（SP2）/
    "rough"=手描きラフで狂いがある前提＝修正パス（尚善・既定）。project json で宣言。"""
    return (proj or {}).get("genzu_trust") or "rough"


def _proj_include_book(proj) -> bool:
    """BOOKを原図に含めるか（作品ごと。SP2はBook=椅子等がシーンの空間アンカーなので含める）。"""
    v = (proj or {}).get("include_book")
    return bool(CFG.get("include_book")) if v is None else bool(v)


def _make_project(key, work, ep, genzu_dir, boards_dir=None, csv_path=None, source="scan",
                  out_dir=None, cut_info=None, board_map=None, include_book=None,
                  staging_map=None, genzu_trust=None):
    if source == "csv":
        units = _units_from_csv(csv_path)
    else:
        units = _units_from_folder(genzu_dir)
    # カット→ボードの紐づけ表（scan構成の作品向け。CSV構成でも空欄の補完に使う）
    bmap = _load_board_map(board_map)
    if bmap:
        n = 0
        for u in units.values():
            if u.get("board"):
                continue
            m = re.match(r"0*(\d+)([A-Za-z]?)", (u["cuts"][0] if u["cuts"] else ""))
            b = bmap.get(m.group(1) + m.group(2).upper()) if m else None
            if b:
                u["board"] = b
                n += 1
        print(f"[board_map] {key}: {n}/{len(units)} ユニットにボードを紐づけ（{board_map}）")
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
    # カット別 situation/remove（プロンプトCUT層）は作品ごと（他作品の同番カットに混ぜない）
    cut_info_map = {}
    if cut_info and os.path.exists(cut_info):
        try:
            cut_info_map = batch.promptlib.load_cut_info(cut_info)
        except Exception:
            pass
    return {
        "key": key, "work": work, "ep": ep, "group": f"{work} #{ep}",
        "genzu_dir": genzu_dir, "boards_dir": boards_dir, "csv": csv_path, "source": source,
        "out_dir": out_dir or CFG.get("out"), "cut_info_map": cut_info_map,
        "include_book": include_book, "staging_map": _load_staging_map(staging_map),
        "genzu_trust": genzu_trust,
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
    # 出力は作品(プロジェクト)ごとの out_dir 配下（尚善とSP2の生成結果を混ぜない）
    proj, _ = _find_unit(uid)
    base = (proj or {}).get("out_dir") or CFG["out"]
    return os.path.join(base, uid)


def _result_path(uid):
    # restored_full.png は原図画角へ戻した最終結果＝原図と画角一致（比較スライダーが揃う）。
    # 無ければ生成直後の gen_raw.png にフォールバック。
    d = _unit_dir(uid)
    for n in ("restored_full.png", "gen_raw.png"):
        p = os.path.join(d, n)
        if os.path.exists(p):
            return p
    return None


def _take_dir(uid, n):
    return os.path.join(_unit_dir(uid), "takes", f"take_{int(n):02d}")


def _snapshot_take(uid):
    """生成直後の結果を takes/take_NN/ に退避（上書きで前版を失わないため）。戻り: テイク番号。"""
    import shutil
    ud = _unit_dir(uid)
    src = os.path.join(ud, "restored_full.png")
    if not os.path.exists(src):
        return None
    with STATE_LOCK:
        takes = STATE.setdefault(uid, {}).setdefault("takes", [])
        n = (max(t["n"] for t in takes) + 1) if takes else 1
    tdir = _take_dir(uid, n)
    os.makedirs(tdir, exist_ok=True)
    for fn in ("restored_full.png", "gen_raw.png", "prompt.en.txt", "qc.json"):
        p = os.path.join(ud, fn)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(tdir, fn))
    qv = _load_json(os.path.join(ud, "qc.json"), {}).get("verdict")
    with STATE_LOCK:
        note = (STATE.get(uid, {}).get("retake_note") or "").strip()
        STATE.setdefault(uid, {}).setdefault("takes", []).append(
            {"n": n, "ts": time.time(), "qc": qv, "note": note})
        STATE[uid]["adopted"] = n
        _save_state_locked()
    return n


def _adopt_take(uid, n):
    """過去テイクを現行結果に採用（root へ戻す＋qcも切替）。best-effort で PSD 再差し込み。"""
    import shutil
    tdir = _take_dir(uid, n)
    src = os.path.join(tdir, "restored_full.png")
    if not os.path.exists(src):
        return False
    ud = _unit_dir(uid)
    shutil.copy2(src, os.path.join(ud, "restored_full.png"))
    for fn in ("gen_raw.png", "prompt.en.txt", "qc.json"):
        p = os.path.join(tdir, fn)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(ud, fn))
    _update_state(uid, adopted=int(n))
    return True


_PREVIEW_REV = "r4"   # 抽出規則を変えたら上げる（旧キャッシュを使わせない）


def _genzu_preview(uid, psd_path, source="base", force=False):
    # ソース別ファイル名（base/visible を分離）＋ process_cut の中間 visible.png と衝突させない。
    out = os.path.join(_unit_dir(uid), f"genzu_{source}_{_PREVIEW_REV}.png")
    stale = bool(psd_path and os.path.exists(out) and os.path.exists(psd_path)
                 and os.path.getmtime(psd_path) > os.path.getmtime(out))  # PSD更新で再取得
    if (force or stale or not os.path.exists(out)) and psd_path:
        os.makedirs(_unit_dir(uid), exist_ok=True)
        try:
            if source == "visible":
                psd_export.export_visible_to_png(psd_path, out, drop_text=False)
            elif source == "override":
                names = set(STATE.get(uid, {}).get("layers_show") or [])
                allnames = [li.name for li in psd_export.list_layers(psd_path)]
                psd_export.export_with_overrides(
                    psd_path, out, show=names, hide={n for n in allnames if n not in names})
            else:
                proj, _u = _find_unit(uid)
                psd_export.export_background_layer(psd_path, out,
                                                   include_book=_proj_include_book(proj))
        except Exception as e:  # noqa
            print(f"[warn] 原図プレビュー失敗 {uid}/{source}: {str(e)[:200]}")
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
                                    cut_info_map=(proj.get("cut_info_map") or CFG.get("cut_info_map")),
                                    staging=_unit_staging(proj, u, st)[0] or None,
                                    genzu_trust=_proj_genzu_trust(proj))
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
    st = STATE.get(uid, {})
    prev_status = st.get("status", "todo")   # 失敗時に戻す（「生成中」で固まらせない）
    board = st.get("board", u["board"])
    # ボードは常に全景で参照する（画風・意匠・「どの角度から見た場所か」の根拠）。
    # 構図の乗っ取りはプロンプトの意匠辞書ルール（batch側 [IMAGES]）で抑える。
    board_path = _board_png(proj, board) if (proj.get("boards_dir") and board) else None
    # リテイク指示（端的な修正メモ）があれば、最終プロンプト末尾へ最優先の修正指示として足す。
    note = (st.get("retake_note") or "").strip()
    base_prompt = st.get("prompt") or None
    if note:
        cut0 = u["cuts"][0] if u.get("cuts") else ""
        eff = base_prompt or batch.build_prompt_pair(
            board, u["scene"], None, cut=cut0,
            cut_info_map=(proj.get("cut_info_map") or CFG.get("cut_info_map")),
            staging=_unit_staging(proj, u, st)[0] or None,
            genzu_trust=_proj_genzu_trust(proj))[0]
        base_prompt = eff + "\n\n[RETAKE CORRECTION — apply with top priority]: " + note
    try:
        log("prep→生成→finish 実行中…" + (f"（指示: {note[:30]}）" if note else ""))
        batch.process_cut(psd, board, u["scene"], _unit_dir(uid), base_prompt,
                          CFG["resolution"], CFG["quality"], CFG["model"], CFG["image_flag"],
                          dry=False, include_book=_proj_include_book(proj),
                          staging=_unit_staging(proj, u, st)[0] or None,
                          genzu_trust=_proj_genzu_trust(proj),
                          header_top=CFG["header_top"], board_path=board_path,
                          genzu_source=st.get("genzu_source", "base"),
                          genzu_layers=st.get("layers_show"),
                          cut_num=(u["cuts"][0] if u.get("cuts") else ""),
                          cut_info_map=(proj.get("cut_info_map") or CFG.get("cut_info_map")),
                          qc_vision=CFG.get("qc_vision", False))
        n = _snapshot_take(uid)   # 上書きせず takes/take_NN/ に保存（S5・前版を失わない）
        with STATE_LOCK:
            s = STATE.setdefault(uid, {})
            if s.get("generated_once"):
                s["retakes"] = s.get("retakes", 0) + 1
            s["generated_once"] = True
            s["status"] = "done"
            s["last_run"] = time.time()
            _save_state_locked()
        with JOBS_LOCK:
            JOBS[uid].update(status="done")
        log(f"完了（テイク{n}）" if n else "完了")
    except Exception as e:  # noqa
        # 「生成中」のまま固めない＝元の状態へ戻す（再生成できるように）
        _update_state(uid, status=(prev_status if prev_status != "generating" else "todo"))
        with JOBS_LOCK:
            JOBS[uid].update(status="error", error=str(e)[:300])
        log("失敗: " + str(e)[:200])
        # コンソール窓にも必ず出す（UIを見ていなくても原因が分かるように）
        print(f"    [gen] {uid} 失敗: {str(e)[:300]}")


def _enqueue(uids, force):
    """生成キューに積む。force=False は冪等（既生成/原図待ちをスキップ）。
    戻り: (queued[uid...], skipped[(uid,理由)...])。理由= no_psd / done / busy。"""
    queued, skipped = [], []
    for uid in uids:
        proj, u = _find_unit(uid)
        if not u:
            skipped.append((uid, "not_found"))
            continue
        if u["filename"] not in proj["psd_idx"]:
            skipped.append((uid, "no_psd"))          # 原図待ち＝スキップ（後日rescanで拾う）
            continue
        if not force and _result_path(uid):
            skipped.append((uid, "done"))            # 既生成＝スキップ（S2冪等・再課金防止）
            continue
        with JOBS_LOCK:
            if JOBS.get(uid, {}).get("status") in ("queued", "running"):
                skipped.append((uid, "busy"))
                continue
            JOBS[uid] = {"status": "queued", "log": [], "error": None, "ts": time.time()}
        _update_state(uid, status="generating")
        GEN_QUEUE.put(uid)
        queued.append(uid)
    if queued:
        _ensure_workers()
    return queued, skipped


def create_app():
    from flask import Flask, jsonify, request, send_file, Response
    app = Flask(__name__)

    def unit_view(proj, u):
        uid = u["id"]
        st = STATE.get(uid, {})
        with JOBS_LOCK:
            j = JOBS.get(uid, {})
            running = j.get("status") == "running"
            gen_error = j.get("error") if j.get("status") == "error" else None
        q = _load_json(os.path.join(_unit_dir(uid), "qc.json"), {})
        return {"id": uid, "cuts": u["cuts"], "assignee": u["assignee"], "scene": u["scene"],
                "board": st.get("board", u["board"]), "group": proj["group"], "project": proj["key"],
                "work": proj["work"], "ep": proj["ep"],
                "has_psd": u["filename"] in proj["psd_idx"],
                "status": st.get("status", "todo"), "running": running, "gen_error": gen_error,
                "genzu_source": st.get("genzu_source", "base"),
                "genzu_rev": st.get("genzu_rev", 0),
                "has_result": _result_path(uid) is not None,
                "qc_verdict": q.get("verdict"), "qc_reasons": q.get("reasons", []),
                "takes": st.get("takes", []), "adopted": st.get("adopted"),
                "retake_note": st.get("retake_note", ""), "staging": st.get("staging", ""),
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
                        "boards": boards, "boards_dir": proj.get("boards_dir") or "",
                        "board_count": len(proj.get("board_idx") or {})})

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
        st = STATE.get(uid, {})
        board = st.get("board", u["board"])
        cut = (u["cuts"][0] if u.get("cuts") else "")
        cim = proj.get("cut_info_map") or CFG.get("cut_info_map") or {}
        stg_text, stg_src, stg_conf = _unit_staging(proj, u, st)
        _, jp = batch.build_prompt_pair(board, u["scene"], None, cut=cut, cut_info_map=cim,
                                        staging=stg_text or None,
                                        genzu_trust=_proj_genzu_trust(proj))
        # コンテ由来の場面情報（詳細画面の日本語概要＋OCR信頼度の表示に使う）
        info = cim.get(batch.promptlib._norm_cut(cut)) if cim else None
        ci = {}
        if info:
            m = re.search(r"conf:(\w+)", info.source or "")
            ci = {"place": info.place, "time": info.time, "situation": info.situation,
                  "scene_key": info.scene_key, "conf": (m.group(1) if m else ""),
                  "source": info.source}
        return jsonify({**unit_view(proj, u), "filename": u["filename"],
                        "prompt": _effective_prompt(proj, u), "prompt_jp": jp or "",
                        "staging": stg_text, "staging_source": stg_src,
                        "staging_conf": stg_conf,
                        "cut_info": ci, "boards_opts": proj["boards_opts"]})

    @app.post("/api/unit/<uid>/prompt")
    def api_prompt(uid):
        _update_state(uid, prompt=(request.json or {}).get("prompt", "").strip() or None)
        return jsonify({"ok": True})

    @app.post("/api/unit/<uid>/board")
    def api_board(uid):
        _update_state(uid, board=(request.json or {}).get("board", ""))
        return jsonify({"ok": True})

    @app.post("/api/unit/<uid>/retake_note")
    def api_retake_note(uid):
        _update_state(uid, retake_note=(request.json or {}).get("note", "").strip())
        return jsonify({"ok": True})

    @app.post("/api/unit/<uid>/staging")
    def api_staging(uid):
        # 画角・場面の言語記述（構図の主チャンネル。日本語OK・最優先ブロックとして生成に入る）
        _update_state(uid, staging=(request.json or {}).get("text", "").strip())
        return jsonify({"ok": True})

    @app.post("/api/unit/<uid>/accept")
    def api_accept(uid):
        _update_state(uid, status=(request.json or {}).get("value", "accepted"))
        return jsonify({"ok": True})

    @app.get("/api/unit/<uid>/layers")
    def api_layers(uid):
        proj, u = _find_unit(uid)
        if not u:
            return jsonify({"error": "not found"}), 404
        psd = proj["psd_idx"].get(u["filename"])
        if not psd:
            return jsonify({"error": "PSDが見つかりません"}), 404
        try:
            layers = [{"name": li.name, "kind": li.kind, "visible": li.visible, "depth": li.depth}
                      for li in psd_export.list_layers(psd)]
        except Exception as e:  # noqa
            return jsonify({"error": str(e)[:200]}), 500
        return jsonify({"layers": layers, "selected": STATE.get(uid, {}).get("layers_show", [])})

    @app.post("/api/unit/<uid>/recapture")
    def api_recapture(uid):
        proj, u = _find_unit(uid)
        if not u:
            return jsonify({"error": "not found"}), 404
        b = request.json or {}
        source = b.get("source", "base")
        # genzu_rev: 取り直しごとに上げ、カードのサムネイルURLを変えてブラウザキャッシュを外す
        kw = {"genzu_source": source,
              "genzu_rev": int(STATE.get(uid, {}).get("genzu_rev", 0)) + 1}
        if source == "override":
            kw["layers_show"] = list(b.get("layers") or [])
        _update_state(uid, **kw)
        psd = proj["psd_idx"].get(u["filename"])
        p = _genzu_preview(uid, psd, source=source, force=True)
        if not p:
            return jsonify({"error": "原図の取得に失敗（PSD未検出? / レイヤー未選択?）"}), 400
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
        # 単体生成はユーザーの明示操作＝force（リテイク含む）。キュー経由で同時数を守る。
        q, s = _enqueue([uid], force=True)
        if not q:
            reason = dict(s).get(uid, "error")
            if reason == "busy":
                return jsonify({"error": "already running"}), 409
            return jsonify({"error": reason}), 400
        return jsonify({"ok": True, "queued": 1})

    @app.post("/api/generate_batch")
    def api_generate_batch():
        b = request.json or {}
        force = bool(b.get("force"))
        uids = b.get("uids")
        # scope 指定時はグループ内から候補を集め、done/no_psd の判定は _enqueue に委ねる
        # （スキップ理由を集計してユーザーに見せるため）。
        if uids is None:
            group = b.get("group")
            scope = b.get("scope", "ungenerated")  # ungenerated | failed
            uids = []
            for p in PROJECTS.values():
                if group and p["group"] != group:
                    continue
                for u in p["units"].values():
                    uid = u["id"]
                    if scope == "failed":
                        with JOBS_LOCK:
                            if JOBS.get(uid, {}).get("status") == "error":
                                uids.append(uid)
                    elif STATE.get(uid, {}).get("status") != "accepted":  # OK済は対象外
                        uids.append(uid)
            if scope == "failed":
                force = True  # 失敗の再実行は明示再生成
        q, s = _enqueue(uids, force=force)
        from collections import Counter
        return jsonify({"queued": len(q), "skipped": len(s),
                        "skip_reasons": dict(Counter(r for _, r in s))})

    @app.post("/api/unit/<uid>/adopt")
    def api_adopt(uid):
        n = (request.json or {}).get("take")
        if not _adopt_take(uid, n):
            return jsonify({"error": "テイクが見つかりません"}), 404
        return jsonify({"ok": True, "adopted": int(n)})

    @app.get("/api/jobs")
    def api_jobs():
        with JOBS_LOCK:
            active = {uid: {"status": j["status"], "error": j.get("error")}
                      for uid, j in JOBS.items() if j.get("status") in ("queued", "running")}
            counts = {}
            for j in JOBS.values():
                counts[j.get("status")] = counts.get(j.get("status"), 0) + 1
        return jsonify({"active": active, "counts": counts,
                        "busy": len(active), "qsize": GEN_QUEUE.qsize()})

    @app.get("/api/unit/<uid>/job")
    def api_job(uid):
        with JOBS_LOCK:
            return jsonify(dict(JOBS.get(uid, {"status": "idle", "log": [], "error": None})))

    @app.get("/img/<uid>/take/<int:n>")
    def img_take(uid, n):
        p = os.path.join(_take_dir(uid, n), "restored_full.png")
        if not os.path.exists(p):
            return "", 404
        return send_file(os.path.abspath(p))

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
 .rnote{width:100%;font-size:12px;padding:4px 6px;border:1px solid #cbd;border-radius:6px;background:#fbfcff}
 .takes{font-size:11px;color:#666;display:flex;flex-wrap:wrap;gap:4px;align-items:center}
 .takechip{font-size:11px;padding:2px 7px;border:1px solid #ccc;border-radius:10px;background:#fff;cursor:pointer}
 .takechip.on{background:#1a5fb4;color:#fff;border-color:#1a5fb4}
 .generr{color:#d1242f;background:#ffefef;border:1px solid #ffc9c9;border-radius:6px;
   padding:4px 8px;font-size:12px;margin:4px 0;word-break:break-all}
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
 .dbox{display:flex;padding:0;width:min(1500px,96vw);height:92vh;overflow:hidden}
 .dleft{flex:1;background:#14161a;display:flex;flex-direction:column;align-items:center;justify-content:center;min-width:0}
 .dleft img{max-width:96%;max-height:calc(100% - 52px);object-fit:contain;cursor:zoom-in;background:#fff}
 .dtabs{height:46px;display:flex;gap:6px;align-items:center}
 .dright{width:400px;background:#fff;padding:12px 14px;overflow-y:auto;display:flex;flex-direction:column;gap:4px}
 .dright h4{margin:8px 0 2px;font-size:12px;color:#57606a}
 .dscene{background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:8px;font-size:13px;white-space:pre-wrap}
 .dscene.lowconf{background:#fff5f5;border-color:#ffb3b3;color:#c1121f}
 .djp{background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:8px;font-size:12px;
   white-space:pre-wrap;max-height:220px;overflow:auto}
 .dkv{font-size:12px;border-collapse:collapse} .dkv td{padding:2px 6px;vertical-align:top}
 .dkv td:first-child{color:#57606a;white-space:nowrap}
 #dEn{width:100%;min-height:150px} #dStage{width:100%;min-height:84px}
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
   <label><input type="checkbox" id="fQC"> QC要確認のみ</label>
   <span class="grow"></span>
   <span class="summary" id="summary"></span>
   <button class="primary" onclick="genBatch('ungenerated')" title="この話数の未生成カットをまとめてキュー投入">未生成を一括生成</button>
   <button onclick="genBatch('failed')" title="失敗したカットだけ再実行">失敗のみ再実行</button>
   <button onclick="rescan()" title="原図フォルダを再走査（後から届いた原図を取り込む）">フォルダ再取得</button><button onclick="refresh()">更新</button>
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
    <label><input type="radio" name="gsrc" value="base" onchange="onGsrc()"> 自動検出(Base)</label>
    <label><input type="radio" name="gsrc" value="visible" onchange="onGsrc()"> 見たまま(visible)</label>
    <label><input type="radio" name="gsrc" value="override" onchange="onGsrc()"> レイヤー選択</label>
    <button class="primary" onclick="recapture()">この設定で取得しなおす</button>
    <span id="gMsg" class="muted"></span></div>
  <div id="gLayers" style="display:none;max-height:200px;overflow:auto;border:1px solid #eee;padding:6px;margin-top:6px;font-size:12px"></div>
  <div class="muted">PhotoshopでPSDを直して保存→「取得しなおす」。Base=背景レイヤー自動検出／visible=表示中の全レイヤー／レイヤー選択=チェックしたレイヤーだけを原図にする（025/052 の誤検出対策）。</div>
</div></div>

<div class="ov" id="dmodal" onclick="if(event.target===this)this.style.display='none'"><div class="box dbox">
  <div class="dleft"><img id="dImg" onclick="lb(this.src)">
    <div class="dtabs">
      <button id="dbG" onclick="dShow('genzu')">原図</button>
      <button id="dbR" onclick="dShow('result')">生成結果</button>
      <button id="dbB" onclick="dShow('board')">ボード</button>
      <button onclick="openCmp(DCUR)">前後比較</button></div></div>
  <div class="dright">
    <div class="bar"><b id="dTitle"></b><span class="grow"></span>
      <button onclick="document.getElementById('dmodal').style.display='none'">閉じる</button></div>
    <div id="dBadges"></div>
    <h4>画角・場面の記述（生成の核・日本語OK・最優先で効く）</h4>
    <textarea id="dStage" placeholder="例: カメラはモニター側にあり、ブラインドのある窓側へ向かって撮影。壁面とブラインドのみが写る。キャラクターや枠線は描かない。"></textarea>
    <div class="bar"><button onclick="dSaveStage()">記述を保存</button><span id="dStageHint" class="muted"></span></div>
    <h4>コンテ情報（自動・記述の下書きに使う）</h4><div id="dScene" class="dscene"></div>
    <h4>詳細</h4><table class="dkv" id="dKv"></table>
    <h4>プロンプト（日本語・確認用）</h4><div id="dJp" class="djp"></div>
    <details><summary>英語プロンプト（生成に使われる・編集可）</summary>
      <textarea id="dEn"></textarea>
      <div class="bar"><button onclick="dSavePrompt()">保存</button>
        <button onclick="dResetPrompt()">自動に戻す</button></div></details>
    <h4>リテイク指示（最優先の修正指示としてプロンプト末尾に付く）</h4>
    <input id="dNote" placeholder="例: 壁面とブラインドのみ。机・扉・部屋の奥行きは描かない">
    <div class="bar"><button class="primary" onclick="dGenerate()">生成</button>
      <button class="ok" onclick="accept(DCUR,'accepted')">OK</button>
      <button class="ng" onclick="accept(DCUR,'reject')">要修正</button></div>
    <div id="dMsg" class="muted"></div>
  </div></div></div>
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
let POLL=null,BATCH='';
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
  const T=Date.now();
  const mb=top.map(b=>{
    const u='/board-img?key='+encodeURIComponent(cur.key)+'&name='+encodeURIComponent(b.board)+'&t='+T;
    const cap=esc(b.board)+' ×'+b.cuts;
    return `<figure>${b.has_img?`<img loading="lazy" src="${u}" onclick="lb('${u}')">`:`<div class="noimg">${esc(b.board)}</div>`}<figcaption>${cap}</figcaption></figure>`;
  }).join('');
  const nimg=(o.boards||[]).filter(b=>b.has_img).length;
  const diag=(o.board_count>0)
    ? `<span class="muted">索引 ${o.board_count}枚 ・ 画像一致 ${nimg}/${(o.boards||[]).length} ・ ${esc(o.boards_dir)}</span>`
    : `<span style="color:#d1242f">⚠ ボードフォルダを読めていません（${o.boards_dir?esc(o.boards_dir):'--boards-dir 未指定'}）。run_console.bat の BOARDS を確認</span>`;
  box.innerHTML=`<details class="ovbox" open><summary>話数概要 — ${esc(cur.group)}</summary>
    ${o.synopsis?`<p class="synopsis">${esc(o.synopsis)}</p>`:'<p class="synopsis muted">（あらすじ未登録）</p>'}
    ${scenes?`<div class="scenes">${scenes}</div>`:''}
    <div class="mbtitle">主要シーンの美術ボード（登場カット数が多い順）　${diag}</div>
    ${mb?`<div class="mboards">${mb}</div>`:'<div class="muted">ボード未割当 / 画像なし</div>'}
    ${o.note?`<div class="note">${esc(o.note)}</div>`:''}</details>`;
}
function render(){
  const fa=$('#fAssignee').value,fs=$('#fStatus').value,fr=$('#fResult').checked,fq=$('#fQC').checked;
  const all=UNITS.filter(u=>u.group===GROUP);
  const us=all.filter(u=>(!fa||u.assignee===fa)&&(!fs||u.status===fs)&&(!fr||!u.has_result)
    &&(!fq||['needs_retake','human'].includes(u.qc_verdict)));
  const gen=all.filter(u=>u.has_result).length, ok=all.filter(u=>u.status==='accepted').length, ng=all.filter(u=>u.status==='reject').length;
  const pct=all.length?Math.round(ok/all.length*100):0;
  const running=[...RUN].map(unit).filter(u=>u&&u.group===GROUP);
  $('#summary').innerHTML=(BATCH?`<span class="pill run">⏳ ${BATCH}</span>`:(running.length?`<span class="pill run">⏳生成中 ${running.length}: c${running.map(u=>u.cuts.join(',')).join(' / c')}</span>`:''))
    +`<span class="pill">全${all.length}</span><span class="pill">生成済 ${gen}</span>`
    +`<span class="pill ok">OK ${ok}</span><span class="pill ng">要修正 ${ng}</span><span class="pill">未生成 ${all.length-gen}</span>`
    +`<div class="pbar"><i style="width:${pct}%"></i></div><span class="muted">${pct}% OK</span>`;
  // 再描画で編集中の状態（開いたタブ・入力途中のテキスト・フォーカス）を失わないよう退避→復元。
  // 生成ポーリングの度に render() が走るため、これが無いと編集がステータス更新で吹き飛ぶ。
  const focusId=document.activeElement&&document.activeElement.id;
  const keepVals={};
  document.querySelectorAll('#grid textarea, #grid input[type=text], #grid input:not([type])').forEach(el=>{if(el.id)keepVals[el.id]=el.value;});
  const openCards=[...document.querySelectorAll('#grid details[open]')].map(dt=>dt.closest('[id^=card_]')&&dt.closest('[id^=card_]').id).filter(Boolean);
  $('#grid').innerHTML=us.map(card).join('');
  openCards.forEach(cid=>{const el=document.getElementById(cid); const dt=el&&el.querySelector('details'); if(dt)dt.open=true;});
  Object.entries(keepVals).forEach(([id,v])=>{const el=document.getElementById(id); if(el&&v&&el.value!==v)el.value=v;});
  if(focusId){const el=document.getElementById(focusId); if(el){el.focus(); try{el.setSelectionRange(el.value.length,el.value.length);}catch(e){}}}
  us.forEach(u=>{if(RUN.has(u.id))markRunning(u.id,true);});
}
function qcBadge(u){
  if(!u.qc_verdict||u.qc_verdict==='unknown') return '';
  const map={pass:['QC✓','#dff3e6','#0a5'],needs_retake:['QC⚠','#fde2e2','#d1242f'],
             human:['QC要確認','#fff3d6','#a36a00']};
  const m=map[u.qc_verdict]; if(!m) return '';
  const tip=(u.qc_reasons||[]).join(' / ');
  return `<span class="b" style="background:${m[1]};color:${m[2]}" title="${esc(tip)}">${m[0]}</span>`;
}
function takeStrip(u){
  const tk=u.takes||[]; if(tk.length<2) return '';   // 2テイク以上で履歴を出す
  const chips=tk.map(t=>{
    const on=(t.n===u.adopted);
    const qc=t.qc==='needs_retake'||t.qc==='human'?' ⚠':(t.qc==='pass'?' ✓':'');
    const tip=`テイク${t.n}${qc}を採用`+(t.note?`\n指示: ${t.note}`:'');
    return `<button class="takechip${on?' on':''}" title="${esc(tip)}" onclick="adoptTake('${u.id}',${t.n})">T${t.n}${on?'●':''}${qc}${t.note?'📝':''}</button>`;
  }).join('');
  return `<div class="takes">テイク履歴: ${chips}<span class="muted">（クリックで採用＝現行結果に戻す）</span></div>`;
}
async function adoptTake(id,n){
  const u=unit(id); if(u&&u.adopted===n) return;
  const r=await post('/api/unit/'+id+'/adopt',{take:n});
  if(r.error){alert(r.error);return;}
  await refresh();
}
function card(u){
  const t=Date.now();
  const opts='<option value="">— ボード未選択 —</option>'+BOARDS.map(b=>`<option ${b===u.board?'selected':''}>${esc(b)}</option>`).join('');
  return `<div class="card ${u.status} ${RUN.has(u.id)?'running':''}" id="card_${u.id}">
   <div class="chead"><span class="cut" style="cursor:pointer" title="クリックで詳細画面" onclick="openDetail('${u.id}')">c${u.cuts.join(',')}</span>
     <span class="who ${u.assignee==='GKV'?'gkv':'other'}">${u.assignee}</span>
     <span class="b ${u.status}">${u.status}</span>${u.retakes?`<span class="muted">RT${u.retakes}</span>`:''}
     ${qcBadge(u)}
     ${u.has_psd?'':'<span class="muted">PSD無</span>'}<span class="scene">${esc(u.scene)}</span></div>
   <div class="thumbs">
     <figure><figcaption>原図[${u.genzu_source}] ${u.has_psd?`<a href="#" onclick="openPsd('${u.id}');return false">PSDを開く</a> · <a href="#" onclick="openGenzu('${u.id}');return false">拡大/取り直し</a>`:''}</figcaption>
       ${u.has_psd?`<img loading="lazy" src="/img/${u.id}/genzu?v=${u.genzu_source}${u.genzu_rev||0}" onclick="openGenzu('${u.id}')" onerror="this.outerHTML='<div class=ph>原図なし</div>'">`:'<div class="ph">PSD未検出</div>'}</figure>
     <figure><figcaption>生成結果 ${u.has_result?`<a href="#" onclick="openCmp('${u.id}');return false">前後比較</a>`:''}</figcaption>${u.has_result?`<img loading="lazy" src="/img/${u.id}/result?t=${t}" onclick="openCmp('${u.id}')">`:'<div class="ph">未生成</div>'}</figure>
   </div>
   ${takeStrip(u)}
   ${u.gen_error?`<div class="generr" title="${esc(u.gen_error)}">⚠ 生成失敗: ${esc(u.gen_error.slice(0,120))}</div>`:''}
   <div class="prog ${RUN.has(u.id)?'on':''}" id="prog_${u.id}"><i></i></div>
   <div class="bar"><select style="flex:1;width:auto" onchange="setBoard('${u.id}',this.value)">${opts}</select>
     <button onclick="showBoard('${u.id}')" onmousemove="boardHover('${u.id}',event)" onmouseleave="boardOut()" title="クリックで拡大／ホバーでプレビュー">ボード表示</button></div>
   <details><summary>プロンプト${u.prompt_edited?'（編集済）':''}</summary>
     <textarea id="pr_${u.id}" placeholder="（自動生成。編集して保存で上書き）"></textarea>
     <div class="bar"><button onclick="savePrompt('${u.id}')">保存</button>
       <button onclick="loadPrompt('${u.id}')">自動表示</button>
       <button onclick="resetPrompt('${u.id}')">自動に戻す</button></div></details>
   ${u.has_result?`<input class="rnote" id="rn_${u.id}" value="${esc(u.retake_note||'')}"
     placeholder="リテイク指示（例: 右の木の幹をつなげる / 奥行きを出す）"
     onchange="saveNote('${u.id}')">`:''}
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
  $('#gLayers').style.display='none'; $('#gLayers').innerHTML='';
  $('#gMsg').textContent=''; $('#gmodal').style.display='flex';
  if(u.genzu_source==='override') onGsrc();}
async function onGsrc(){
  const src=document.querySelector('input[name=gsrc]:checked').value;
  const box=$('#gLayers');
  if(src!=='override'){box.style.display='none';return;}
  box.style.display='block'; box.innerHTML='レイヤー取得中…';
  const d=await (await fetch('/api/unit/'+GCUR+'/layers')).json();
  if(d.error){box.textContent='エラー: '+d.error;return;}
  const sel=new Set(d.selected||[]);
  box.innerHTML=d.layers.map(l=>`<label style="display:block;padding-left:${l.depth*14}px">`+
    `<input type="checkbox" class="lyr" value="${esc(l.name)}" ${sel.has(l.name)?'checked':''}> `+
    `${esc(l.name)} <span class="muted">[${esc(l.kind)}]${l.visible?'':' (非表示)'}</span></label>`).join('');
}
async function recapture(){const src=document.querySelector('input[name=gsrc]:checked').value; $('#gMsg').textContent='取得中…';
  const body={source:src};
  if(src==='override'){body.layers=[...document.querySelectorAll('#gLayers .lyr:checked')].map(c=>c.value);
    if(!body.layers.length){$('#gMsg').textContent='レイヤーを1つ以上選んでください';return;}}
  const r=await post('/api/unit/'+GCUR+'/recapture',body); if(r.error){$('#gMsg').textContent='エラー: '+r.error;return;}
  $('#gImg').src='/img/'+GCUR+'/genzu?t='+Date.now(); $('#gMsg').textContent='取得しました（'+src+'）'; await refresh();}
async function openPsd(id){const r=await post('/api/unit/'+id+'/open',{}); slog(id,r.error?('開けません: '+r.error):'PSDを開きました');}
async function loadPrompt(id){const d=await (await fetch('/api/unit/'+id)).json(); const t=document.getElementById('pr_'+id); if(t)t.value=d.prompt;}
let DCUR=null;
async function openDetail(id){DCUR=id; const u=unit(id); if(!u)return;
  $('#dTitle').textContent='c'+u.cuts.join(',')+'（'+u.assignee+'）';
  $('#dBadges').innerHTML=`<span class="b ${u.status}">${u.status}</span> ${qcBadge(u)}${u.retakes?` <span class="muted">RT${u.retakes}</span>`:''}`;
  $('#dScene').textContent='読み込み中…'; $('#dJp').textContent='…'; $('#dEn').value=''; $('#dMsg').textContent='';
  $('#dmodal').style.display='flex'; dShow(u.has_result?'result':'genzu');
  const d=await (await fetch('/api/unit/'+id)).json();
  const ci=d.cut_info||{};
  const low=(ci.conf==='low')||!ci.place;
  const sc=$('#dScene'); sc.classList.toggle('lowconf',low);
  sc.textContent=ci.place
    ?('場所: '+ci.place+'\n時刻: '+(ci.time||'—')+(ci.situation?('\n状況: '+ci.situation):'')
      +(low?'\n⚠ コンテOCRの信頼度が低い/場面説明なし。内容を確認してください':''))
    :'場面情報なし（コンテ未紐づけ）。⚠ 画角・場所はリテイク指示かプロンプトで手動指定してください';
  $('#dJp').textContent=d.prompt_jp||'（日本語プロンプトなし）';
  $('#dEn').value=d.prompt||'';
  $('#dNote').value=u.retake_note||'';
  $('#dStage').value=d.staging||'';
  $('#dStageHint').textContent=d.staging_source==='auto'
    ?('自動下書き'+(d.staging_conf?('（信頼度 '+d.staging_conf+'）'):'')+' — 直して保存で確定')
    :(d.staging_source==='manual'?'手動確定済み':'未記入（コンテ情報を下書きに書いてください）');
  $('#dStageHint').style.color=(d.staging_conf==='low'||!d.staging)?'#c1121f':'';
  $('#dKv').innerHTML=[['ファイル',d.filename],['原図ソース',u.genzu_source],
    ['ボード',u.board||'—'],['テイク',(u.takes||[]).length+(u.adopted?('（採用 T'+u.adopted+'）'):'')],
    ['OCR信頼度',ci.conf||'—'],['QC',(u.qc_reasons||[]).join(' / ')||'—']]
    .map(([k,v])=>`<tr><td>${k}</td><td>${esc(String(v))}</td></tr>`).join('');
}
function dShow(which){const u=unit(DCUR); if(!u)return; const t=Date.now();
  const srcs={genzu:`/img/${DCUR}/genzu?v=${u.genzu_source}${u.genzu_rev||0}`,
              result:`/img/${DCUR}/result?t=${t}`, board:`/img/${DCUR}/board?t=${t}`};
  const im=$('#dImg'); im.onerror=()=>{im.onerror=null;$('#dMsg').textContent='画像がありません（'+which+'）';};
  $('#dMsg').textContent=''; im.src=srcs[which];
  const ids={genzu:'dbG',result:'dbR',board:'dbB'};
  Object.values(ids).forEach(b=>$('#'+b).classList.remove('primary'));
  if(ids[which])$('#'+ids[which]).classList.add('primary');
}
async function dSaveStage(){await post('/api/unit/'+DCUR+'/staging',{text:$('#dStage').value});
  const d=await (await fetch('/api/unit/'+DCUR)).json(); $('#dJp').textContent=d.prompt_jp||''; $('#dEn').value=d.prompt||'';
  $('#dMsg').textContent='画角・場面の記述を保存しました（プロンプトに反映済み）';}
async function dSavePrompt(){await post('/api/unit/'+DCUR+'/prompt',{prompt:$('#dEn').value}); $('#dMsg').textContent='プロンプトを保存しました';}
async function dResetPrompt(){await post('/api/unit/'+DCUR+'/prompt',{prompt:''});
  const d=await (await fetch('/api/unit/'+DCUR)).json(); $('#dEn').value=d.prompt||''; $('#dMsg').textContent='自動生成に戻しました';}
async function dGenerate(){
  await post('/api/unit/'+DCUR+'/staging',{text:$('#dStage').value});
  await post('/api/unit/'+DCUR+'/retake_note',{note:$('#dNote').value});
  const r=await post('/api/unit/'+DCUR+'/generate',{}); if(r.error){$('#dMsg').textContent='エラー: '+r.error;return;}
  RUN.add(DCUR); const u=unit(DCUR); if(u){u.status='generating';u.running=true;} render(); pollJobs();
  $('#dMsg').textContent='生成キューに投入しました（完了後「生成結果」タブで確認）';}
async function savePrompt(id){const t=document.getElementById('pr_'+id); await post('/api/unit/'+id+'/prompt',{prompt:t?t.value:''}); slog(id,'保存しました');}
async function resetPrompt(id){await post('/api/unit/'+id+'/prompt',{prompt:''}); const t=document.getElementById('pr_'+id); if(t)t.value=''; slog(id,'自動に戻しました');}
async function setBoard(id,v){await post('/api/unit/'+id+'/board',{board:v}); slog(id,'ボード保存');}
async function accept(id,v){await post('/api/unit/'+id+'/accept',{value:v}); const u=unit(id); if(u)u.status=v; render();}
function slog(id,m){const l=document.getElementById('log_'+id); if(l){l.style.display='block';l.textContent=m;}}
async function saveNote(id){const e=document.getElementById('rn_'+id);
  await post('/api/unit/'+id+'/retake_note',{note:e?e.value:''}); const u=unit(id); if(u)u.retake_note=e?e.value:'';}
async function gen(id){
  const t=document.getElementById('pr_'+id); if(t&&t.value.trim()) await post('/api/unit/'+id+'/prompt',{prompt:t.value});
  const rn=document.getElementById('rn_'+id); if(rn) await post('/api/unit/'+id+'/retake_note',{note:rn.value});
  const r=await post('/api/unit/'+id+'/generate',{}); if(r.error){slog(id,'エラー: '+r.error);return;}
  RUN.add(id); markRunning(id,true); const u=unit(id); if(u){u.status='generating';u.running=true;} render(); slog(id,'キュー投入…');
  pollJobs();
}
async function genBatch(scope){
  const label=scope==='failed'?'失敗したカットを再実行':'未生成のカットを一括生成';
  if(!confirm(label+'しますか？（同時実行 上限内でキュー処理）')) return;
  const r=await post('/api/generate_batch',{group:GROUP,scope:scope});
  const sk=r.skip_reasons||{};
  const skmsg=Object.keys(sk).length?(' / スキップ '+Object.entries(sk).map(([k,v])=>k+':'+v).join(',')):'';
  alert('キュー投入 '+(r.queued||0)+'件'+skmsg);
  await refresh(); pollJobs();
}
// 生成ジョブ全体を1本のタイマーで監視（多数カードでもポーラは1つ）
function pollJobs(){
  if(POLL) return;
  POLL=setInterval(async()=>{
    let j; try{j=await (await fetch('/api/jobs')).json();}catch(e){return;}
    const active=j.active||{};
    RUN.clear(); Object.keys(active).forEach(id=>RUN.add(id));
    UNITS.forEach(u=>{ if(active[u.id]) u.status='generating'; });
    BATCH=`待ち/生成中 ${j.busy||0}`+((j.qsize||0)?`（残 ${j.qsize}）`:'');
    render();
    if((j.busy||0)===0){ clearInterval(POLL); POLL=null; BATCH=''; await refresh(); }
  },2500);
}
async function rescan(){const p=PROJECTS.find(x=>x.group===GROUP); if(!p)return; await post('/api/projects/'+encodeURIComponent(p.key)+'/rescan',{}); await refresh();}
function openAdd(work){$('#mWork').value=work||''; $('#mEp').value=''; $('#mGenzu').value=''; $('#mBoards').value='';
  $('#mTitle').textContent=work?(work+' に話数を追加'):'作品・話数を追加'; $('#mMsg').textContent=''; $('#modal').style.display='flex';}
async function addProject(){$('#mMsg').textContent='追加中…';
  const r=await post('/api/projects',{work:$('#mWork').value,ep:$('#mEp').value,genzu_dir:$('#mGenzu').value,boards_dir:$('#mBoards').value});
  if(r.error){$('#mMsg').textContent='エラー: '+r.error;return;}
  $('#modal').style.display='none'; WORK=$('#mWork').value||WORK; GROUP=null; await refresh();}
$('#fAssignee').onchange=render;$('#fStatus').onchange=render;$('#fResult').onchange=render;$('#fQC').onchange=render;
$('#cmpSlider').addEventListener('pointermove',cmpMove);
document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('#cmp').style.display='none';$('#lb').style.display='none';$('#gmodal').style.display='none';}});
refresh();
</script></body></html>"""


def main(argv=None):
    p = argparse.ArgumentParser(prog="genzu_fix.server", description="原図修正コンソール")
    p.add_argument("--project", default=None,
                   help="discover_assets が作る project json。genzu_dir/boards_dir/out/work/ep を補完")
    p.add_argument("--projects-glob", default="runs/project_*.json",
                   help="起動時に読み込む作品レジストリ（全作品がタブに載る）")
    p.add_argument("--genzu-dir", default=None)
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
    p.add_argument("--max-parallel", type=int, default=3, help="生成の同時実行数の上限")
    p.add_argument("--qc-vision", action="store_true",
                   help="生成後にAI視覚QC（人物残り/文字残り/画角）も走らせる（要 ANTHROPIC_API_KEY）")
    p.add_argument("--port", type=int, default=8765)
    a = p.parse_args(argv)
    # --project（discover_assets 出力）で未指定の genzu_dir/boards_dir/out/work/ep を補完。
    if a.project:
        pj = _load_json(a.project, {})
        a.genzu_dir = a.genzu_dir or pj.get("genzu_dir")
        a.boards_dir = a.boards_dir or pj.get("boards_dir")
        if a.out == "work/console" and pj.get("out_dir"):
            a.out = pj["out_dir"]
        if pj.get("work"):
            a.work = pj["work"]
        if pj.get("ep"):
            a.ep = pj["ep"]
        # カット表は project 側を正とする。project に csv が無い作品（SP2等・香盤表なし）は
        # --csv の既定値(ep7)を引きずらず、原図フォルダ走査で組む。
        if a.csv == "runs/cut_board_map_ep7.csv":
            a.csv = pj.get("csv")
        # 話数概要・cut_info も既定(尚善ep7)のままなら project 側を正とする
        if a.overview_json == "runs/ep_overview.json" and pj.get("overview"):
            a.overview_json = pj["overview"]
        if a.cut_info == "runs/cut_scene_info_ep7.csv":
            a.cut_info = pj.get("cut_info") or ""
    # カット別 situation/remove（great-edisonの3層プロンプトCUT層）。在ればプロンプトに反映。
    cut_info_map = {}
    try:
        cut_info_map = batch.promptlib.load_cut_info(a.cut_info)
    except Exception:
        pass
    CFG.update(dict(out=a.out, csv=a.csv, boards_json=a.boards_json,
                    resolution=a.resolution, quality=a.quality, model=a.model,
                    image_flag=a.image_flag, include_book=a.include_book,
                    header_top=a.header_top, cut_info_map=cut_info_map,
                    max_parallel=a.max_parallel, qc_vision=a.qc_vision))
    OVERVIEWS.update(_load_json(a.overview_json, {}))
    global STATE
    STATE = _load_json(_state_path(), {})

    def add_project(work, ep, genzu_dir, boards_dir, csv_path, out_dir, cut_info, label,
                    board_map=None, include_book=None, staging_map=None, genzu_trust=None):
        """genzu_dir が実在すれば PROJECTS に登録。csv が実在すれば csv、無ければ scan。"""
        if not (genzu_dir and os.path.isdir(genzu_dir)):
            print(f"[skip] {label}: 原図フォルダが見つかりません: {genzu_dir}")
            return None
        key = f"{work}#{ep}"
        source = "csv" if (csv_path and os.path.exists(csv_path)) else "scan"
        if source == "scan":
            print(f"[info] {label}: カット表CSVなし→原図フォルダ走査で構成: {genzu_dir}")
        PROJECTS[key] = _make_project(key, work, ep, genzu_dir, boards_dir,
                                      csv_path if source == "csv" else None,
                                      source=source, out_dir=out_dir, cut_info=cut_info,
                                      board_map=board_map, include_book=include_book,
                                      staging_map=staging_map, genzu_trust=genzu_trust)
        # 各作品の過去state(OK判定/プロンプト編集等)を取り込む。
        # その作品のユニットに属する uid だけ・既存キーは上書きしない（他作品の混入や汚染を防ぐ）。
        if out_dir:
            units = PROJECTS[key]["units"]
            for k, v in _load_json(os.path.join(out_dir, "console_state.json"), {}).items():
                if k in units:
                    STATE.setdefault(k, v)
        return key

    # 1) 作品レジストリ（runs/project_*.json）を全部読み込む → 全作品がタブに載る
    import glob as _glob
    for pjpath in sorted(_glob.glob(a.projects_glob)):
        pj = _load_json(pjpath, {})
        if not pj.get("work"):
            continue
        add_project(pj["work"], str(pj.get("ep", "00")), pj.get("genzu_dir"),
                    pj.get("boards_dir"), pj.get("csv"), pj.get("out_dir"),
                    pj.get("cut_info"), os.path.basename(pjpath),
                    board_map=pj.get("board_map"), include_book=pj.get("include_book"),
                    staging_map=pj.get("staging_map"), genzu_trust=pj.get("genzu_trust"))
    # 2) CLI 指定があれば従来どおり追加/上書き（後方互換）
    if a.genzu_dir:
        add_project(a.work, a.ep, a.genzu_dir, a.boards_dir, a.csv, a.out, a.cut_info, "CLI引数")
    # 3) 永続化された追加プロジェクト（＋作品ボタン由来）を復元
    for rec in _load_json(_projects_path(), []):
        if rec["key"] not in PROJECTS and os.path.isdir(rec.get("genzu_dir", "")):
            PROJECTS[rec["key"]] = _make_project(rec["key"], rec["work"], rec["ep"],
                                                 rec["genzu_dir"], rec.get("boards_dir"),
                                                 rec.get("csv"), rec.get("source", "scan"))
    if not PROJECTS:
        p.error("作品が1つも見つかりません（runs/project_*.json を作るか --genzu-dir を指定）")
    _save_projects()
    app = create_app()
    print(f"原図修正コンソール: http://127.0.0.1:{a.port}  (out={a.out})")
    app.run(host="127.0.0.1", port=a.port, threaded=True)


if __name__ == "__main__":
    main()
