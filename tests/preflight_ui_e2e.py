"""LoRA Preflight 画像整形画面のブラウザ表示テスト（Playwright）。

CSSバグ（例: #lightbox の display 指定が hidden 属性に勝って画面全体が黒幕で覆われる）
は HTTP レベルの e2e では検出できないため、実ブラウザで検証する。
- 初期表示でライトボックスが隠れている
- スキャン→全身チェック→整形→サムネ表示→クリックで拡大→Escで閉じる

実行: python tests/preflight_ui_e2e.py
依存が無い環境（playwright/chromium未導入）は SKIP して終了コード0。
"""
from __future__ import annotations

import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
APP_DIR = REPO / "lora_preflight_app"
CHROMIUM = "/opt/pw-browsers/chromium"

try:
    from PIL import Image
    from playwright.sync_api import sync_playwright
except ImportError as exc:
    print(f"SKIP: 依存が無い ({exc})")
    raise SystemExit(0)

if not Path(CHROMIUM).exists():
    print("SKIP: chromium が無い")
    raise SystemExit(0)


def main() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    base = f"http://127.0.0.1:{port}"

    work = Path(tempfile.mkdtemp(prefix="preflight_ui_"))
    raw = work / "raw"
    raw.mkdir()
    img = Image.new("RGB", (900, 2000), (255, 255, 255))
    img.paste(Image.new("RGB", (300, 1900), (60, 60, 90)), (300, 50))
    img.save(raw / "fullbody.png")

    proc = subprocess.Popen(
        [sys.executable, "app.py", "--port", str(port), "--no-browser"],
        cwd=str(APP_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(("  ok: " if cond else "  NG: ") + name + ("" if cond else f" {detail}"))
        if not cond:
            failures.append(name)

    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.2)
        else:
            print("server did not start")
            return 1

        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=CHROMIUM)
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(base + "/")
            page.wait_for_timeout(300)

            display = page.evaluate("getComputedStyle(document.getElementById('lightbox')).display")
            check("初期表示でライトボックスは非表示", display == "none", display)

            page.fill("#inputDir", str(raw))
            page.click("#scanBtn")
            page.wait_for_selector(".image-card", timeout=10000)
            page.locator("[data-mode-toggle]").first.check()
            page.wait_for_selector(".neck-line[data-neck-id]", timeout=5000)
            check("全身チェックで首ラインが出る", page.locator(".neck-line[data-neck-id]").count() == 1)

            # 首ラインをドラッグ→位置が変わる
            line = page.locator(".neck-line[data-neck-id]").first
            before = line.get_attribute("style")
            box = line.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 1)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 60, steps=5)
            page.mouse.up()
            after = line.get_attribute("style")
            check("首ラインをドラッグで動かせる", before != after, f"{before} -> {after}")

            page.click("#prepareBtn")
            page.wait_for_function("document.querySelectorAll('.result-thumb').length >= 4", timeout=30000)
            check("全身絵の4枚サムネが表示される", page.locator(".result-thumb").count() >= 4)

            page.locator(".result-thumb img").first.click()
            page.wait_for_timeout(300)
            display = page.evaluate("getComputedStyle(document.getElementById('lightbox')).display")
            check("クリックで拡大表示が開く", display == "flex", display)
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            display = page.evaluate("getComputedStyle(document.getElementById('lightbox')).display")
            check("Escで拡大表示が閉じる", display == "none", display)

            # 元画像の拡大表示: 首ライン付きで開き、拡大中にドラッグ調整→カードへ反映
            page.locator(".thumb-wrap > img").first.click()
            page.wait_for_timeout(400)
            display = page.evaluate("getComputedStyle(document.getElementById('lightbox')).display")
            check("元画像クリックで拡大表示が開く", display == "flex", display)
            neck_display = page.evaluate("getComputedStyle(document.getElementById('lightboxNeck')).display")
            check("拡大表示に首ラインが出る", neck_display != "none", neck_display)
            card_before = page.locator(".neck-line[data-neck-id]").first.get_attribute("style")
            lb_line = page.locator("#lightboxNeck")
            box = lb_line.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 1)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 80, steps=5)
            page.mouse.up()
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            card_after = page.locator(".neck-line[data-neck-id]").first.get_attribute("style")
            check("拡大中の調整がカードの首ラインへ反映", card_before != card_after, f"{card_before} -> {card_after}")
            check("JSエラーが出ていない", not errors, "; ".join(errors))
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    if failures:
        print(f"\nFAILED: {failures}")
        return 1
    print("\nALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
