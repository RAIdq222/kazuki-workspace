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

            # 画像を開く（ブラウザのファイル選択 <input type=file>。内部で /api/upload に送られる）
            page.set_input_files("#file", img)
            page.wait_for_function(
                "() => document.getElementById('info').textContent.includes('1200')",
                timeout=8000)
            check("画像読込(ファイル選択)", "1200" in page.text_content("#info"))
            check("uploadはwork/_uploadsに保存", "work" in page.evaluate("() => window.S.path"))

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
            # 線の太さスライダ反映
            page.eval_on_selector("#lw", "el=>{el.value=7;el.dispatchEvent(new Event('input'))}")
            check("線の太さ反映", page.evaluate("() => window.S.lw") == 7)

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

            # /api/render: フルレゾPNGを返す。ガイド密度がPNGに反映されるか回帰確認（4≠30）
            ann = page.evaluate("() => annotation()")
            r4 = page.request.post(base + "/api/render",
                data=json.dumps({"path": img, "annotation": ann, "line_scale": 1.0, "guides": 4}),
                headers={"content-type": "application/json"})
            r30 = page.request.post(base + "/api/render",
                data=json.dumps({"path": img, "annotation": ann, "line_scale": 1.0, "guides": 30}),
                headers={"content-type": "application/json"})
            check("render PNG返却", r4.ok and r4.headers.get("content-type", "").startswith("image/png")
                  and len(r4.body()) > 0)
            check("ガイド密度がPNGに反映(4≠30)", r4.body() != r30.body())

            # 保存: showSaveFilePicker は headless で出せないので無効化し、ダウンロード経路を検証。
            # PNGはブラウザ側でフル解像度生成（サーバ非依存）。0KBにならないことを担保する。
            page.evaluate("() => { window.showSaveFilePicker = undefined; }")
            with page.expect_download() as di:
                page.click("#savepng")
            png_path = di.value.path()
            check("PNG保存(ダウンロード)", di.value.suggested_filename.endswith(".perspective.png"))
            check("PNGが空でない(>0KB)", bool(png_path) and os.path.getsize(png_path) > 1000)
            # 透過PNG（線だけ）保存：中身があり、背景が透明であること
            with page.expect_download() as dt:
                page.click("#savepngtr")
            trp = dt.value.path()
            check("透過PNGファイル名", dt.value.suggested_filename.endswith(".perspective_lines.png"))
            check("透過PNGが空でない(>0)", bool(trp) and os.path.getsize(trp) > 200)
            if trp:
                from PIL import Image as _Im
                im = _Im.open(trp).convert("RGBA")
                check("透過PNGはRGBA", im.mode == "RGBA")
                # 四隅は完全透明（背景が描かれていない）
                corners = [im.getpixel((0, 0)), im.getpixel((im.width - 1, 0)),
                           im.getpixel((0, im.height - 1)), im.getpixel((im.width - 1, im.height - 1))]
                check("四隅が透明", all(px[3] == 0 for px in corners))
                # 線が存在する=不透明ピクセルがある（alphaの最大>0）
                check("線(不透明画素)が存在", im.getchannel("A").getextrema()[1] > 0)

            with page.expect_download() as dj:
                page.click("#savejson")
            jobj = json.load(open(dj.value.path(), encoding="utf-8"))
            check("JSON保存VP数", len(jobj.get("vanishing_points", [])) == n_vp + 2)
            check("JSON保存chars数", len(jobj.get("characters", [])) == n_char0 + 1)
            check("JSONに guide_density", "guide_density" in jobj)

            # 誤差1°未満は水平へ自動補正 / 1°以上は傾きを保持（状態を変えるので最後に）
            snap_lt1 = page.evaluate("""() => {
                window.S.horizon={ya:0.5,yb:0.5};
                const r=window.imgRect(); const Ps=[(r.x0+r.x1)/2,(r.y0+r.y1)/2];
                window.rotateHorizon(0.5*Math.PI/180, Ps);   // 0.5°だけ回す
                return Math.abs(window.S.horizon.ya-window.S.horizon.yb);
            }""")
            check("<1°は水平へ自動補正", snap_lt1 < 1e-9)
            keep_gt1 = page.evaluate("""() => {
                window.S.horizon={ya:0.5,yb:0.5};
                const r=window.imgRect(); const Ps=[(r.x0+r.x1)/2,(r.y0+r.y1)/2];
                window.rotateHorizon(3*Math.PI/180, Ps);     // 3°回す
                return Math.abs(window.S.horizon.ya-window.S.horizon.yb);
            }""")
            check("1°以上は傾きを保持", keep_gt1 > 1e-4)

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
