# LoRA Preflight 画像整形 — 設計書

作成日: 2026-07-02
ブランチ: `claude/feature-design-implementation-u22jp5`
元資料: 同ディレクトリの `HANDOFF_MERGED.md` / `TODO_IMAGE_PROCESSING.md`（引き継ぎ資料のコピー）

## 0. 前提と実装の置き場所（最重要）

引き継ぎ対象アプリ本体（`app.py` ほか `lora_preflight_app` フォルダ）は
**このリポジトリには入っていない**（Windows 側 `C:\Users\Dolak\Documents\Codex\lora作り自動化\...` に実体、ZIP渡し想定）。

そこで実装は次の2層に分ける:

1. **コアロジック層（本リポジトリで実装・テスト完結）**
   - `src/lora_preflight/` に **UI非依存・純粋関数中心** のパッケージとして実装する。
   - 依存は PIL(Pillow) と numpy のみ（アプリ側 requirements と衝突しない最小構成）。
   - 合成画像によるユニットテストを `tests/` に置き、このリポジトリ単体で検証できる。
2. **アプリ統合層（app.py への薄いパッチ）**
   - `lora_preflight_app` の ZIP が手に入り次第、`app.py` から本パッケージを呼ぶ薄い統合を行う。
   - 統合手順書を `docs/lora-preflight/integration-notes.md` として実装時に書く。
   - それまでは **CLIドライバ（`scripts/preflight_plan.py`）** で実画像確認できるようにする。

この分割により「まず設計 → コア実装 → 実画像で確認 → app.py 統合」を、
アプリ本体の到着を待たずに進められる。

## 1. 設計原則: Plan（計画）と Render（実行）の分離 = WYSIWYG保証

引き継ぎ資料で最も強い要求は
**「画面サムネと実ファイル出力がズレてはならない」**（ユーザーが強く嫌がっている）。

これをアーキテクチャで保証する:

```
入力画像 ─→ analyze() ─→ ImageInfo（寸法・内容bbox・背景色）
ImageInfo + 設定 ─→ plan_*() ─→ CropPlan（純データ・JSON化可能）
入力画像 + CropPlan ─→ apply_plan() ─→ 出力画像（PIL Image）
```

- **CropPlan が唯一の真実**。クロップ矩形・パディング量・最終サイズ・背景色を全部持つ。
- サムネは `apply_plan()` の結果を縮小しただけのもの。**プレビュー専用の別経路を作らない**。
  → プレビューと出力PNGは同一関数の産物なので、原理的にズレない。
- CropPlan は manifest にそのまま記録する（再現・デバッグ・再実行が可能になる）。

## 2. 設定スキーマ

`config/default_settings.json`（アプリ側）に追記する想定。コア層では dataclass `PreflightConfig` として受け取る。

```jsonc
{
  "preflight": {
    "sizes": [[1024,1024],[1152,896],[1216,832],[1344,768],[1536,640]],
    "allow_rotate": true,          // 縦横入替候補（896x1152 等）も許可
    "pad_crop_x": 0.5,             // §3.3 のスライダー値 x（0..1、既定0.5）
    "max_crop_frac": 0.15,         // §3.4 「削りすぎ」判定: 元面積に対する切除率の上限
    "fullbody_base_height": 2200,  // §4 全身絵の正規化高さ
    "fullbody_tile": 1024,         // 全身絵から切る正方形の一辺
    "neck_ratio": 0.14             // §4.4 首位置の初期推定（人物高に対する頭の割合）
  }
}
```

`1024` / `2200` は資料の指示どおり**固定値にせず設定値**とする。

## 3. 通常画像の処理（顔アップ・上半身・バストアップ等）

### 3.1 解析

```python
analyze(img) -> ImageInfo(width, height, content_bbox, bg_color)
```

- `content_bbox`: 背景との差分による内容範囲。既存アプリの推定ロジックと同等の
  実装をコア層に持つ（境界画素の中央値を背景色とみなし、閾値差分で bbox を取る）。
- `bg_color`: 境界画素の中央値。パディングの塗り色に使う（真っ白でない資料画像に対応）。

### 3.2 比率候補の評価

