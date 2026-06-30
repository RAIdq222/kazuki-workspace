#!/usr/bin/env python
"""パース編集エディタのランチャ（PYTHONPATH 不要）。

    python run_perspective_editor.py --port 8770 [--image path\\to\\cut.png]

ブラウザで http://127.0.0.1:8770/ を開き、画像パスを入れて「開く」。
アイレベル・消失点をドラッグで配置すると消失点へ収束するパースガイドを自動描画する。
「自動推定」で cv/vision/hybrid を叩いて初期値を流し込み、微調整して「保存」。
依存(flask/pillow/numpy)が無ければ、入れるコマンドを表示して終了する。
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def _check_deps():
    missing = []
    for mod, pip_name in (("flask", "flask"), ("PIL", "pillow"), ("numpy", "numpy")):
        try:
            __import__(mod)
        except Exception:
            missing.append(pip_name)
    if missing:
        print("必要なパッケージが不足しています:", ", ".join(missing))
        print("次を実行してから再度お試しください:")
        print("    python -m pip install " + " ".join(missing))
        return False
    return True


def main():
    if not _check_deps():
        sys.exit(1)
    from genzu_fix.perspective_editor import main as editor_main
    editor_main()


if __name__ == "__main__":
    main()
