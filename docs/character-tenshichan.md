# 天使ちゃん キャラクター設定（公式設定資料に基づく）

> 2026-07-06 取り込み。原本: Drive「設定資料」フォルダ（01_ラフ / 02_着彩）。
> 生成に使う参照画像は Higgsfield メディアライブラリ登録済み（下記 media_id）。

## 参照画像（Higgsfield media_id — generate_video の image_references に使う）

| 資料 | media_id | 用途 |
|---|---|---|
| 三面図（着彩・正面/横/背面） | `09c22898-36d7-433f-9582-f732fc6e5100` | **主参照**。全カットに必ず入れる |
| カラーラフver（3面） | `22cb2de5-1822-40d9-b2a6-1a6d1622f778` | 補助（色味の別解釈） |
| うさぎぬいぐるみ設定 | `eb75692f-6f08-44ba-822a-5ac8242b22e8` | 部屋シーン・ぬい登場回 |
| スマホ（ケース）設定 | `ff72251e-1a95-4dd7-b37d-b6e65ddf1fdf` | スマホ操作カット |

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

## 未収集（あれば追加）

- 表情差分シート、パーカー以外の衣装（パジャマ等）、部屋の全景設定画
- 脚本類: 今回のフォルダには未格納だった（ラフ2点と着彩フォルダのみ）。
  共有されたら口調・語彙の辞書を作ってタイトル/セリフ生成に反映する
