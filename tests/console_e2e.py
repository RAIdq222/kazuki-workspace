"""コンソール(genzu_fix.server)のブラウザ動作テスト（①拡大 ②左右入替 ③ボードホバー他）。

実機の原図PSDやHiggsfieldを使わずに、out配下へ原図/結果のダミーPNGを置いて
画像ルート・比較ビュー・ボード表示の挙動をPlaywrightで検証する。

実行: PYTHONPATH=src python tests/console_e2e.py
依存が無い環境（playwright/chromium未導入）は SKIP して終了コード0。
"""
from __future__ import annotations
import os, sys, csv, time, socket, subprocess, tempfile

CHROMIUM = "/opt/pw-browsers/chromium"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _solid(path, color, size=(200, 300)):
    from PIL import Image
    Image.new("RGB", size, color).save(path)


def _make_fixture(root):
    out = os.path.join(root, "out")
    boards = os.path.join(root, "boards")
    gz = os.path.join(root, "genzu")  # 空でよい（PSDは無し）
    for d in (out, boards, gz, os.path.join(out, "testcut01")):
        os.makedirs(d, exist_ok=True)
    # 原図(前)=赤 / 最終結果(後)=青。比較で左右に出る。
    # 原図プレビューはソース別ファイル名（genzu_<source>.png）。既定 source=base。
    _solid(os.path.join(out, "testcut01", "genzu_base.png"), (220, 60, 60))
    _solid(os.path.join(out, "testcut01", "restored_full.png"), (60, 80, 220))
    _solid(os.path.join(boards, "BoardA.png"), (60, 200, 90))
    # QC結果（S3）: カードにバッジ／フィルタが出るか検証するため
    with open(os.path.join(out, "testcut01", "qc.json"), "w", encoding="utf-8") as f:
        f.write('{"verdict":"needs_retake","reasons":["色が残っている"],"checks":{}}')
    # テイク履歴（S5）: take_01=赤 / take_02=青、現行=take2。console_state に2テイクを仕込む
    for n, col in ((1, (220, 60, 60)), (2, (60, 80, 220))):
        td = os.path.join(out, "testcut01", "takes", f"take_{n:02d}")
        os.makedirs(td, exist_ok=True)
        _solid(os.path.join(td, "restored_full.png"), col)
    with open(os.path.join(out, "console_state.json"), "w", encoding="utf-8") as f:
        f.write('{"testcut01":{"status":"done","adopted":2,'
                '"takes":[{"n":1,"ts":0,"qc":"pass"},{"n":2,"ts":0,"qc":"needs_retake"}]}}')
    csv_path = os.path.join(root, "cuts.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cut", "assignee", "scene", "filename", "board"])
        w.writerow(["1", "GKV", "テストc001", "testcut01.psd", "BoardA.png"])
    return out, boards, gz, csv_path


