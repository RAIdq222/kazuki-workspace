# 参照ファイルの自動探索（新話数の入口・脱ハードコード）

ep7 は原図/ボード/香盤/コンテ/脚本/設定資料の場所がコード・CSV・.batに散らばってベタ書き。
ep8 以降は「作業ルートを指すだけ」で参照先を自動特定し、1つの **project マニフェスト** にまとめる。

## 使い方（ep8 なら）
```
python scripts/discover_assets.py --root "C:\...\尚善_原図修正自動化検証" --work 尚善 --ep 08
# → runs/project_尚善_08.json を書き、検出結果を表示
python run_console.py --project runs/project_尚善_08.json
```
`--project` はコンソールの `genzu_dir / boards_dir / out / work / ep` を補完する
（個別に `--genzu-dir` 等で上書きも可）。

## 何を・どう探すか
`src/genzu_fix/assets.py`（`discover(root, work, ep)`）が作業ルートを走査（既定 深さ4）して命名規則で分類:

| キー | 種別 | 規則（ep=07/007/7・work=尚善/shz の揺れを吸収） | ep7 実例 |
|---|---|---|---|
| `genzu_dir` | フォルダ | `00…原図` | `00.原図` |
| `boards_dir` | フォルダ | `01…美術ボード`（ネスト可） | `01.美術ボード\01.美術ボード` |
| `out_dir` | フォルダ | `10…生成結果` | `10.生成結果` |
| `script` | ファイル | `<work>…<ep>…決定稿….pdf`（conteは除外） | `尚善007原作修正済決定稿0718.pdf` |
| `koban` | ファイル | `香盤…#?<ep>….xls[x]` | `尚善_色香盤表#07_260512.xlsx` |
| `conte` | ファイル | `<shz|work>_<ep>_conte….pdf` / `コンテ…<ep>….pdf` | `shz_07_conte_決定稿1025.pdf` |
| `settings` | 複数 | `<work>…設定….pdf/docx`、`世界観/設定補足/設定参考…` | `[尚善]世界観・背景設定補足.pdf` ほか |

- **script と conte の紛らわしさ**（両方「決定稿」）は、conte 該当を script から除外して解決。
- 見つからないものは `missing` に入る（**落とさず部分成功**）。フォルダ/ファイル名が規則と違えば
  生成 json を手で1行足せばよい（＝規則の外れ値も吸収できる設計）。

## マニフェスト（runs/project_<work>_<ep>.json）
```json
{ "work":"尚善","ep":"08","root":"…",
  "genzu_dir":"…/00.原図","boards_dir":"…/01.美術ボード","out_dir":"…/10.生成結果",
  "script":"…決定稿.pdf","koban":"…香盤表#08.xlsx","conte":"…conte.pdf",
  "settings":["…世界観….pdf", …], "found":[…], "missing":[…] }
```

## 今後の統合（B の残り）
- 現状 `--project` はコンソールのフォルダ系を補完。**cut_board_map/cut_scene_info/overview も project に束ねる**と
  完全に脱ハードコードになる（`--csv`/`--overview-json`/`--cut-info` を project から引く）。
- 新話数の cut_board_map は **香盤表(koban)→cut_board_map 生成ツール** が要る（香盤表パーサ。未実装＝次段）。
- Drive 側（PDF/xlsx が Drive のみの場合）の探索は、Drive ID を manifest に足す拡張で対応可能
  （このセッションは Drive MCP で ID を引ける。ローカルpipelineは fetch_asset でDL）。
