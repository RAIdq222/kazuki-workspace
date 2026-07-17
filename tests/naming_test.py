"""naming.parse_cut_codes のテスト（shz 回帰＋SP2 対応）。
実行: PYTHONPATH=src python tests/naming_test.py
"""
from __future__ import annotations
import sys

sys.path.insert(0, "src")
from genzu_fix.naming import parse_cut_codes as p


def main():
    fails = []

    def check(name, cond, got=""):
        print(("ok  " if cond else "FAIL") + " " + name + (f"  -> {got}" if not cond else ""))
        if not cond:
            fails.append(name)

    # 尚善（回帰）
    r = p("shz_07_091_101_116_genzu.psd")
    check("shz 束カット", (r["work"], r["ep"], r["cuts"]) == ("shz", "07", ["091", "101", "116"]), r)
    r = p("shz_07_239B_genzu_BGonly.psd")
    check("shz 枝番+BGonly", r["cuts"] == ["239B"], r)
    r = p("shz_07_015_genzu.psd")
    check("shz 単カット", r["cuts"] == ["015"], r)

    # 佐々木とピーちゃん第2期（SP2 = prefixに数字・_genzuサフィックス無し）
    r = p("SP2_10_006.psd")
    check("SP2 単カット", (r["work"], r["ep"], r["cuts"]) == ("SP2", "10", ["006"]), r)
    r = p("SP2_10_022_025.psd")
    check("SP2 束カット", r["cuts"] == ["022", "025"], r)
    r = p("SP2_10_267_276.psd")
    check("SP2 束カット2", r["cuts"] == ["267", "276"], r)
    r = p("SP2_10_290_R.psd")
    check("SP2 _R(リテイク版)は修飾扱い", r["cuts"] == ["290"], r)
    r = p("SP2_10_258_BG only.psd")
    check("SP2 'BG only'は修飾扱い", r["cuts"] == ["258"], r)

    # 非原図（参考PSD等）はカット無し
    r = p("SP2_現実世界_隔離空間_夜.psd")
    check("参考PSDはカット無し", r["cuts"] == [], r)
    r = p("BGサイズ_144dpi基本.psd")
    check("テンプレPSDはカット無し", r["cuts"] == [], r)

    if fails:
        print("FAIL:", fails)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
