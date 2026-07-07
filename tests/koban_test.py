"""香盤表パーサ（koban.py＋build_cut_board_map）のテスト。openpyxl不要・実データの癖を再現。

実行: PYTHONPATH=src python tests/koban_test.py
"""
from __future__ import annotations
import os
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, "src")
from genzu_fix import koban


def _sheet_xml(rows):
    def cell(ref, val):
        return f'<c r="{ref}" t="inlineStr"><is><t>{val}</t></is></c>' if val != "" else ""
    body = []
    for i, r in enumerate(rows, 1):
        cells = "".join(cell(f"{chr(65+j)}{i}", v) for j, v in enumerate(r))
        body.append(f'<row r="{i}">{cells}</row>')
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(body)}</sheetData></worksheet>')


def make_xlsx(path):
    """ep7 香盤表の癖を再現した最小xlsx（sheet2=シーン色ノイズ付き）。"""
    main_rows = [
        ["#07_色香盤表", "尚善 色香盤表", "#07", "2026/05/12"],
        ["CUT", "場所", "シーン色", "備考"],
        ["001～002", "夜空", "", "蛾おまかせ"],
        ["003～013", "", "BANK", ""],
        ["014～018", "花家_復活の儀の部屋", "復活の儀の部屋色", ""],
        ["023～046", "", "", "c046_ハイコンおまかせ"],      # 場所空欄=継承
        ["047～052", "花家_復活の儀の部屋", "夜色", ""],
        ["053～129", "森", "夜色", "c115おまかせ"],
        ["", "", "", "c117、118_色彩戻し"],                  # CUT空欄=備考続き
        ["Bパート", "", "", ""],                              # パート行=無視
        ["207～239A", "森", "朝色", ""],                      # 枝番で終わる
        ["239B～246", "", "", "c240…戻し"],                   # 枝番で始まる
        ["247～256", "", "森_よどんだ朝", ""],
        ["274～289", "道観_食堂", "室内_夕方(？)", ""],
        ["290~292", "イメージ", "01_normal", ""],             # 半角チルダ
        ["293～", "森", "01_normal", ""],                     # 終端開き
        ["色彩設計戻しカット", "", "", ""],                    # 以降は単票=無視
        ["c117", "", "", ""],
        ["c240", "", "", ""],
    ]
    noise_rows = [["#07_シーン色"], ["01_normal", "夜色"], ["尚善", "尚善"]]
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", _sheet_xml(main_rows))
        z.writestr("xl/worksheets/sheet2.xml", _sheet_xml(noise_rows))


def main():
    fails = []

    def check(name, cond, info=""):
        print(("ok  " if cond else "FAIL") + " " + name + (f"  ({info})" if info and not cond else ""))
        if not cond:
            fails.append(name)

    d = tempfile.mkdtemp()
    xp = os.path.join(d, "koban.xlsx")
    make_xlsx(xp)

    cuts, warns = koban.parse_koban_xlsx(xp, last_cut=298)
    by = {c["cut"]: c for c in cuts}

    check("xlsx読取＋展開でカットが出る", len(cuts) > 0)
    check("レンジ展開 001～002", "1" in by and "2" in by)
    check("BANKはbankフラグ", by.get("3", {}).get("bank") is True)
    check("場所の継承(023→復活の儀の部屋)", by.get("23", {}).get("place") == "花家_復活の儀の部屋")
    check("備考続き行が直前に連結", "c117、118" in by.get("53", {}).get("note", ""))
    check("枝番終端 239A", "239A" in by and by["239A"]["time"] == "朝")
    check("枝番始端 239B", "239B" in by and by.get("240") is not None)
    check("239(素)は存在しない", "239" not in by)
    check("シーン色→time(夜色→夜)", by.get("47", {}).get("time") == "夜")
    check("シーン色→time(よどんだ朝)", by.get("247", {}).get("time") == "よどんだ朝")
    check("シーン色→time(室内_夕方)", by.get("274", {}).get("time") == "夕方")
    check("半角チルダ 290~292", all(k in by for k in ("290", "291", "292")))
    check("終端開き 293～ を last-cut=298 で閉じる", all(str(n) in by for n in range(293, 299)))
    check("戻しカット節のc117単票は含めない", by.get("117") is None or by["117"]["range_label"] != "117")
    check("シーン色シート(ノイズ)を誤読しない", "01_normal" not in by)

    # --- end-to-end: 原図/ボード付きで CSV 生成 ---
    gz = os.path.join(d, "00.原図", "GKV")
    os.makedirs(gz)
    for fn in ("shz_08_001_genzu.psd", "shz_08_047_genzu.psd",
               "shz_08_239B_genzu.psd", "shz_08_023_030_genzu.psd"):  # 束カット
        open(os.path.join(gz, fn), "wb").close()
    bo = os.path.join(d, "boards")
    os.makedirs(bo)
    open(os.path.join(bo, "SZ#6_復活の儀の部屋(夜)_R1.png"), "wb").close()
    out_csv = os.path.join(d, "map.csv")
    r = subprocess.run(
        [sys.executable, "scripts/build_cut_board_map.py", "--koban", xp,
         "--genzu-dir", os.path.join(d, "00.原図"), "--boards-dir", bo,
         "--work", "尚善", "--ep", "08", "--last-cut", "298", "--out", out_csv],
        capture_output=True, text=True)
    print(r.stdout.strip()[:400])
    check("build スクリプト成功", r.returncode == 0, r.stderr[:200])
    import csv as _csv
    rows = list(_csv.DictReader(open(out_csv, encoding="utf-8-sig")))
    m = {x["cut"]: x for x in rows}
    check("BANK行は出力しない", "3" not in m)
    check("PSD一致: cut47", m.get("47", {}).get("filename") == "shz_08_047_genzu.psd"
          and m["47"]["assignee"] == "GKV")
    check("束PSD: cut23/30が同一filename", m.get("23", {}).get("filename") == "shz_08_023_030_genzu.psd"
          and m.get("30", {}).get("filename") == "shz_08_023_030_genzu.psd")
    check("枝番PSD: 239B", m.get("239B", {}).get("filename") == "shz_08_239B_genzu.psd")
    check("原図待ち: cut53は予測filename", m.get("53", {}).get("filename") == "shz_08_053_genzu.psd"
          and m["53"]["assignee"] == "(原図待ち)")
    check("ボード提案: 復活の儀(夜)が47に付く", "復活の儀" in m.get("47", {}).get("board", ""))
    check("確度低はボード空欄(夜空c1)", m.get("1", {}).get("board", "") == "")

    if fails:
        print("\nFAIL:", fails)
        return 1
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
