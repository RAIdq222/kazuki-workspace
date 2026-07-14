"""assets 自動探索のユニットテスト（PYTHONPATH=src python tests/assets_test.py）。"""
from __future__ import annotations
import os
import sys
import tempfile

sys.path.insert(0, "src")
from genzu_fix import assets


def _touch(p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").close()


def main():
    fails = []

    def check(name, cond):
        print(("ok  " if cond else "FAIL") + " " + name)
        if not cond:
            fails.append(name)

    check("ep 07 の表記ゆれ", set(assets._ep_tokens("07")) == {"07", "7", "007"})
    check("work 尚善→shzも", "shz" in assets._work_tokens("尚善"))

    # ep8 相当の完全ツリー
    r = tempfile.mkdtemp()
    os.makedirs(os.path.join(r, "00.原図"))
    os.makedirs(os.path.join(r, "01.美術ボード", "01.美術ボード"))
    os.makedirs(os.path.join(r, "10.生成結果"))
    _touch(os.path.join(r, "尚善008原作修正済決定稿0101.pdf"))
    _touch(os.path.join(r, "尚善_色香盤表#08_260512.xlsx"))
    _touch(os.path.join(r, "shz_08_conte_決定稿0101.pdf"))
    _touch(os.path.join(r, "資料", "[尚善]世界観・背景設定補足.pdf"))
    m = assets.discover(r, "尚善", "08")
    check("原図/ボード/出力を検出", all(m[k] for k in ("genzu_dir", "boards_dir", "out_dir")))
    check("script は決定稿(conteでない)", m["script"] and "conte" not in os.path.basename(m["script"]))
    check("conte は conte", m["conte"] and "conte" in os.path.basename(m["conte"]))
    check("koban は xlsx", m["koban"] and m["koban"].endswith(".xlsx"))
    check("設定資料を収集", len(m["settings"]) >= 1)
    check("missing なし", not m["missing"])

    # 欠落ツリー（香盤/コンテ無し）→ missing に出る・落ちない
    r2 = tempfile.mkdtemp()
    os.makedirs(os.path.join(r2, "00.原図"))
    _touch(os.path.join(r2, "尚善009決定稿.pdf"))
    m2 = assets.discover(r2, "尚善", "09")
    check("欠落は missing に", "koban" in m2["missing"] and "conte" in m2["missing"])
    check("部分成功で genzu/script は取れる", m2["genzu_dir"] and m2["script"])

    # SP2 #10 実構成（ユーザーが整えた形）: 03.設定資料 配下＋「<ep>…コンテ」語順
    r3 = tempfile.mkdtemp()
    os.makedirs(os.path.join(r3, "00.原図", "談"))
    os.makedirs(os.path.join(r3, "01.美術ボード"))
    os.makedirs(os.path.join(r3, "10.生成結果"))
    _touch(os.path.join(r3, "03.設定資料", "SP2#10_決定稿コンテ.pdf"))
    _touch(os.path.join(r3, "03.設定資料", "隔離空間の輪郭線について.jpg"))
    _touch(os.path.join(r3, "03.設定資料", "SP2_現実世界_隔離空間_夜.psd"))
    m3 = assets.discover(r3, "佐々木とピーちゃん第2期", "10")
    check("SP2: コンテは conte に（scriptでない）",
          m3["conte"] and "コンテ" in os.path.basename(m3["conte"]) and not m3["script"])
    check("SP2: 設定資料フォルダ配下を収集(コンテ除く)",
          len(m3["settings"]) == 2 and all("コンテ" not in s for s in m3["settings"]))

    if fails:
        print("FAIL:", fails)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
