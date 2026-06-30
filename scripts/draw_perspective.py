"""画像にアイレベル・消失点・キャラ垂直線を引く（PYTHONPATH 不要のラッパ）。

使い方:
  # 3手法すべてで解析し、横並び比較画像も出す（既定）
  python scripts/draw_perspective.py path/to/cut.png

  # 手法を選ぶ（vision / cv / hybrid / all、カンマ区切り可）
  python scripts/draw_perspective.py cut.png --method cv
  python scripts/draw_perspective.py cut.png --method vision,hybrid

  # 出力先を指定（既定 work/_perspective/<stem>/）
  python scripts/draw_perspective.py cut.png --out-dir work/persp

出力（work/_perspective/<stem>/ 既定）:
  <stem>.<method>.png   線を重ねたオーバーレイ
  <stem>.<method>.json  正規化座標（アイレベル/消失点/キャラ頭足）
  <stem>.compare.png    method=all のとき横並び比較

vision / hybrid は環境変数 ANTHROPIC_API_KEY が要る。cv は不要（numpy のみ）。
出来た PNG は Read ツールで開けば線が見える。
"""
from __future__ import annotations
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from genzu_fix import perspective

if __name__ == "__main__":
    raise SystemExit(perspective.main())