入力 W×H（比率 r = W/H）。候補サイズ集合 S = 規定サイズ ∪（`allow_rotate` 時はその縦横反転）。

各候補 (w,h)、比率 c = w/h について、**同じ比率へ合わせる2通りの計画**を作る:

- **候補1（pad計画）**: 画像全体を残し、足りない側へ余白を追加して比率 c にする。
  - r > c なら上下に余白、r < c なら左右に余白。`pad_area` = 追加画素数。
- **候補2（crop計画）**: 最小限の切り取りで比率 c にする。
  - r > c なら左右を削り、r < c なら上下を削る。`crop_area` = 切除画素数。

比率が同じなら pad と crop は同一（両方ゼロ）＝無加工でリサイズのみ。

### 3.3 pad か crop かの決定（x スライダー）

資料の規則をそのまま式にする:

```
crop_area >= x * pad_area  →  候補1（pad）を採用
それ以外                     →  候補2（crop）を採用
```

- x はスライダー（0〜1、既定 0.5）。
- **x=0**: crop_area≥0 は常に真 → 常に余白側（padding優先）。
- **x=1**: 切り取り面積が余白面積を上回るときだけ pad → できるだけ crop。
- UI 説明文（そのまま使える文言）:
  > 「余白と切り取りのバランス。**0に近いほど余白を足して画像全体を残し**、
  > 1に近いほど余白を作らず切り取りで合わせます。迷ったら 0.5 のままで構いません。」

### 3.4 比率の選択と「削りすぎ」フォールバック

1. 第一候補 = 比率距離 `|log(c) - log(r)|` が最小のもの（縦長画像には縦系、横長には横系が自然に選ばれる）。
2. **削りすぎ判定**: 採用計画が crop で、`crop_area / (W*H) > max_crop_frac` のとき、
   その比率に固執しない。切除率が `max_crop_frac` 以下になる候補のうち比率距離最小のものへ逃がす。
3. どの候補でも収まらない場合は、全候補中 `crop_area` 最小のものを採用する
   （= 資料の「切り取り量が少なく、かつ規定サイズに収まるものを選ぶ」）。
4. フォールバックが起きたことは CropPlan にフラグとして残す（警告表示はするが、資料の指示どおり
   **警告で終わらせず自動でより良い処理へ逃がす**のが既定動作）。

### 3.5 切り取り位置（アンカー）

- **左右を削る場合（縦長→横詰め）**: content_bbox の水平中心にクロップ窓を合わせる（画像端にクランプ）。
- **上下を削る場合（横長→縦詰め）**: 資料の指示「基本的には上側を削り、絵のない白を優先して削る」を
  次の優先順で実装する:
  1. まず content_bbox の**外側の余白**（上→下の順）から削る。
  2. 余白だけで足りなければ、残りは**上側の内容**から削る。
  - 下端（足元・地面側）は最後まで守る。
- パディングは対象軸の両側へ均等（奇数分は下/右へ+1）。塗り色は `bg_color`。

### 3.6 仕上げ

- クロップ/パディング後、目標 (w,h) へ Lanczos リサイズ（拡大時は既存アップスケーラー経路を挟める）。
- 出力サイズは**必ず規定サイズに正確一致**（1px の誤差も不可。テストで担保）。

## 4. 全身絵の処理（1枚 → 4枚生成）

### 4.1 前処理（高さ正規化）

1. 高さを `fullbody_base_height`（2200）に合わせて拡縮。横幅 W' はこの時点では自由。
2. **W' > tile(1024) の場合**: 3枚の正方形タイル用に、content_bbox 水平中心基準で幅を 1024 へクロップ
   した「タイル用画像」を作る（A_4 全身用にはクロップ前の画像を使う）。
3. **W' < tile の場合**: 左右均等に `bg_color` でパディングして幅 1024 の「タイル用画像」を作る。
   人物は一切切らない（資料: 「変に人物を切らない。頭、足、体全体が残ることを優先」）。

### 4.2 A_1: 頭から上半身（1024x1024）

- `top = max(0, content_top - margin)`（margin 既定 16px。頭の上に少し空気を残しつつ頭は絶対に切らない）
- タイル用画像の `y ∈ [top, top+1024]` を切る。

### 4.3 A_3: 足元側（1024x1024）

