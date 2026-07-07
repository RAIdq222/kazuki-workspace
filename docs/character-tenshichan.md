# 天使ちゃん キャラクター設定（公式設定資料に基づく）

> 2026-07-06 取り込み。原本: Drive「設定資料」フォルダ（01_ラフ / 02_着彩）。
> 生成に使う参照画像は Higgsfield メディアライブラリ登録済み（下記 media_id）。

## 参照画像（Higgsfield media_id — generate_video の image_references に使う）

| 資料 | media_id | 用途 |
|---|---|---|
| 三面図（着彩・正面/横/背面） | `09c22898-36d7-433f-9582-f732fc6e5100` | 形状・衣装ディテールの補助参照 |
| カラーラフver（3面） | `22cb2de5-1822-40d9-b2a6-1a6d1622f778` | 補助（色味の別解釈） |
| うさぎぬいぐるみ設定 | `eb75692f-6f08-44ba-822a-5ac8242b22e8` | 部屋シーン・ぬい登場回 |
| スマホ（ケース）設定 | `ff72251e-1a95-4dd7-b37d-b6e65ddf1fdf` | スマホ操作カット |

### ルック参照フレーム（本編実動画から抽出・字幕除去済み。**塗り/ルックの主参照**）

> 2026-07-07 追加。三面図だけを参照にすると「設定資料の絵」に寄ってしまい
> 本編のルック（柔らかいグラデの豊かなアニメ塗り＋温かいライティング）から外れる、
> というユーザー指摘を受けて、本編フレームをルックの一次参照に昇格。

| フレーム | media_id | 内容 |
|---|---|---|
| look_face_eating | `ce3220ac-ab9a-4b57-ad34-95044529bf99` | 顔アップ（食事・チョーカー/フード目元） |
| look_bust_nightstreet | `87d156cd-b768-456b-8394-c906e6837b1e` | 夜街の上半身（叫び顔・照明） |
| look_full_street | `d951c4ef-1837-4e79-93d5-b76e079942c1` | 夕方の全身立ち（衣装全体・プロポーション） |
| look_full_dynamic | `2f7fd693-8a70-465c-a598-5bdf9175d8bf` | ダイナミックな全身ポーズ |

再抽出手順: Personal Clipperのクリップ（CloudFront）→ fps=0.5でフレーム展開 →
lbpcascade_animeface で顔サイズ上位を選抜 → 下部の焼き込み字幕帯をクロップ →
media_upload。

### シーン別 背景/舞台の参照セット（2026-07-07 追加）

> ユーザー指摘: ルック参照だけだと「別の家の内装」になる。**シーンの舞台ごとに
> 実動画の該当舞台フレームを参照に入れる**こと。舞台参照が無い場所の企画は、
> 先にライブラリ（docs/scene-library-design.md）から抽出してから生成する。

**屋外セット（15話・牛丼回 8AoIEagt3x8 から。最近回はライティングの統一性が高い）**

| フレーム | media_id | 内容 |
|---|---|---|
| out15_starry_bust | `7538c328-5d19-440e-bf6b-994a7357982a` | 星空の下のバスト（夜空・逆光気味） |
| out15_full_streetlight | `8dd042a8-1bfb-48d8-b5a5-7922a84da0bf` | 住宅街の街灯下・全身 |
| out15_back_nightwalk | `e6b2f224-7164-4bc5-8d53-13211c153563` | 夜道を歩く後ろ姿 |
| out15_bust_nightstreet | `068f114e-aee8-4ba3-a429-e666ea7eb7a8` | 夜の街のバスト |

**部屋（1K内装）セット（チキンラーメン回 8Y1ym_5tjNU から。
※部屋紹介ショート 9HPDI3bQWW0 はClipperがクリップ0本で失敗＝ショートは取り込み不安定）**

| フレーム | media_id | 内容 |
|---|---|---|
| room_shelf_plushies | `33067f70-2ca8-46d1-8adf-1873bb60d5cc` | ぬい棚のある壁際（部屋の質感） |
| room_window_eating | `084247ff-46fc-45f7-96be-bff7d190c7d7` | 夜窓＋白うさぎぬい＋食卓（部屋の定番構図） |
| room_bookshelf | `9a4af8d3-0b38-47c9-841f-d931a0368ef0` | 枕・壁面（寝床まわり） |

**使い方**: 生成時の参照 = ルック参照（顔/塗り）＋**舞台参照（そのシーンの場所）**＋
必要な小物設定画。屋外モノは屋外セットから1〜2枚、部屋モノは部屋セットから1〜2枚を
必ず image_references / 静止画生成の参照に入れる。

CloudFront URL は `show_medias`(type=image) でいつでも再取得可。

## ビジュアル仕様（三面図から）

