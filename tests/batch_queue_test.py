"""一括生成キュー（S1）＋冪等/失敗復帰（S2）の動作テスト。Higgsfield 不要。

空PSD（生成が必ず失敗する）とダミー結果を置き、/api/generate_batch の
- queued / skip(done,no_psd) の集計
- 生成失敗後に status が「生成中」で固まらず元へ戻る
を検証する。実行: PYTHONPATH=src python tests/batch_queue_test.py
"""
from __future__ import annotations
import csv
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request


def _post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=8).read())


def _get(base, path):
    return json.loads(urllib.request.urlopen(base + path, timeout=8).read())


def main():
    root = tempfile.mkdtemp(prefix="batch_queue_")
    out, gz = os.path.join(root, "out"), os.path.join(root, "genzu")
    os.makedirs(out, exist_ok=True)
    os.makedirs(gz, exist_ok=True)
    for n in ("shz_07_047_genzu.psd", "shz_07_050_genzu.psd"):
        open(os.path.join(gz, n), "wb").close()          # 空PSD=has_psd True（生成は失敗する）
    os.makedirs(os.path.join(out, "shz_07_050_genzu"), exist_ok=True)
    open(os.path.join(out, "shz_07_050_genzu", "restored_full.png"), "wb").close()  # 既生成
    csvp = os.path.join(root, "cuts.csv")
    with open(csvp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cut", "assignee", "scene", "filename", "board"])
        w.writerow(["47", "GKV", "c047", "shz_07_047_genzu.psd", ""])   # 未生成→queue
        w.writerow(["50", "GKV", "c050", "shz_07_050_genzu.psd", ""])   # 既生成→skip done
        w.writerow(["99", "GKV", "c099", "shz_07_099_genzu.psd", ""])   # PSD無し→skip no_psd

    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    proc = subprocess.Popen(
        [sys.executable, "-m", "genzu_fix.server", "--genzu-dir", gz, "--csv", csvp,
         "--out", out, "--work", "尚善", "--ep", "07", "--max-parallel", "2", "--port", str(port)],
        env=dict(os.environ, PYTHONPATH="src"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    fails = []
    try:
        for _ in range(20):
            try:
                _get(base, "/api/units"); break
            except Exception:
                time.sleep(1)
        r = _post(base, "/api/generate_batch", {"group": "尚善 #07", "scope": "ungenerated"})
        print("batch:", r)
        if r.get("queued") != 1:
            fails.append(f"queued!=1: {r}")
        if r.get("skip_reasons", {}).get("done") != 1 or r.get("skip_reasons", {}).get("no_psd") != 1:
            fails.append(f"skip_reasons不一致: {r}")
        for _ in range(30):
            if _get(base, "/api/jobs")["busy"] == 0:
                break
            time.sleep(1)
        units = {u["id"]: u for u in _get(base, "/api/units")}
        st = units["shz_07_047_genzu"]["status"]
        print("cut47 status:", st, "running:", units["shz_07_047_genzu"]["running"])
        if st == "generating":
            fails.append("失敗後も『生成中』で固まっている")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    if fails:
        print("FAIL:", fails)
        return 1
    print("ALL PASS: queue投入 / 冪等skip(done,no_psd) / 失敗時の状態復帰")
    return 0


if __name__ == "__main__":
    sys.exit(main())
