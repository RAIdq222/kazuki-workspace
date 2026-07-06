# LoRA Preflight 画像整形 — 設計書

作成日: 2026-07-02
ブランチ: `claude/feature-design-implementation-u22jp5`
元資料: 同ディレクトリの `HANDOFF_MERGED.md` / `TODO_IMAGE_PROCESSING.md`（引き継ぎ資料のコピー）

## 0. 前提と実装の置き場所（最重要）

アプリ本体は 2026-07-02 に ZIP で受領し **`lora_preflight_app/` に収載済み**
（コード＋config のみ。`models/` `.venv/` `wheelhouse/` はユーザーの Windows 側に実体）。

実装は2層に分ける:

1. **コアロジック層** = `lora_preflight_app/preflight_core.py`
   - **UI非依存・純粋関数中心**・依存は Pillow のみ。
   - アプリフォルダ内に置くのは、ZIP配布時にフォルダ単体で完結させるため
     （当初案の `src/lora_preflight/` からの変更点）。
   - テスト: `tests/preflight_core_test.py`（合成画像・モデル不要）。
2. **アプリ統合層** = `app.py` の整形処理（`process_image_v2`）とUI
   - e2e テスト: `tests/preflight_app_e2e.py`（サーバ実起動・HTTP経由で検証）。
   - 実画像の手元確認は CLI `scripts/preflight_plan.py`（アプリ起動不要）。

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

1. 採用比率 = 比率距離 `|log(c) - log(r)|` が最小のもの（縦長画像には縦系、横長には横系が自然に選ばれる）。
2. **実装時の発見**: 切除率は比率距離の単調関数（`crop_frac = 1 - exp(-距離)`）なので、
   **最近比率が常に最小クロップでもある**。つまり「別の（より緩い）比率へ逃がす」は
   数学的に発生し得ない。資料の意図（削りすぎ→余裕を出す）は**余白側（候補1）へ倒す**ことで実現する。
3. **削りすぎ判定**: 採用計画が crop で `crop_frac > max_crop_frac` のとき、同じ比率のまま
   **pad（余白）計画に切り替える**。画像は一切削られない。
4. フォールバックが起きたことは CropPlan.fallback に理由文字列として残し、UIにバッジ表示する
   （警告で終わらせず**自動でより安全な処理へ逃がす**のが既定動作）。

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

- 候補 = 規定サイズの**縦向き**（640x1536, 768x1344, …。`allow_rotate` 前提）。縦は全て残す。
- 選択規則: 縦長順（h/w 降順）に見て、**必要幅が人物幅以上になる最初の候補**
  ＝「人物に食い込まない最も縦長の比率」を選ぶ。幅が余白で足りない分はパディング。
  全候補で人物が欠ける場合のみ、欠損最小の候補へ逃がし fallback を記録
  （資料: まず 1536 系 → 削りすぎるなら 1344 系へ、の一般化）。
- 元の全身画像（幅クロップ前）から生成する。

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
lora_preflight_app/
  preflight_core.py   # コア一式（既存アプリの単一ファイル流儀に合わせ1ファイル）:
                      #   PreflightConfig / ImageInfo / CropPlan
                      #   analyze(img) -> ImageInfo
                      #   plan_normal(info, cfg) -> CropPlan
                      #   plan_fullbody(info, cfg, neck_ratio=None) -> list[CropPlan]（4枚）
                      #   plan_for_mode(info, cfg, mode) / apply_plan(img, plan) / thumbnail(...)
  app.py              # 統合: process_image_v2()（1 or 4枚出力）、run_upscaler()、
                      #   create_output_thumbnail()（出力実物からサムネ）、write_prepare_manifest()
scripts/
  preflight_plan.py   # CLI: 入力画像→plan JSON＋出力PNG＋サムネ（実画像確認用）
tests/
  preflight_core_test.py   # コア不変条件（合成画像）
  preflight_app_e2e.py     # サーバ実起動のe2e
```

出力命名: 整形画面（prepare）は**元ファイル名ベース**（`A.png` → `A.png` / `A_1..4.png`）。
タグ付け後のビルドは従来の連番 stem（`001.png` / `001_1..4.png`、caption `.txt` と対）。

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

| フェーズ | 内容 | TODO対応 | 状態 |
|---|---|---|---|
| P1 | コア: config / analyze / CropPlan / apply_plan / thumbnail ＋テスト | 2, 5(基盤) | **済 (2026-07-02)** |
| P2 | 通常画像: plan_normal（比率選択・x判定・フォールバック・アンカー）＋テスト | 2 | **済** |
| P3 | 全身絵: plan_fullbody（2200正規化・4枚・首推定・命名）＋テスト | 3, 4 | **済** |
| P4 | CLIドライバ `scripts/preflight_plan.py` で実画像確認 | 5 | **済**（合成画像で動作確認。実画像はユーザー確認待ち） |
| P5 | app.py 統合: モード選択UI・スライダー・4枚サムネ・manifest記録 | 1, 5, 6 | **済**（e2eテスト通過） |
| P6 | 自動判定（全身絵らしさの初期値提案） | 7 | 未着手（資料の指示どおり最後） |

残タスク:
- P6 自動判定（EVA02タグ or 人物縦横比ヒューリスティック→チェックボックス初期値の提案）。
- タグ付け画面(`/tagging`)側でのモード指定UI（現在 build API は `modes`/`neckYs` を受け取れるが UI 未配線）。
- Windows 実機（実画像・Real-ESRGAN 経路）での動作確認。

追記(2026-07-06): 首位置は**画像ごとの手動ライン**方式に決定（ユーザー判断）。
「全身絵として処理」を入れるとサムネ上に赤いラインが出て、ドラッグで首位置を指定
→ `neckY`（元画像座標）として送られ fb_body の切り出し上端になる（manifest に
neckSource: manual/auto を記録）。`neckRatio` はラインの初期位置のみに使う。
EVA02 による自動判定（§旧案）は P6 の「初期位置の提案」に格下げ。

## 10. 未決事項（ユーザー確認したい点）

1. **`lora_preflight_app` 本体（ZIP）をこのリポジトリに入れるか**。
   入れれば P5/P6 まで一気に進められる（`model.onnx` 等の大物は .gitignore で除外し、
   コードと config だけコミットする想定）。
2. `max_crop_frac`（削りすぎ判定の閾値）の既定値 0.15 でよいか。
3. `neck_ratio` 初期値 0.14 でよいか（どうせスライダーで微調整可能）。
4. パディング塗り色: 白固定ではなく境界色の自動推定でよいか。
5. 横長画像で余白を使い切っても足りない場合、「上側の内容」へ食い込む仕様でよいか
  （資料の記述どおりだが、顔が上にある構図では頭が削れ得る。プレビューで確認可能にはする）。
