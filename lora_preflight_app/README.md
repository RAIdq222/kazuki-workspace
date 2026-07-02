# LoRA Preflight

SDXL/Animagine向けキャラLoRAの前処理を、AI Toolkit投入前までまとめるローカルWeb UIです。

この版でできること:

- 新規キャラ画像フォルダを読み込む
- 過去LoRAの `001.png` / `001.txt` 形式キャプションから固定タグ辞書を作る
- 固定タグ辞書を `config/tag_dictionary.json` として保存し、毎回のスキャンでは過去LoRAを読み直さない
- 新規画像を内蔵EVA2タグgerで解析し、固定タグ辞書でフィルタする
- ジャケットあり、マスクありなどの管理トリガーをサムネ一覧でチェックする
- 余白検出、クロップ、リサイズを行う
- `1024x1024`、`1152x896`、`1536x640` など最大3種の学習サイズから自動選択する
- 縦横入替が有効なら、`896x1152`、`640x1536` なども候補として扱う
- 全身などが切れそうな場合は、中身を切らずに必要最小限の余白で合わせる
- 必要ならSD WebUI/Forge APIの `R-ESRGAN 4x+ Anime6B` を後段に挟む
- Real-ESRGAN単体exe、または任意の手書きコマンドも使える
- 処理済み画像と同名 `.txt` を `dataset` フォルダへ出力する

未実装:

- 「AI Toolkitへ流し込んで開始」ボタンの中身
- AI ToolkitのWeb UI自動操作

## 起動

Python 3.10以降を用意します。

```powershell
pip install -r requirements.txt
python app.py
```

Windowsでは `run_windows.bat` でも起動できます。

起動後、ブラウザで以下が開きます。

```text
http://127.0.0.1:7869/
```

別ポートにしたい場合:

```powershell
python app.py --port 7870
```

ブラウザを自動で開きたくない場合:

```powershell
python app.py --no-browser
```

## 基本の使い方

1. `新規キャラ画像フォルダ` に処理したい画像フォルダを指定します。
2. 初回だけ、`過去LoRAフォルダ` に過去キャプション群の親フォルダを指定して `辞書作成/更新` を押します。
3. 以後は保存済みの固定タグ辞書を使うため、過去LoRAフォルダは毎回指定しなくて構いません。
4. 必要に応じて、キャラトリガー、共通タグ、管理トリガーを設定します。
5. `サムネ一覧を作成` を押します。
6. サムネ一覧で、ジャケットあり/マスクありなどの管理トリガーをチェックします。
7. `AI Toolkit投入前まで作成` を押します。
8. 出力先の `dataset` フォルダに、`001.png` / `001.txt` 形式で出力されます。

## フォルダ例

入力:

```text
new_character_input/
  image_a.png
  image_b.png
```

過去LoRA:

```text
past_loras/
  char_a/
    001.png
    001.txt
  char_b/
    001.png
    001.txt
```

出力:

```text
new_character_input_preflight/
  dataset/
    001.png
    001.txt
    002.png
    002.txt
  manifest.json
  vocabulary_summary.json
```

## EVA2タグger

初回だけ画面の `初回ダウンロード` を押すと、`wd-eva02-large-tagger-v3` のONNXモデルとタグ一覧を `models` フォルダへ保存します。
保存後のタグ付けはこのアプリ内で完結し、Stable Diffusion WebUI / Forge は不要です。

EVA2が使えない場合やタグが空の場合だけ、入力画像と同名の `.txt` があれば候補タグとして読みます。
入力画像に同名 `.txt` がなく、EVA2も使えない場合、画像内容から意味タグは生成されません。
その場合のキャプションは、キャラトリガー、共通タグ、サムネでチェックした管理トリガーのみになります。

## Real-ESRGAN / Anime6B連携

既定ではアップスケーラーは使いません。
必要な場合だけ `SD WebUI / Forge API: R-ESRGAN 4x+ Anime6B`、Real-ESRGAN単体exe、または手書きコマンドを選びます。

Stable Diffusion WebUI / Forge を `--api` 付きで起動している場合、以下の設定のまま使えます。

```text
WebUI API URL: http://127.0.0.1:7860
UpScaler名: R-ESRGAN 4x+ Anime6B
```

処理倍率は1倍です。クロップ/リサイズ後の完成サイズを保ったまま、Extras APIで補正します。

WebUI/Forgeを使わず単体exeで処理する場合は、`アップスケーラー方式` を `Real-ESRGAN単体 exe` に変え、実行ファイルを指定します。

```text
Real-ESRGAN実行ファイル: C:\tools\realesrgan-ncnn-vulkan.exe
モデル名: realesrgan-x4plus-anime
倍率: 1
```

モデルファイルの場所が標準と違う場合は、`モデルフォルダ` も指定してください。

手書きしたい場合は、`アップスケーラー方式` を `手書きコマンド` にします。

`{input}` が一時入力画像、`{output}` が最終出力画像に置換されます。

例:

```text
realesrgan-ncnn-vulkan.exe -i "{input}" -o "{output}" -s 1 -n realesrgan-x4plus-anime
```

アップスケーラーが失敗した場合は、Real-ESRGANなしの整形済み画像を出力し、警告を出します。

`使わない` を選んだ場合は、Real-ESRGANは実行されません。

## 注意

- 自動クロップは安全マージン付きですが、長い髪、武器、手足などが切れる可能性はあります。
- 現在は「中身を切らない」方を優先します。目的比率に完全に合わせられない場合は余白が残ります。
- 初回は必ず出力画像を確認して、`余白マージン` と `余白検出しきい値` を調整してください。
- 固定タグ辞書がない場合、候補タグはほぼ制限されません。
- キャプションの最終判断が必要な差分は、管理トリガーとして人間がチェックする前提です。
