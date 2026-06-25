# プロンプト設計：カット別 3層アセンブリ

> 目的: 設定資料・絵コンテ・香盤表から抽出したカット別情報を、GPT Image 2 への
> 生成プロンプトへ構造的に反映する。実装は `src/genzu_fix/prompt.py`。

## 1. 基本方針

- **3層アセンブリ**でプロンプトを組む（`森の中.md` の分離方針を全シーン/全カットへ一般化）。
- 出力は **EN（モデル入力）と JP（人の作業確認用）の対**。モデルへ渡すのは EN のみ。
- 機械で取れる所（time/weather/place/era/structures）は自動。コンテ依存の所
  （situation / 個別 remove）は空欄で持ち、後段（コンテ→Vision）で充足する。

```
[A] GLOBAL  作品共通  役割 / レジスト / 白黒線画 / 線質 / 除去 / 余白        … 固定文字列
[B] SCENE   シーン固有 場所語彙 / era / 構成物 / 避けるもの(anti)            … scene_profiles/<key>.json
[C] CUT     カット固有 time→線処理 / weather→線処理 / 場面 / 個別remove      … 香盤表 + ボード名 + コンテ
```

## 2. データの出どころ（機械化の境界）

| スロット | 一次情報源 | 自動度 | 現状 |
|---|---|---|---|
| time / weather | `naming.parse_board`（ボード名） | ◎機械 | 済 |
| place / era / structures / avoid | scene_profile | ◎機械（プロファイル整備後） | GKV 2シーン整備済 |
| **situation / 個別 remove** | **絵コンテ → Vision** | △ | 空欄（#4で充足） |

`runs/cut_board_map_ep7.csv` で **カット→ボードは確定済み**なので、A・B と C の
time/weather までは今すぐ機械生成できる。残る穴は「カット→場面/除去対象」のみ。

## 3. ファイル

- `src/genzu_fix/prompt.py` … 組み立てエンジン。
  - `build(board, scene) -> Prompt(en, jp, info)` … 表口。
  - `gen-info` サブコマンド … `cut_board_map` → `cut_scene_info_ep7.csv` を機械生成。
  - `show --cut N` … 1カットの EN/JP プロンプトを確認。
- `runs/scene_profiles/<key>.json` … B層の構造化・対訳データ。
  - キー項目: `place / era / structures / style_note / avoid`（各 en/jp）、`match`（別名）。
  - `match` は美術ボード名/シーン名への substring 一致でプロファイルを選ぶための別名。
- `runs/cut_scene_info_ep7.csv` … カット別の構造化情報（schema）。
  - 列: `cut, scene_key, place, time, weather, situation, situation_en, remove, remove_en, structures, era, source`。
  - `situation/remove` は対訳で持つ（JP=確認用 / `*_en`=モデル入力用）。④（conte）で充足。
  - 充足前でも人手で直接編集して埋めてよい（CSVがレビュー成果物を兼ねる）。
- `src/genzu_fix/conte.py` … ④ 絵コンテ→situation/remove 抽出（render→extract→merge）。下記 §7。
- `src/genzu_fix/batch.py` … `build_prompt`/`build_prompt_pair` が prompt.py へ委譲。
  生成時に出力先へ `prompt.en.txt`（モデル入力）/ `prompt.jp.txt`（確認用）を残す。

## 4. 設計上の効かせどころ（既知の弱点対策）

- **構図の再解釈**を抑える: GLOBAL 冒頭で "trace-and-clean, NOT a re-illustration" /
  "keep every contour anchored to the input" を最優先に置く。
- **線の硬さ**対策: 線質を「近景太/遠景細・入り抜き・ベクター/塗り絵調を禁止・ベタ禁止」と具体化。
- **除去ルール**は `qc.py` の「主体に属する=消す／環境=残す」と一語一句揃える（検品と一貫）。
- **白黒なので time/weather は色でなく線処理に翻訳**: 夜=陰影輪郭の密度、雨=線での濡れ表現、
  霧=遠景の線を疎に。グレーのベタ・ウォッシュは常に禁止。

## 5. 使い方

```bash
# カット別 構造化情報を機械生成（GKV）
python -m genzu_fix.prompt gen-info --assignee GKV --out runs/cut_scene_info_ep7.csv

# 1カットの EN/JP プロンプトを確認
python -m genzu_fix.prompt show --cut 15

# バッチ（既存）。prompt は自動で 3層アセンブリ。出力先に prompt.en/jp.txt が残る
python -m genzu_fix.batch --genzu-dir <原図> --out <出力> --assignee GKV
```

## 7. ④ 絵コンテ→situation/remove（`genzu_fix.conte`）

ep7 コンテ（`shz_07_conte_決定稿1025.pdf`）は **テキスト層なしの純スキャン**で OCR 不可
（Drive の read_file_content は空を返す）。よって **ページ画像化 → Claude Vision で構造化** する。
モデル入力は English Only のため、抽出は **対訳**（`situation`/`characters` を JP＋EN）で行う。

3工程（途中再開・人手レビュー可）。コンテ実物がある黒江さんローカルで実行する:

```bash
# 1. PDF の該当ページを PNG 化（GKV=花家/復活の儀の部屋 は cut14〜52 のページ）
python -m genzu_fix.conte render --pdf "…/03.設定資料/コンテ/shz_07_conte_決定稿1025.pdf" \
    --out work/conte_pages --first <P> --last <Q>

# 2. ページPNGを Claude Vision でコマ別JSON化（要 ANTHROPIC_API_KEY）
python -m genzu_fix.conte extract --pages-dir work/conte_pages --out runs/conte_frames_ep7.json

# 3. frames を cut_scene_info の situation/remove へマージ（前ゼロ違いも突合）
python -m genzu_fix.conte merge --frames runs/conte_frames_ep7.json \
    --cut-info runs/cut_scene_info_ep7.csv
```

- 抽出は qc.py の除去基準に揃える（characters=人物＋持ち物→消す / background_elements=環境→残す）。
- マージは `cut_label`→カット番号で突合。**コンテのNo.採番がパート別オフセットでズレる**場合は
  merge が「CSVに無いカット番号」を警告するので、最初の数本で対応を確認すること。
- batch は `--cut-info`（既定 `runs/cut_scene_info_ep7.csv`）を読み、充足済みカットは
  situation/remove 込みの [CUT] ブロックでプロンプトを組む（`prompt.build_for_cut`）。

## 8. 残り（順序：④ → ③ → ②）

- **③ scene_profile 整備**: GKV 以外のシーン（森/道観/花氏邸の各時間帯…）のプロファイルを追加。
  素材は Drive `04.美術設定`（場所別PNG）/ `資料`（世界観・参考写真）/ 美術ボード。
- **② GLOBAL 文面詰め**: 数カットで生成比較し、線質・レジスト・除去の効きを実測してから確定（保留）。
