"""LoRA Preflight アプリ(app.py)の整形フロー e2e テスト。

サーバを実際に起動し、合成画像で /api/prepare/scan → /api/prepare/image を叩いて
- 通常モード: 1枚出力・規定サイズ
- 全身絵モード: {stem}_1..4.png の4枚出力・サムネURLが実出力から生成される
- manifest.json に source/kind/plan が記録される
を検証する。EVA02モデル・アップスケーラー不要。
実行: python tests/preflight_app_e2e.py
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
APP_DIR = REPO / "lora_preflight_app"

sys.path.insert(0, str(APP_DIR))
from PIL import Image  # noqa: E402


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _post(base: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(
        base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def _get_bytes(base: str, path: str) -> bytes:
    return urllib.request.urlopen(base + path, timeout=10).read()


def synth(path: Path, width: int, height: int, box: tuple) -> None:
    img = Image.new("RGB", (width, height), (255, 255, 255))
    img.paste(Image.new("RGB", (box[2] - box[0], box[3] - box[1]), (40, 40, 40)), (box[0], box[1]))
    img.save(path, "PNG")


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(("  ok: " if cond else "  NG: ") + name + ("" if cond else f" {detail}"))
        if not cond:
            failures.append(name)

    work = Path(tempfile.mkdtemp(prefix="preflight_e2e_"))
    input_dir = work / "raw"
    input_dir.mkdir()
    synth(input_dir / "normal_a.png", 1200, 1000, (100, 100, 1100, 900))
    synth(input_dir / "fullbody_b.png", 900, 2000, (300, 50, 600, 1950))

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, "app.py", "--port", str(port), "--no-browser"],
        cwd=str(APP_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            try:
                _get_bytes(base, "/")
                break
            except Exception:
                time.sleep(0.2)
        else:
            print("server did not start")
            return 1

        scan = _post(base, "/api/prepare/scan", {"inputDir": str(input_dir), "outputDir": str(work / "out")})
        check("scan ok", scan.get("ok") is True)
        images = {img["name"]: img for img in scan["images"]}
        session_id = scan["sessionId"]

        # 通常モード
        res = _post(
            base,
            "/api/prepare/image",
            {"sessionId": session_id, "imageId": images["normal_a.png"]["id"], "mode": "normal", "padCropX": 0.5},
        )
        outs = res["image"]["results"]
        check("通常: 1枚出力", len(outs) == 1, str(len(outs)))
        out_path = Path(outs[0]["image"])
        check("通常: ファイル名は元名", out_path.name == "normal_a.png", out_path.name)
        with Image.open(out_path) as img:
            check("通常: 出力寸法=規定サイズ", f"{img.width}x{img.height}" == outs[0]["targetSize"], str(img.size))
        check("通常: サムネURLあり", bool(outs[0].get("thumbUrl")))
        thumb = _get_bytes(base, outs[0]["thumbUrl"])
        check("通常: サムネ取得できる", len(thumb) > 500, str(len(thumb)))

        # 全身絵モード
        res = _post(
            base,
            "/api/prepare/image",
            {"sessionId": session_id, "imageId": images["fullbody_b.png"]["id"], "mode": "fullbody"},
        )
        outs = res["image"]["results"]
        check("全身: 4枚出力", len(outs) == 4, str(len(outs)))
        names = [Path(o["image"]).name for o in outs]
        check("全身: 命名 _1.._4", names == [f"fullbody_b_{i}.png" for i in (1, 2, 3, 4)], str(names))
        kinds = [o["kind"] for o in outs]
        check("全身: 種別順", kinds == ["fb_upper", "fb_body", "fb_feet", "fb_full"], str(kinds))
        for o in outs[:3]:
            with Image.open(o["image"]) as img:
                check(f"全身: {o['kind']} は1024正方形", img.size == (1024, 1024), str(img.size))
        with Image.open(outs[3]["image"]) as img:
            check("全身: fb_full は縦向き", img.height >= img.width, str(img.size))
        for o in outs:
            check(f"全身: {o['kind']} サムネ取得", len(_get_bytes(base, o["thumbUrl"])) > 500)

        # manifest
        manifest_path = work / "out" / "manifest.json"
        check("manifest がある", manifest_path.exists())
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            items = manifest.get("items", [])
            check("manifest: 5項目(1+4)", len(items) == 5, str(len(items)))
            check("manifest: source記録", all(i.get("source") for i in items))
            check("manifest: kind記録", {i["kind"] for i in items} == {"normal", "fb_upper", "fb_body", "fb_feet", "fb_full"})
            check("manifest: plan記録", all(i.get("plan", {}).get("crop_box") for i in items))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(work, ignore_errors=True)

    if failures:
        print(f"\nFAILED: {failures}")
        return 1
    print("\nALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
