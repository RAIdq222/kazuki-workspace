# 美術ボード → Blender 3Dステージ化 — 検証メモ

> ステータス: PoC成功 (2026-07-14)。台所ボード1枚を3Dステージ化し、2アングルでレンダリング確認済み。

## 1. 目的

美術ボード(彩色済みの背景設定画)を Blender で立体化し、
レイアウト・背景作業のリファレンス(カメラを自由に動かせる3Dステージ)として使う。
X の事例(Fable 5 にアニメ背景用3Dステージを全自動生成させる)と同じアプローチ。

## 2. PoC 題材

- **SZ#1_台所_清書.png** (Google Drive: `01.美術ボード`, fileId `1keBMzFsIDHc2wA2YX1sQm9AXoE32VwvB`)
- 同じ部屋を2アングル(かまど側/入口側)で描いた彩色ボード → 形状のクロスチェックができ、
  かつ色・ライティングの参照になるため第1号に採用。
- 線画の美術設定 `shz_b01_04_食堂`(パース図+立面図)も取得済み (`04.美術設定`)。
  次の題材候補。

## 3. 実行環境(検証済みの事実)

- **`pip install bpy` でヘッドレスBlenderが動く**(bpy 5.0.1 / Python 3.11)。
  Claude Code on the web のサンドボックス内で完結。Blender本体のインストール不要。
- レンダは Cycles CPU (このコンテナは4コア)。1600px・96サンプル・デノイズ有で1枚数分。
- Eevee はヘッドレス(GPUなし)では不可。Cycles一択。
- Google Drive MCP のダウンロードは **10MB 上限**。それ以上のボード(清書PNGは100MB超が多い)は
  縮小版を用意してもらうか、別経路が必要。
- MCPの大きいツール結果は自動でファイルに保存される → base64 を Python でデコードすれば画像として扱える
  (チャット貼付画像は保存されないので、受け渡しは引き続き Drive 経由)。

## 4. 作り方(スクリプトの構造)

`src/stage3d/kitchen_stage.py` — 全プロシージャル(外部アセットなし)。

1. ボードを目視で読み取り、部屋をパラメータ化
   (部屋 6.4×4.4m・壁高2.55m・切妻天井、木造軸組+漆喰パネル壁、格子窓、板張り床)
2. 部品ごとに関数化: 床/壁軸組/天井(垂木・梁)/格子窓/かまど/棚/壺/薪/机/格子戸/収納棚/籠
3. マテリアルはボードから拾ったパレット(PAL辞書)のフラットな Principled BSDF。
   床板はオブジェクトランダムで明度を揺らして板ごとの色ムラを再現
4. ライティング: 格子窓の外に面光源+発光面(外光)、天井下に暖色フィル、暗めのワールド
5. ボードと同じ2アングルにカメラを置いてレンダ (AgX, exposure 0.9)

実行:

```bash
pip install bpy pillow  # 初回のみ
python3 src/stage3d/kitchen_stage.py -- --views A,B --samples 96 \
    --res 1600x1035 --out work/renders --blend work/kitchen_stage.blend
```

`--blend` で .blend も保存されるので、手元の Blender GUI で開いてカメラを動かせる。

## 5. ハマりどころ(再発防止)

- `primitive_cube_add(size=1)` は一辺1 → `scale` にはそのまま寸法を入れる
  (半分にすると全部品が½サイズになり、床に隙間・家具が浮く)。
- bpy 5.0 で `use_nodes` に DeprecationWarning が出るが動く(Blender 6.0 で削除予定)。

## 6. 単一HTMLビューワー (2026-07-14 追加)

Blenderを使わずにカメラ操作+スクショだけできる閲覧用ビューワーを追加。

- `src/stage3d/viewer_app.js` … Three.js のビューワー本体(プリセットカメラ/画角スライダー/
  WASD移動/スクショ保存ボタン)。編集機能なし。
- `src/stage3d/build_viewer.py` … .blend → GLB(メッシュのみ) → esbuild でバンドルした JS と
  GLB(base64) を1つのHTMLに埋め込む。**出来た HTML はブラウザで開くだけで動く(オフライン可)**。

```bash
# 前提: npm i three esbuild 済みのディレクトリ (node_modules) を用意
python3 src/stage3d/build_viewer.py --blend work/kitchen_stage.blend \
    --title "尚善 台所 3Dステージ" --node_dir <node_modulesのある場所> \
    --out work/kitchen_viewer.html
```

ハマりどころ:
- Base Color にノードが刺さったマテリアル(床の色ムラ)は glTF 変換で白落ちする
  → エクスポート前にリンクを外し固定色に落とす処理を入れた。
- esbuild はエントリファイルの場所から node_modules を解決する → エントリを node_dir 側へ
  コピーしてからバンドル。
- Three.js のライトは Cycles と単位が違うため強度は別調整
  (Playwright+Chromium のヘッドレススクショで確認しながら詰めた)。

## 7. 追加シーン (2026-07-14): 竹林の山道 / 俯瞰の寝室

チャット貼付の2ボードを同じ手法で立体化 (画像はチャット貼付だとファイル保存されないため、
内容を読み取ってパラメータ化。今後は Drive 経由が確実)。

- `src/stage3d/stagelib.py` … box/cyl/sphere/mat/カメラ/レンダCLIを共通化
- `src/stage3d/bamboo_path.py` … 竹林の山道。**大量配置は ops で作らず、テンプレートを
  `object.copy()`(リンク複製) でばら撒く**(opsで1本ずつ作ると数千opsで数十分かかる)。
  遠景の岩山 + 半透明板を重ねたアニメ的な霧 (`fog_` 接頭辞、ビューワーでは three.js の
  Fog に置き換えるため `--exclude_prefix fog_` でGLBから除外)
- `src/stage3d/topdown_room.py` … 俯瞰の寝室 (朱の飾り格子建具・屏風・黒漆箪笥・寝台・
  衣桁・行灯)。手前の南壁は作らないステージセット構成 (ボードの俯瞰を遮らない)
- `src/stage3d/configs/*.json` … ビューワーのシーン設定 (カメラプリセット/ライト/フォグ/露出)。
  `build_viewer.py --config` で注入。座標は three.js 系 (Blender `(x,y,z)` → `(x, z, -y)`)

ハマりどころ追記:
- Blender カメラの `clip_end` は既定100m → 遠景の山が切れる。`stagelib.add_camera` で500mに
- 俯瞰ボードの部屋は「カメラ側の壁を作らない」が正解 (壁があると外側しか映らない)
- Playwright での動作確認は `click()` がWebGL負荷でタイムアウトすることがある
  → `page.evaluate()` で直接 onclick を呼ぶ

## 8. 次アクション(案)

- [ ] 尚善の他ボードの立体化(線画設定 `shz_b01_04_食堂` はパース図+立面図で好条件)
- [ ] カメラパス(ゆっくりPAN)の連番レンダ → 動画化(ツイートの0:19動画相当)
- [ ] 本番運用するなら: ボード→パラメータ読み取りの観点テンプレ化、部品ライブラリの共通化
- [ ] 200MB級の清書ボードの受け渡し経路(縮小書き出し or 別ホスト)
