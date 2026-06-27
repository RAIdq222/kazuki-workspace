#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ep7 美術ボード マニフェスト生成.
Drive「01.美術ボード」(folder 17twdF6Nq48IsQR6wkoP8w5ocGFwLokWz) の実ファイル列挙から、
ep7 で使う/関連するボードを scene グループ別に board_manifest_ep7.csv / .md に出力する。
ID・URL は Drive 検索結果の実値（2026-06 時点）。閲覧URL = https://drive.google.com/file/d/<id>/view
"""
import csv, os

FOLDER = "17twdF6Nq48IsQR6wkoP8w5ocGFwLokWz"  # 01.美術ボード

# (board_filename, drive_id, scene_group, time, used_in_cutmap)
BOARDS = [
    # --- 復活の儀 / 花氏邸 ---
    ("SZ#6_復活の儀の部屋(夜)_R1.png", "1J4CtRurmidXqHnP3Yfv39TxSsRoNcSR4", "復活の儀の部屋", "夜", True),
    ("SZ#6_復活の儀の部屋(昼)_R1.png", "15Pu1VHemYBbhZD9_uYok4Fmhmp_oPL1v", "復活の儀の部屋", "昼", False),
    ("#6_復活の儀の部屋　外廊下（昼）_R1.png", "1GUWwavUlFdc6ecsqCib8aEBCpctYMoNP", "復活の儀の部屋", "昼", False),
    ("#6_復活の儀の部屋へのドア前（昼）.png", "1tFC1P-51Qj3009VOTgt9d-iaGMOwMVw-", "復活の儀の部屋", "昼", False),
    ("#6花氏邸_屋敷_祭壇(昼)_R1.png", "1ENT70LoQpnZyAhiSubw_dxXuJKqCaP2V", "復活の儀の部屋", "昼", False),
    ("#6花氏邸_屋敷_祭壇(浅夕)_R1.png", "1KvY_-IFiYjXR1-juzWXwHdhVn4tQ6J54", "復活の儀の部屋", "浅夕", False),
    ("#6_花氏邸_屋敷広間(夜)_R1.png", "1WzJl3XyNuI5QvIfyVUbAMPlBi2BjNa-C", "花氏邸_全景", "夜", False),
    ("#6_花氏邸_全景（夜）_R2.png", "1X97tGi9_C-kJoKPgElWRTWRHTjTwobmu", "花氏邸_全景", "夜", True),
    ("#6_花氏邸_全景（昼）_R1.png", "1qaS3-EzFU4sb4q9kInVwS21ce4pUpoL4", "花氏邸_全景", "昼", False),
    ("#6_花氏邸_全景（昼）_R2.png", "1P_5eco1v5dwggu2S7XFBluewoG4yte2y", "花氏邸_全景", "昼", False),
    ("#6_花氏邸_全景（夕方）_R2.png", "1eqKswiGejWMlpYZlfsVbMayy-3FKDCwh", "花氏邸_全景", "夕方", False),
    ("#6_花氏邸_全景（浅夕）_R2.png", "1KHUfakdUy3bznep0qlv2wW0KEB4JqHKA", "花氏邸_全景", "浅夕", False),
    ("#6_花氏邸_屋敷の入口_（昼）_幕あり_R2.png", "1n8uq-SXLpdKwHprGUXt8_VReb8A31nP8", "花氏邸_全景", "昼", False),
    ("#6_花氏邸_屋敷の入口_（昼）_幕なし_R2.png", "1ejBvYd1cOF_zpRaLfRaJDCEKnieajt1l", "花氏邸_全景", "昼", False),
    # --- 森 / 山中 ---
    ("#6#7森の中（夜）R.png", "1wgAo-MOBuZgFCIjE2GerRzMhB4FJFTMg", "森", "夜", True),
    ("#6#7森の中（昼）.png", "1y-LoifPzIiWMW5NI0sy6fbEg8CAo2Yh9", "森", "昼", True),
    ("森明けげ方.png", "1_zzR6GtZcUWDNf5PjLub3G_IQ5x3zl3E", "森", "朝/明け方", True),
    ("#6_山中 小さな池がある広場（昼）.png", "1NpPxSgFKrNycrRTEEjShk0hvlTfNEYM0", "山中_池の広場", "昼", False),
    ("#6_山中_小さな池がある広場_朝（霧あり）.png", "1ipZXIE46CcF_Pu9ofG-gfZ3_9M9mWHKb", "山中_池の広場", "朝(霧)", False),
    ("#6_山中 小さな池がある広場_朝（霧なし）.png", "14GhBkdO0IzJboldWTznzjfjzGBMAIe0H", "山中_池の広場", "朝", False),
    # --- 道観 / 寺院 ---
    ("#6_山の中道教の寺院（昼）_R1.png", "1vTABxngXIaHQrKjQ0AiaUtmSSZddxYGm", "道観", "昼", True),
    ("#6_山の中道教の寺院_R1_朝.png", "1eilKJiPxC87Fw12ug9yQZJBruO1AG3Qv", "道観", "朝", True),
    ("#6_山の中道教の寺院_R1_夕方.png", "1HUhgmAV3GwDXq9tE1hlFZbspEcQpI_II", "道観", "夕方", False),
    ("#6_山の中道教の寺院_R1_夕方 （雨）.png", "1lVn1ICdsqzrCowOomRBMYNFuYav5s-Dp", "道観", "夕方(雨)", False),
    ("#6_山の中道教の寺院_R1_夜.png", "1K15KwSf0i49WQnFwLw7LZCw3D-VN57rb", "道観", "夜", False),
    ("#6 寺院内　道然たちの寝室（昼）_R2.png", "1jhd7pHQcXsCrnfMCfLz9YDwyuQq2og3B", "道観_寝室", "昼", True),
    ("#6 寺院内　道然たちの寝室（夜_窓開きver）_R2.png", "17SDhik6h3t6OU16jGPQ7NSIzuXOuNwS5", "道観_寝室", "夜", False),
    ("寺院内 台所 食堂(夕方_雨)_R2_.png", "1L4dT0A0OJgIVns8Kmg6_abAcPs11bVxM", "道観_台所食堂", "夕方(雨)", True),
    ("寺院内 台所 食堂(朝)_R2.png", "1pX28Wt7-jvOvgJbrshT4CzgTwRDpLIOr", "道観_台所食堂", "朝", False),
    ("寺院内 台所 食堂(昼)_R2.png", "1B2ABxfdDQPLYcCySoqxA_qwj8Be4wY3j", "道観_台所食堂", "昼", False),
]

def url(fid): return f"https://drive.google.com/file/d/{fid}/view"

out_dir = os.path.join(os.path.dirname(__file__), "..", "runs")
out_dir = os.path.abspath(out_dir)
csv_path = os.path.join(out_dir, "board_manifest_ep7.csv")
md_path = os.path.join(out_dir, "board_manifest_ep7.md")

with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["board", "scene_group", "time", "used_in_cutmap", "drive_id", "view_url"])
    for name, fid, grp, t, used in BOARDS:
        w.writerow([name, grp, t, "yes" if used else "", fid, url(fid)])

groups = {}
for name, fid, grp, t, used in BOARDS:
    groups.setdefault(grp, []).append((name, fid, t, used))

with open(md_path, "w", encoding="utf-8") as f:
    f.write("# ep7 美術ボード 実画像マニフェスト\n\n")
    f.write("Drive「01.美術ボード」フォルダの実ファイルへの対応表。"
            "`★`= cut_board_map_ep7.csv が参照中のボード。\n"
            "リンクはGoogle Drive閲覧URL（要・対象アカウントでのログイン）。\n\n")
    f.write(f"- フォルダ: [01.美術ボード](https://drive.google.com/drive/folders/{FOLDER})\n")
    f.write("- 生成元: `scripts/make_board_manifest_ep7.py`（ID/URLはDrive検索の実値, 2026-06時点）\n\n")
    used_n = sum(1 for b in BOARDS if b[4])
    f.write(f"**収録: {len(BOARDS)}枚（うち cut_board_map 参照: {used_n}枚＝参照9種すべて実在確認済み）**\n\n")
    for grp in ["復活の儀の部屋", "花氏邸_全景", "森", "山中_池の広場",
                "道観", "道観_寝室", "道観_台所食堂"]:
        if grp not in groups:
            continue
        f.write(f"## {grp}\n\n")
        f.write("| | 時間 | ボード | リンク |\n|---|---|---|---|\n")
        for name, fid, t, used in groups[grp]:
            star = "★" if used else ""
            f.write(f"| {star} | {t} | `{name}` | [開く]({url(fid)}) |\n")
        f.write("\n")

print("wrote", csv_path)
print("wrote", md_path)
print(f"{len(BOARDS)} boards, {sum(1 for b in BOARDS if b[4])} used-in-cutmap")
