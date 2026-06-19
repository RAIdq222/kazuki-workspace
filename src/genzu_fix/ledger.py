"""生成台帳 (generation ledger)。

将来の「管理画面」のデータ土台。1 生成 = 1 レコードを JSONL で追記する。
どの原図を / どの美術ボードを使い / どんなプロンプト・パラメータで生成し /
どんな結果(ジョブID・URL・保存先)になったかを後から追えるようにする。

UI は未実装。まずは機械可読な追記ログだけを確定させる。
"""
from __future__ import annotations
import json, time, os
from dataclasses import dataclass, field, asdict

LEDGER_PATH = os.environ.get("GENZU_LEDGER", "runs/ledger.jsonl")


@dataclass
class GenRecord:
    run_id: str                      # ジョブID (Higgsfield generation id)
    created_at: float                # epoch 秒
    cut: str                         # カット識別 (例: shz_02_143)
    genzu_file: str                  # 原図ファイル名 / Drive id
    board_files: list[str] = field(default_factory=list)  # 使った美術ボード(0..n)
    model: str = "gpt_image_2"
    params: dict = field(default_factory=dict)            # aspect_ratio/resolution/quality 等
    prompt: str = ""
    aspect_prep: dict = field(default_factory=dict)       # 比率パディング情報 (prep.json)
    result_url: str = ""             # 生成結果 rawUrl
    output_file: str = ""            # 切り戻し後の保存先
    cost_credits: float | None = None
    status: str = "completed"
    notes: str = ""


def append(rec: GenRecord, path: str = LEDGER_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")


def load(path: str = LEDGER_PATH) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