- `bottom = min(H, content_bottom + margin)`
- `y ∈ [bottom-1024, bottom]` を切る。足先は絶対に切らない。

### 4.4 A_2: 首から下（1024x1024）

- 首位置は**画像位置ベースのヒューリスティック**で初期推定する（EVA02タグに依存しない。資料の方針どおり）:
  ```
  person_h = content_bottom - content_top
  neck_y   = content_top + neck_ratio * person_h    （neck_ratio 既定 0.14）
  ```
  立ち絵の標準的な頭身（6.5〜7.5頭身）で頭部は人物高の 13〜15% 程度に収まるため、
  0.14 を初期値とし設定で調整可能にする。
- `y ∈ [neck_y, neck_y+1024]` を切る（下端クランプ）。**顔を入れない**のが目的
  （`head out of frame` 構図の学習用）ため、迷ったら**やや下寄せ**（顔が入るより顎下で始まる方がよい）。
- UI に**首位置の微調整スライダー**を置き、手動で上下できるようにする（§6）。
  調整値は CropPlan → manifest に記録。

### 4.5 A_4: 全身をできるだけ残した1枚

- 候補 = 規定サイズの**縦向き**（640x1536, 768x1344, …。`allow_rotate` 前提）。
- 選択規則: パディングは許容し、**人物（content_bbox）に食い込むクロップがゼロで済む最も縦長の候補**を選ぶ。
  全候補で食い込みが出る場合は、人物の欠損面積が最小の候補（資料: まず 1536 系 → 削りすぎるなら 1344 系へ、の一般化）。
- 元の全身画像（幅クロップ前）から §3 と同じ pad/crop 機構で生成する。

### 4.6 命名と出力

元ファイル名 `A.png` に対し、名前順で【上半身→首から下→下半身→全身】と並ぶよう:

```
A_1.png  … 頭から上半身 (fb_upper)
A_2.png  … 首から下     (fb_body)
A_3.png  … 足元側       (fb_feet)
A_4.png  … 全身         (fb_full)
```

## 5. manifest 記録

既存 `manifest.json` に、出力1枚ごとに次を追記する:

```jsonc
{
  "source": "input/A.png",            // 派生元
  "output": "dataset/A_2.png",
  "kind": "fb_body",                  // normal | fb_upper | fb_body | fb_feet | fb_full
  "plan": { /* CropPlan の全フィールド: crop矩形, pad量, 目標サイズ, bg_color,
               neck_y, fallbackフラグ, 使用した設定値(x, max_crop_frac, ...) */ }
}
```

派生元と派生種別が残るので、後段（タグ付け・AI Toolkit投入）で
「同一元画像の派生4枚」をグルーピングできる。

## 6. UI 設計（`/` 画像整形画面への追加）

1. **処理モード選択**（画像ごと）: `通常画像` / `全身絵` のラジオまたはトグル。
   - まず手動選択のみ。自動判定（EVA02タグ or 人物縦長さヒューリスティック）は最終フェーズで
     「初期値の提案」として追加し、**必ず手動で上書き可能**にする。
2. **x スライダー**（通常画像用）: 0〜1、step 0.05、既定 0.5。§3.3 の説明文を添える。
3. **首位置スライダー**（全身絵用）: A_2 プレビュー上で ±調整。初期値は自動推定。
4. **プレビュー**: 全身絵は 4 枚ぶんのサムネをグリッド表示。サムネは §1 のとおり
   `apply_plan()` 結果の縮小のみ（別経路禁止）。
5. フォールバック（§3.4）発生時はサムネ隅にバッジ表示（例:「比率を 1216x832→1344x768 に変更」）。

## 7. モジュール構成と公開API

```
src/lora_preflight/
  __init__.py
  config.py      # PreflightConfig dataclass + JSON読み込み
  analyze.py     # analyze(img) -> ImageInfo（content_bbox, bg_color）
  planner.py     # plan_normal(info, cfg) -> CropPlan
                 # plan_fullbody(info, cfg) -> list[CropPlan]（4枚: kind付き）
  render.py      # apply_plan(img, plan) -> Image
                 # thumbnail(img, plan, max_side=512) -> Image  ＝ apply_planの縮小
scripts/
  preflight_plan.py   # CLI: 入力画像→plan JSON＋出力PNG＋サムネを work/ に出す（実画像確認用）
tests/
  test_lora_preflight.py
```