def _wait_http(url, timeout=20):
    import urllib.request
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def main():
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print("SKIP: playwright未導入:", e)
        return 0
    if not os.path.exists(CHROMIUM):
        print("SKIP: chromium未検出:", CHROMIUM)
        return 0

    root = tempfile.mkdtemp(prefix="console_e2e_")
    out, boards, gz, csv_path = _make_fixture(root)
    port = _free_port()
    env = dict(os.environ, PYTHONPATH="src")
    proc = subprocess.Popen(
        [sys.executable, "-m", "genzu_fix.server", "--genzu-dir", gz,
         "--out", out, "--csv", csv_path, "--boards-dir", boards,
         "--work", "テスト", "--ep", "01", "--port", str(port)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    failures = []
    try:
        if not _wait_http(base + "/api/projects"):
            print("FAIL: サーバ起動せず")
            print((proc.stdout.read() or b"").decode()[-2000:])
            return 1
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(base, wait_until="networkidle")

            def check(name, cond):
                print(("ok  " if cond else "FAIL") + " " + name)
                if not cond:
                    failures.append(name)

            # カードが1枚描画される
            page.wait_for_selector(".card", timeout=8000)
            check("カード描画", page.locator(".card").count() == 1)
            # QCバッジ（S3）: needs_retake の qc.json → 「QC⚠」バッジ、QCフィルタで1件
            check("QC⚠バッジ表示", page.locator("text=QC⚠").count() >= 1)
            page.check("#fQC")
            check("QCフィルタで1件", page.locator(".card").count() == 1)
            page.uncheck("#fQC")

            # テイク履歴（S5）: 2テイクのチップ表示＋採用でadoptedが切替
            import json as _json
            import urllib.request
            check("テイクチップ2個", page.locator(".takechip").count() == 2)
            u0 = _json.loads(urllib.request.urlopen(base + "/api/units").read())[0]
            check("初期adopted=2", u0.get("adopted") == 2)
            page.once("dialog", lambda d: d.accept())  # adopt に confirm は無いが念のため
            page.locator(".takechip", has_text="T1").first.click()
            page.wait_for_timeout(700)
            u1 = _json.loads(urllib.request.urlopen(base + "/api/units").read())[0]
            check("採用でadopted=1に", u1.get("adopted") == 1)

            # 指示付きリテイク（A）: 指示入力→保存→APIに反映
            check("リテイク指示欄あり", page.locator("#rn_testcut01").count() == 1)
            page.fill("#rn_testcut01", "右の木の幹をつなげる")
            page.locator("#rn_testcut01").blur()
            page.wait_for_timeout(500)
            u2 = _json.loads(urllib.request.urlopen(base + "/api/units").read())[0]
            check("リテイク指示が保存された", u2.get("retake_note") == "右の木の幹をつなげる")
            # 画像ルート（原図/結果/ボード）が200
            import urllib.request
            for which in ("genzu", "result", "board"):
                code = urllib.request.urlopen(f"{base}/img/testcut01/{which}").status
                check(f"/img/{which}=200", code == 200)

            # 話数概要パネル＋主要ボード（登場回数）
            import json as _json
            import urllib.parse
            ov = _json.loads(urllib.request.urlopen(
                base + "/api/overview?key=" + urllib.parse.quote("テスト#01")).read())
            check("overview boardsにBoardA", any(b["board"] == "BoardA.png" for b in ov["boards"]))
            check("overview has_img=true", ov["boards"][0]["has_img"] is True)
            page.wait_for_selector("#ovbox .mboards", timeout=5000)
            check("概要パネル描画", page.locator("#ovbox .ovbox").count() >= 1)
            check("主要ボード画像表示", page.locator("#ovbox .mboards img").count() >= 1)
            mbsrc = page.get_attribute("#ovbox .mboards img", "src") or ""
            check("ボード画像=/board-img", "/board-img" in mbsrc)

            # 比較を開く（横並びが既定）
            page.evaluate("setCmpMode('side')")
            page.locator("text=前後比較").first.click()
            page.wait_for_selector("#cmp", state="visible")
            check("比較オーバーレイ表示", page.locator("#cmp").is_visible())
            check("横並びモード表示", page.locator("#cmpSide").is_visible())
            a = page.get_attribute("#cmpSideA", "src") or ""
            b = page.get_attribute("#cmpSideB", "src") or ""
            check("横並び左=原図", "/genzu" in a)
            check("横並び右=結果", "/result" in b)

            # ① 横並びの画像クリックで拡大（ライトボックス）
            page.click("#cmpSideA")
            page.wait_for_selector("#lb", state="visible")
            check("①画像クリックで拡大", "/genzu" in (page.get_attribute("#lbimg", "src") or ""))
            page.click("#lb")  # 閉じる

            # スライダーへ切替
            page.evaluate("setCmpMode('slider')")
            check("スライダーモード表示", page.locator("#cmpSlider").is_visible())
            top_before = page.get_attribute("#cmpImgA", "src") or ""
            check("スライダー上=原図(左)", "/genzu" in top_before)
            # ポインタ移動で境界が動く
            page.evaluate("""()=>{const s=document.querySelector('#cmpSlider');
              const r=s.getBoundingClientRect();
              s.dispatchEvent(new PointerEvent('pointermove',{clientX:r.left+r.width*0.25,bubbles:true}));}""")
            left25 = page.evaluate("()=>document.querySelector('#cmpDiv').style.left")
            check("境界が移動(≈25%)", left25 not in ("", "50%") and float(left25.replace("%", "")) < 40)

            # 重ね合わせ（透過スライダー）
            page.evaluate("setCmpMode('overlay')")
            check("重ね合わせモード表示", page.locator("#cmpOverlay").is_visible())
            check("透過スライダー表示", page.locator("#cmpOpsRow").is_visible())
            page.evaluate("cmpOpac(20)")
            op20 = page.evaluate("()=>document.querySelector('#cmpOvA').style.opacity")
            check("透過20%反映", abs(float(op20) - 0.20) < 0.01)
            page.evaluate("cmpOpac(80)")
            op80 = page.evaluate("()=>document.querySelector('#cmpOvA').style.opacity")
            check("透過80%反映", abs(float(op80) - 0.80) < 0.01)
            page.evaluate("setCmpMode('slider')")

            # ② 左右入替
            page.click("text=入替")
            top_after = page.get_attribute("#cmpImgA", "src") or ""
            check("②入替で上=結果に", "/result" in top_after)
            check("②タグ左が生成結果", page.inner_text("#cmpTagL") == "生成結果")
            page.click("text=入替")  # 元に戻す

            page.evaluate("()=>document.querySelector('#cmp').style.display='none'")

            # ③ ボード表示ホバーでプレビュー
            page.eval_on_selector("button:has-text('ボード表示')",
                                  """el=>{const r=el.getBoundingClientRect();
                                  el.dispatchEvent(new MouseEvent('mousemove',
                                  {clientX:r.left+2,clientY:r.top+2,bubbles:true}));}""")
            page.wait_for_selector("#bpop", state="visible", timeout=3000)
            check("③ホバーでボードプレビュー", "/board" in (page.get_attribute("#bpopImg", "src") or ""))
            # クリックでボード拡大
            page.click("button:has-text('ボード表示')")
            page.wait_for_selector("#lb", state="visible")
            check("ボードクリックで拡大", "/board" in (page.get_attribute("#lbimg", "src") or ""))

            check("JSランタイムエラー無し", not errs)
            if errs:
                print("  pageerror:", errs)
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    if failures:
        print(f"\n{len(failures)} 件失敗:", failures)
        return 1
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
