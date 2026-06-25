# データ受け渡し（ep7 10カット）— 受け手セッションへ

`handoff_request_for_data_session.md` への回答。**生データの受け渡しだけ**を扱う。
原図理解（situation/remove 等の記述）は受け手セッションが handoff の画像を見て行う作業で、
こちらから渡すのは一次素材（画像・寸法）に限る。ユーザーに分析結果を手入力させない。

対象10カット: **15, 23, 47, 53, 207, 240, 257, 274, 293, 294**

---

## 1. すでに git にある（再依頼は不要）
- `runs/ledger.jsonl` … 既存生成30行（cut/params/prompt/result_url 等）。旧プロンプト突合はこれで可能。
- `runs/cut_scene_info_ep7.csv` … `place / time / weather / structures / era` は記入済み。
  空欄は `situation / remove`（＋EN）だけ＝**受け手が画像を見て埋める列**。
- `runs/cut_board_map_ep7.csv`, `runs/boards_ep7.json`, `runs/board_manifest_ep7.{csv,md}` … ボード対応・索引。

## 2. 唯一こちらに無い＝作業マシンから渡す生データ
`work/`（.gitignore 除外）にしか無いものだけ。**1コマンドで生成**して commit する:

```
set PYTHONPATH=src
python scripts/gather_handoff_ep7.py ^
  --genzu-dir "C:\...\00.原図" ^
  --work "work" ^
  --conte-dir "C:\...\コンテ書き出し"    （あれば。無ければ省略可）
git add handoff/ep7
git commit -m "data: ep7 10カットの原図/コンテ受け渡し"
git push
```

`handoff/ep7/cut<NN>/` に入るもの:
| ファイル | 中身 | 必須 |
|---|---|---|
| `genzu.png` | 背景作画レイヤーのみ合成（自動検出Base相当） | ◎ |
| `genzu_visible.png` | 見たまま全レイヤー（指示・補助線・タップ穴も見える） | ○ |
| `manifest.json` | 画素/region/aspect/scale（work内にあればコピー） | △ |
| `conte.*` | 絵コンテ（--conte-dir にカット番号付き画像があれば） | △ |

受け手はこの `genzu.png`(構造)＋`genzu_visible.png`(指示)＋`conte` を見て、
`cut_scene_info_ep7.csv` の `situation/remove` を自分で埋める → CUT層を具体化。

## 3. データではなく「判断」— ユーザーが一言で答えればよい（B〜Dの残り）
分析でも素材でもなく、運用方針の確認。手入力作業ではない:
- **ボード2枚入力**（原図＋ボード画像のIMAGE2運用）に進めてよいか。
- **cut240 のボード**: scene「森_よどんだ朝」に board「#6 寝室(昼)」が当たって `道観_寝室` に化けている。正は森側か寝室側か。
- **出力 aspect**: カット固定値の根拠（ledger に 16:9 と 3:2 が混在）。
- **束カット**（016_026 等）は 1ファイル=1生成でよいか。
- **生成の分担**: そちら（work/有り）で回すか、`padded.png` を共有してこちらで回すか。

---

### 流れまとめ
受け手: `git pull` → `handoff/ep7/` を読む → `cut_scene_info` を自力で埋める → CUT層生成。
ユーザー: 上記コマンドで `handoff/ep7/` を push ＋ §3 を一言。これだけで前進する。
