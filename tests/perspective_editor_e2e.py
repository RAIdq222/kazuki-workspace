"""パース編集エディタ(genzu_fix.perspective_editor)のブラウザ動作テスト。

合成PNGを開き、UI操作（自動推定[cv]・消失点追加・人物追加・保存）が動くことを
Playwright で検証する。playwright/chromium 未導入なら SKIP（終了コード0）。

実行: PYTHONPATH=src python tests/perspective_editor_e2e.py
"""
from __future__ import annotations
import os
import sys
import math
import time
import json
import socket
import subprocess
import tempfile

CHROMIUM = "/opt/pw-browsers/chromium"


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


def _wait_http(url, timeout=20):
    import urllib.request
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=1); return True
        except Exception:
            time.sleep(0.3)
    return False


def _make_image(path):
    from PIL import Image, ImageDraw
    W, H = 1200, 800
    im = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(im)
    vp = (700, 360)
    for y in (0, 150, 650, 800):
        d.line([(0, y), vp], fill=(0, 0, 0), width=2)
        d.line([(W, y), vp], fill=(0, 0, 0), width=2)
    for x in (300, 520, 900):
        d.line([(x, 0), (x, H)], fill=(0, 0, 0), width=3)
    im.save(path)


def main():
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print("SKIP: playwright未導入:", e); return 0
    try:
        import flask  # noqa
    except Exception as e:
        print("SKIP: flask未導入:", e); return 0
    if not os.path.exists(CHROMIUM):
        print("SKIP: chromium未検出:", CHROMIUM); return 0

    root = tempfile.mkdtemp(prefix="persp_editor_e2e_")
    img = os.path.join(root, "cut.png")
    _make_image(img)
    port = _free_port()
    env = dict(os.environ, PYTHONPATH="src")
    proc = subprocess.Popen(
        [sys.executable, "-m", "genzu_fix.perspective_editor", "--port", str(port)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    failures = []

    def check(name, cond):
        print(("ok  " if cond else "FAIL") + " " + name)
        if not cond:
            failures.append(name)

    try:
        if not _wait_http(base + "/api/config"):
            print("FAIL: サーバ起動せず")
            print((proc.stdout.read() or b"").decode()[-2000:]); return 1
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1400, "height": 950})
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(base, wait_until="networkidle")

            # 画像を開く（パスを貼って Enter。#open はネイティブダイアログ起動なのでテストでは使わない）
            page.fill("#path", img)
            page.press("#path", "Enter")
            page.wait_for_function(
                "() => document.getElementById('info').textContent.includes('1200')",
                timeout=8000)
            check("画像読込(寸法表示)", "1200" in page.text_content("#info"))

            # アップロード(ドラッグ&ドロップ相当)エンドポイント
            up = page.request.post(base + "/api/upload", multipart={
                "file": {"name": "up.png", "mimeType": "image/png",
                         "buffer": open(img, "rb").read()}})
            uj = up.json()
            check("/api/upload ok", up.ok and uj.get("width") == 1200)
            check("uploadはwork/_uploadsに保存", "work" in (uj.get("path", "")))

            # 自動推定(cv) → 消失点が1つ以上入る
            page.select_option("#method", "cv")
            page.click("#auto")
            page.wait_for_function("() => window.S && window.S.vps.length >= 1", timeout=8000)
            n_vp = page.evaluate("() => window.S.vps.length")
            n_char0 = page.evaluate("() => window.S.chars.length")  # cvは強い縦線をcharsに入れる
            check("cv自動推定で消失点", n_vp >= 1)
            check("cv自動推定でアイレベル", page.evaluate(
                "() => Math.abs(window.S.horizon.ya - window.S.horizon.yb) < 0.02"))  # ほぼ水平

            # 消失点を手動追加（水平＋鉛直）
            page.click("#addvp"); page.click("#addvpv")
            check("消失点追加", page.evaluate("() => window.S.vps.length") == n_vp + 2)
            check("鉛直消失点フラグ", page.evaluate(
                "() => window.S.vps.some(v=>v.vertical===true)"))

            # スナップON時、水平消失点は地平線上に乗る
            check("水平VPが地平線上", page.evaluate(
                "() => {const v=window.S.vps.find(v=>!v.vertical);"
                "return Math.abs(v.y-(window.S.horizon.ya+(window.S.horizon.yb-window.S.horizon.ya)*v.x))<1e-6;}"))

            # 人物垂直線を追加
            page.click("#addchar")
            check("人物追加", page.evaluate("() => window.S.chars.length") == n_char0 + 1)

            # 密度スライダ反映
            page.eval_on_selector("#density", "el=>{el.value=30;el.dispatchEvent(new Event('input'))}")
            check("ガイド密度反映", page.evaluate("() => window.S.density") == 30)

            # アイレベルを掴んで画像の外へドラッグ → 傾く（消失点も連動）
            page.evaluate("() => { window.S.horizon={ya:0.5,yb:0.5}; "
                          "window.S.vps.forEach(v=>{if(!v.vertical)v.y=0.5;}); draw(); }")
            geo = page.evaluate("""() => {
                const cvEl=document.getElementById('cv'); const b=cvEl.getBoundingClientRect();
                const nx=0.15, ny=window.horizonYat(nx); const p=window.n2s(nx,ny);
                const r=window.imgRect();
                return {gx:b.left+p[0], gy:b.top+p[1], outX:b.left+r.x1+90, outY:b.top+r.y1+140};
            }""")
            vp_before = page.evaluate("() => { const v=window.S.vps.find(v=>!v.vertical); return v?v.y:null; }")
            page.mouse.move(geo["gx"], geo["gy"])
            page.mouse.down()
            page.mouse.move(geo["gx"] + 20, geo["gy"] + 4)         # まず画像内で掴む
            page.mouse.move(geo["outX"], geo["outY"], steps=10)    # 画像外へ → 回転
            page.mouse.up()
            tilt = page.evaluate("() => Math.abs(window.S.horizon.ya - window.S.horizon.yb)")
            print(f"    傾き(|ya-yb|) = {tilt:.3f}")
            check("画面外ドラッグでアイレベルが傾く", tilt > 0.02)
            if vp_before is not None:
                vp_after = page.evaluate("() => { const v=window.S.vps.find(v=>!v.vertical); return v.y; }")
                check("消失点がアイレベルに連動", abs(vp_after - vp_before) > 0.01)

            # 保存 → JSON/PNG が出来る
            page.click("#save")
            page.wait_for_function(
                "() => document.getElementById('msg').textContent.includes('保存')",
                timeout=8000)
            stem = "cut"
            jp = os.path.join("work", "_perspective", stem, f"{stem}.edit.json")
            pp = os.path.join("work", "_perspective", stem, f"{stem}.edit.png")
            check("保存JSON存在", os.path.exists(jp))
            check("保存PNG存在", os.path.exists(pp))
            if os.path.exists(jp):
                obj = json.load(open(jp, encoding="utf-8"))
                check("JSONにvanishing_points", len(obj.get("vanishing_points", [])) == n_vp + 2)
                check("JSONにcharacters", len(obj.get("characters", [])) == n_char0 + 1)

            check("JSエラー無し", not errs)
            if errs:
                print("  pageerror:", errs[:3])
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    print()
    if failures:
        print("FAILED:", len(failures), failures); return 1
    print("ALL PASS"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
