#!/usr/bin/env python
"""原図修正コンソールのランチャ（PYTHONPATH 不要）。

`python -m genzu_fix.server ...` は src レイアウトのため PYTHONPATH=src が要るが、
このスクリプトは src/ を自動で sys.path に足すので、どこから呼んでも起動できる:

    python run_console.py --genzu-dir "..\\00.原図" --out "..\\10.生成結果" --port 8765

依存(flask/psd-tools/pillow/numpy)が無ければ、入れるコマンドを表示して終了する。
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def _check_deps():
    missing = []
    for mod, pip_name in (("flask", "flask"), ("psd_tools", "psd-tools"),
                          ("PIL", "pillow"), ("numpy", "numpy")):
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
    from genzu_fix.server import main as server_main
    server_main()


if __name__ == "__main__":
    main()