主要シグネチャ:

```python
@dataclass(frozen=True)
class CropPlan:
    kind: str                 # normal / fb_upper / fb_body / fb_feet / fb_full
    src_size: tuple[int,int]
    crop_box: tuple[int,int,int,int]   # 元画像座標。パディングのみなら全面
    pad: tuple[int,int,int,int]        # left, top, right, bottom（crop後座標）
    scale_to: tuple[int,int]           # 最終出力サイズ（規定サイズに一致）
    bg_color: tuple[int,int,int]
    fallback: str | None               # 比率フォールバックの説明（無ければ None）
    params: dict                       # x, neck_y, neck_ratio, base_height など使用値

def plan_normal(info: ImageInfo, cfg: PreflightConfig) -> CropPlan: ...
def plan_fullbody(info: ImageInfo, cfg: PreflightConfig) -> list[CropPlan]: ...
def apply_plan(img: Image.Image, plan: CropPlan) -> Image.Image: ...
```

すべて決定的（同じ入力・設定 → 同じ plan）。乱数・時刻に依存しない。

## 8. テスト計画（合成画像で不変条件を検証）

白背景＋色矩形（人物ダミー）の合成画像を使い、実画像なしで検証できるようにする:

1. **サイズ正確性**: どの入力でも出力寸法が規定サイズに正確一致。
2. **WYSIWYG**: `thumbnail()` と `apply_plan()` 縮小のピクセル一致（同一経路であることの回帰テスト）。
3. **スライダー単調性**: x を 0→1 に動かすと pad採用 → crop採用 へ単調に切り替わる。
4. **削りすぎフォールバック**: 極端な比率（例 1:3）で max_crop_frac 超過 → 候補が逃げ、fallback が記録される。
5. **全身4枚**: A_1 に content_top が、A_3 に content_bottom が含まれる（頭・足が切れない）。
   A_2 に content_top（頭頂）が含まれない。命名順が 1..4。
6. **幅不足/超過**: W'<1024 で人物画素が失われない（パディングのみ）。W'>1024 で中心クロップ。
7. **上削り優先**: 横長画像の縦詰めで、下端の内容が上端より優先して保存される。

## 9. 実装フェーズ（TODOの「まず実装してほしい順番」に対応）

| フェーズ | 内容 | TODO対応 | 場所 |
|---|---|---|---|
| P1 | コア: config / analyze / CropPlan / apply_plan / thumbnail ＋テスト | 2, 5(基盤) | 本リポジトリ |
| P2 | 通常画像: plan_normal（比率選択・x判定・フォールバック・アンカー）＋テスト | 2 | 本リポジトリ |
| P3 | 全身絵: plan_fullbody（2200正規化・4枚・首推定・命名）＋テスト | 3, 4 | 本リポジトリ |
| P4 | CLIドライバ `scripts/preflight_plan.py` で実画像確認 | 5 | 本リポジトリ |
| P5 | app.py 統合: モード選択UI・スライダー・4枚サムネ・manifest記録 | 1, 5, 6 | app到着後 |
| P6 | 自動判定（全身絵らしさの初期値提案） | 7 | app到着後 |

P1〜P4 はアプリ本体が無くても完了・検証できる。

## 10. 未決事項（ユーザー確認したい点）

1. **`lora_preflight_app` 本体（ZIP）をこのリポジトリに入れるか**。
   入れれば P5/P6 まで一気に進められる（`model.onnx` 等の大物は .gitignore で除外し、
   コードと config だけコミットする想定）。
2. `max_crop_frac`（削りすぎ判定の閾値）の既定値 0.15 でよいか。
3. `neck_ratio` 初期値 0.14 でよいか（どうせスライダーで微調整可能）。
4. パディング塗り色: 白固定ではなく境界色の自動推定でよいか。
5. 横長画像で余白を使い切っても足りない場合、「上側の内容」へ食い込む仕様でよいか
  （資料の記述どおりだが、顔が上にある構図では頭が削れ得る。プレビューで確認可能にはする）。
