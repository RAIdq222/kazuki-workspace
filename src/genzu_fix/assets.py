"""話数の各種参照ファイルを「フォルダを指すだけ」で自動特定する（ep8以降の脱ハードコード）。

背景: ep7 は runs/*_ep7.csv やフォルダパスがコード/バッチにベタ書き。新話数を足すたびに
散らばった箇所を直すのは事故のもと。ここでは作業ルートを走査して
  原図フォルダ / 美術ボードフォルダ / 出力フォルダ / 脚本(決定稿) / 香盤表 / 絵コンテ / 設定資料
を命名規則から見つけ、1つの project マニフェスト(dict)にまとめる。

命名規則（ep7 実データから一般化。ep は 07 / 007 / 7、作品は 尚善 / shz の揺れを吸収）:
  脚本   尚善<ep3>...決定稿....pdf         例) 尚善007原作修正済決定稿0718.pdf
  香盤   ...香盤...#?<ep>....xls[x]         例) 尚善_色香盤表#07_260512.xlsx
  コンテ <shz>_<ep>_conte....pdf / ...コンテ...<ep>....pdf  例) shz_07_conte_決定稿1025.pdf
  原図   フォルダ名 00...原図
  ボード フォルダ名 01...美術ボード（ネスト可）
  出力   フォルダ名 10...生成結果
  設定   ...設定... を含む pdf/docx（作品共通・複数）＝設定資料

この dict をそのまま runs/project_<work>_<ep>.json に保存し、server/batch が読めば
話数追加は「discover → その json を渡す」だけになる。Drive 側の探索は scripts 側で拡張。
"""
from __future__ import annotations
import os
import re

# 作品プレフィックス(shz)→和名(尚善)。server.WORK_NAMES と揃える。
WORK_ALIASES = {"shz": ["尚善"], "尚善": ["shz", "尚善"]}


def _ep_tokens(ep: str) -> list[str]:
    """ep 文字列から照合に使う表記ゆれを作る。'07'→['07','007','7']。"""
    ep = str(ep).strip()
    digits = re.sub(r"\D", "", ep) or ep
    n = int(digits) if digits.isdigit() else None
    toks = {ep, digits}
    if n is not None:
        toks |= {f"{n:02d}", f"{n:03d}", str(n)}
    return [t for t in toks if t]


def _work_tokens(work: str) -> list[str]:
    toks = {work}
    toks.update(WORK_ALIASES.get(work, []))
    for k, vs in WORK_ALIASES.items():
        if work == k or work in vs:
            toks.add(k)
            toks.update(vs)
    return [t for t in toks if t]


def _build_specs(work: str, ep: str):
    """(key, kind, [compiled regex...]) のリスト。kind='dir'|'file'|'files'(複数収集)。"""
    eps = _ep_tokens(ep)
    ep_alt = "(?:%s)" % "|".join(sorted((re.escape(e) for e in eps), key=len, reverse=True))
    works = _work_tokens(work)
    w_alt = "(?:%s)" % "|".join(re.escape(w) for w in works)

    def rx(*pats):
        return [re.compile(p, re.IGNORECASE) for p in pats]

    return [
        # フォルダ（作業ルート直下想定・番号プレフィックス）
        ("genzu_dir", "dir", rx(r"^0*0[\.\s_]*原図")),
        ("boards_dir", "dir", rx(r"^0*1[\.\s_]*美術ボード")),
        ("out_dir", "dir", rx(r"^10[\.\s_]*生成結果")),
        # 話数固有ファイル
        ("script", "file", rx(rf"{w_alt}.*{ep_alt}.*決定稿.*\.pdf$",
                              rf"{w_alt}0*{ep_alt}.*(?:脚本|決定稿|シナリオ).*\.pdf$")),
        ("koban", "file", rx(rf"香盤.*#?\s*{ep_alt}.*\.xlsx?$",
                             rf"{w_alt}.*香盤.*{ep_alt}.*\.xlsx?$")),
        ("conte", "file", rx(rf"(?:shz|{w_alt})[_\s]*{ep_alt}[_\s]*conte.*\.pdf$",
                             rf"(?:絵?コンテ).*{ep_alt}.*\.pdf$")),
        # 作品共通（複数）
        ("settings", "files", rx(rf"{w_alt}.*設定.*\.(?:pdf|docx)$",
                                 r"(?:世界観|設定補足|設定参考).*\.(?:pdf|docx)$")),
    ]


def discover(root: str, work: str, ep: str, max_depth: int = 4) -> dict:
    """作業ルートを走査して参照先を特定。戻り: project マニフェスト dict。"""
    specs = _build_specs(work, ep)
    dir_hits = {k: [] for k, kind, _ in specs if kind == "dir"}
    file_hits = {k: [] for k, kind, _ in specs if kind in ("file", "files")}
    root = os.path.abspath(root)
    base_depth = root.rstrip(os.sep).count(os.sep)

    for cur, dirs, files in os.walk(root):
        depth = cur.count(os.sep) - base_depth
        if depth > max_depth:
            dirs[:] = []
            continue
        for d in dirs:
            for k, kind, pats in specs:
                if kind == "dir" and any(p.search(d) for p in pats):
                    dir_hits[k].append(os.path.join(cur, d))
        for f in files:
            for k, kind, pats in specs:
                if kind in ("file", "files") and any(p.search(f) for p in pats):
                    file_hits[k].append(os.path.join(cur, f))

    def pick_dir(cands):
        # 浅い（ルートに近い）ものを優先。ネスト boards(01/01)は最深の実体でなく最初でOK。
        return sorted(cands, key=lambda p: (p.count(os.sep), len(p)))[0] if cands else None

    # 脚本(決定稿)と絵コンテ(決定稿)は名前が紛らわしい。conte に該当するものは script から除外。
    conte_set = set(file_hits.get("conte", []))
    if "script" in file_hits:
        file_hits["script"] = [f for f in file_hits["script"] if f not in conte_set]

    def pick_file(cands):
        return sorted(cands, key=lambda p: (p.count(os.sep), -len(os.path.basename(p))))[0] if cands else None

    manifest = {
        "work": work, "ep": str(ep), "root": root,
        "genzu_dir": pick_dir(dir_hits["genzu_dir"]),
        "boards_dir": pick_dir(dir_hits["boards_dir"]),
        "out_dir": pick_dir(dir_hits["out_dir"]),
        "script": pick_file(file_hits["script"]),
        "koban": pick_file(file_hits["koban"]),
        "conte": pick_file(file_hits["conte"]),
        "settings": sorted(set(file_hits["settings"])),
    }
    keys = ["genzu_dir", "boards_dir", "out_dir", "script", "koban", "conte"]
    manifest["found"] = [k for k in keys if manifest[k]] + (["settings"] if manifest["settings"] else [])
    manifest["missing"] = [k for k in keys if not manifest[k]]
    return manifest