- **フード**: 白のうさぎ耳フード付きオーバーサイズパーカー。フードに**紫のバッテン(×)ボタン目**
  と**ピンクの頬マーク**（＝ぬいぐるみと同じ顔）。前開き、裾リブ
- **インナー**: 薄紫のフリルブラウス＋濃紫の大きなリボンタイ
- **ボトム**: 黒ハイウエストスカート（フロントボタン2列）、膝上丈
- **脚**: 素足に**絆創膏**（右膝下に緑、左すねに青）※左右・色は三面図準拠
- **足元**: 白フリルソックス＋黒の厚底ローファー
- **髪**: 茶色ロング＋**ピンクのインナーカラー**、前髪ぱっつん気味
- **目**: 紫（大きめ）。**黒チョーカー**着用
- 体型: 小柄・華奢

## 小物設定

- **ぬいぐるみ**: 白うさぎ。紫バッテンボタンの目・ピンク頬・首に紫リボン。垂れ耳・ずんぐり体型
- **スマホ**: 薄紫ケース。背面にぬいぐるみと同じ顔（×目＋頬＋リボン）のプリント。カメラ3眼

## 性格・世界観（動画解析から。詳細は docs/shorts-ideation.md §1）

20代独身OL / 職場の理不尽で病む→深夜に回復 / ぼっち気味 / 感情表現大 / ポンコツ可愛い。
夜の街・1Kの部屋・ラーメン屋等が主な舞台。

## Seedance 生成時の定型（プロンプトに含める英語記述）

```
A petite young woman wearing an oversized white bunny-ear hoodie (purple X-button
eyes and pink cheek marks on the hood), light-purple frilly blouse with a large
dark-purple ribbon, black high-waisted button skirt, black chunky loafers with
white frilly socks, adhesive bandages on her legs, long brown hair with pink
inner color, large purple eyes, black choker. Japanese anime style.
```

- 参照は最低でも三面図を `image_references` に渡す（横顔/後ろ姿カットで特に効く）
- ぬい/スマホが映るカットはその設定画も追加で渡す

## ルック制御の勝ちパターン（2026-07-07 QCテストで確立。以後の生成はこの手順必須）

**教訓（2段階で学んだ）**:
- 三面図＋テキストだけのSeedance直行 → 耳が長くなる・別ルックの厚塗り化（初回の失敗）
- 三面図参照＋「フラットセル塗り」指示 → 今度は**設定資料の絵に寄りすぎて本編と合わない**
  （2回目の失敗。ユーザー指摘）
- **正解: ルックは本編実動画フレーム（上記「ルック参照フレーム」）を一次参照にし、
  三面図は形状・衣装ディテールの補助に回す**。本編のルック＝柔らかいグラデの
  豊かなアニメ塗り・繊細な線・温かいシネマティックライティング・
  短い垂れ耳フード・（多くのカットで）実写寄り背景との合成

**2段階QCフロー**:
1. **スタートフレームを静止画で確定**（安い）: `generate_image` model=nano_banana_pro、
   参照= **ルック参照フレーム2〜3枚（顔＋全身を混ぜる）**＋必要なら三面図。
   プロンプトの要点:
   - `match the identity AND the exact art style / rendering look of the attached
     anime screenshot references (same series): soft rich anime shading with gentle
     gradients, warm cinematic lighting, delicate lineart` ＋ `Do NOT flatten the style`
   - 実写背景合成なら `composited over a photorealistic live-action background`
     ＋ `soft natural contact shadow under her feet`
   - 細部チェックリスト: 短い垂れ耳 / 紫X釦目＋ピンク頬マーク / リボン / チョーカー /
     絆創膏（右膝下=緑・左すね=青）/ 白フリルソックス＋黒厚底ローファー / ピンクインナー
2. **合格した静止画を `start_image` にして Seedance で動かす**: roleは
   `start_image`（`image_references` は複数形が正）。プロンプト冒頭に
   `Keep her design, outfit, proportions and the art style COMPLETELY unchanged
   from the start frame` を入れ、**音声はSE/環境音のみの定型文必須**
   （docs/shorts-script-style.md §4）。10秒1カットでルック維持を確認してから本数を増やす

**実績**: 浅草雷門Vlogテスト（三面図版: image `0eb418c4-…`→video `415bfa90-…`/`fdc15805-…`、
本編ルック版: image `6480199f-…`）。10秒のルック維持・SEのみ音声（whisper検査クリーン）を確認。
残課題: 絆創膏の左右が入れ替わることがある（静止画段階で目視チェックして弾く）

## 未収集（あれば追加）

- 表情差分シート、パーカー以外の衣装（パジャマ等）、部屋の全景設定画
- 脚本類: 今回のフォルダには未格納だった（ラフ2点と着彩フォルダのみ）。
  共有されたら口調・語彙の辞書を作ってタイトル/セリフ生成に反映する
