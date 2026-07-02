# LoRA Preflight App 引き継ぎメモ

作成日: 2026-07-02

この文書は、別のChatGPT/Codex/開発者へこのフォルダを渡し、続きの改善作業を進めるための統合版引き継ぎメモです。  

## 対象フォルダ

```text
C:\Users\Dolak\Documents\Codex\lora作り自動化\outputs\lora_preflight_app
```

このフォルダごとZIPにして渡す想定です。

## 目的

LoRA作成前の準備をローカルだけで進めるための試作ツールです。

主な目的:

- 画像整形、規定サイズ化
- EVA02による自動タグ付け
- 登録済みタグ辞書でのタグフィルター
- 管理トリガー追加
- AI Toolkit投入前の画像と `.txt` キャプション作成

他人にZIPで渡す前提なので、原則としてこのフォルダ内で完結させます。

## 起動方法

1. `run_windows.bat` を実行する。
2. 初回は `.venv` がなければ自動作成される。
3. `wheelhouse/` から依存パッケージをインストールするため、基本的にインターネット不要。
4. ブラウザで `http://127.0.0.1:7869/` を開く。

受け取る側のPCには Python 3.10以上が必要です。

## 現在の主な画面

- `/`
  - 画像整形・アップスケール画面。
  - 規定サイズ候補は `1024x1024`, `1152x896`, `1216x832`, `1344x768`, `1536x640`。

- `/tagging`
  - EVA02タグ付け、管理トリガー、AI Toolkit投入前データ作成画面。

- `/dictionary`
  - タグ辞書編集画面。
  - Excelなしで辞書を編集できる。

## 現在の整理状態

削除済み:

- `models/wd-eva02-large-tagger-v3/model.safetensors`
- `.sessions/`
- `__pycache__/`

残しているもの:

- `.venv/`
  - 起動確認済みの環境を壊さないため残している。
  - 配布ZIPを軽くしたい場合は削除してよい。
  - 削除しても `run_windows.bat` が受け取り側PCで作り直す。

## 必ず残すもの

配布ZIPに残すもの:

- `app.py`
- `run_windows.bat`
- `requirements.txt`
- `wheelhouse/`
- `static/`
- `config/tag_dictionary.json`
- `config/default_settings.json`
- `models/wd-eva02-large-tagger-v3/model.onnx`
- `models/wd-eva02-large-tagger-v3/selected_tags.csv`

特に `config/tag_dictionary.json` は登録済み辞書なので消さないでください。

## 削除してよいもの


確認後に削除してよい:

- `.venv/`
  - 配布には基本不要。
  - ZIPを軽くしたいなら削除可。
  - ただし今のPCで起動確認済み環境を残したいなら残してよい。

- 出力済みの `dataset/`, `manifest.json`, `*_preflight`, `*_prepared` など
  - 残っていれば配布には不要。

## EVA02モデル

現在の実装は ONNX Runtime でEVA02を動かします。

必要:

```text
models/wd-eva02-large-tagger-v3/model.onnx
models/wd-eva02-large-tagger-v3/selected_tags.csv
```


## タグ辞書

辞書本体:

```text
config/tag_dictionary.json
```

このファイルは必ず残してください。

EVA02が返すタグは `looking_at_viewer` のようにアンダーバー付きになることがあります。  
現在の実装では、読み込み時にアンダーバーをスペースへ正規化します。

例:

```text
looking_at_viewer -> looking at viewer
```

## 画像整形の現状

現在は試作段階です。

処理の流れ:

1. 画像から背景との差分で内容範囲を推定。
2. 内容範囲の縦横比に近い規定サイズを選ぶ。
3. その比率へクロップ。
4. 指定サイズへリサイズ。
5. 必要なら外部アップスケーラーへ渡す。

重要な注意:

- 全身画像の自動クロップは未完成。
- 頭や足が切れるケースがある。
- 直近で「頭と足を残すように処理する」試行をしたが、結果が悪かったため元の処理へ戻した。
- 次に改善する場合は、元画像、画面サムネ、出力PNGを必ず比較すること。
- ユーザーは「見えているものと実ファイル結果がズレる」ことを強く嫌がっている。

## アップスケーラーの現状

現在の選択肢:

- 使わない
- Stable Diffusion WebUI / Forge API
- Real-ESRGAN単体exe
- 手書きコマンド

### Stable Diffusion WebUI / Forge API

`R-ESRGAN 4x+ Anime6B` を使う場合は、Stable Diffusion WebUIまたはForgeを `--api` 付きで起動する必要があります。

通常URL:

```text
http://127.0.0.1:7860
```

WebUI/Forgeが起動していない、または `--api` が付いていない場合は接続エラーになります。

### Real-ESRGAN単体exe

配布物として安定させるなら、将来的にはこの方式を整備するのがよいです。

想定:

```text
tools/
  realesrgan/
    realesrgan-ncnn-vulkan.exe
    models/
```

現時点では `tools/realesrgan` 自動検出までは未実装です。画面でexeパスを指定する方式です。

## AI Toolkit連携の現状

AI Toolkitへ直接流し込んで学習開始するボタンは、まだ本実装ではありません。  
現状は「AI Toolkit投入前の画像とテキストを作る」ところまでが主対象です。

## 次のChatGPT/Codexへの依頼内容

このフォルダを受け取った次の担当者は、以下の順番で進めるとよいです。

1. `run_windows.bat` で起動確認する。
2. `/dictionary` で `config/tag_dictionary.json` の辞書が読めているか確認する。
3. `/tagging` でEVA02タグ付けが動くか確認する。
4. `/` の画像整形で、元画像、画面サムネ、出力PNGを比較する。
5. 全身画像のクロップ仕様を再設計する。
6. 画像整形の結果プレビューと実ファイルがズレないようにする。
7. Real-ESRGAN単体exeの同梱または自動検出を実装する。
8. AI Toolkitへ流し込む部分を設計する。

## 触る時の注意

- 不用意に辞書を消さない。
- `model.onnx` と `selected_tags.csv` を消さない。
- 画像整形ロジックは壊れやすいので、変更ごとに実画像で確認する。
- 画面に出ているサムネと実際の出力PNGが違う状態は避ける。
- `default_settings.json` に個人PCのパスが入ることがあるので、配布前に確認する。

## ZIP配布前チェックリスト

1. `config/tag_dictionary.json` が残っている。
2. `models/wd-eva02-large-tagger-v3/model.onnx` が残っている。
3. `models/wd-eva02-large-tagger-v3/selected_tags.csv` が残っている。
4. `model.safetensors` が入っていないことを確認する。
5. `.sessions/` がないことを確認する。
6. `__pycache__/` がないことを確認する。
7. `.venv/` を残すか削除するか決める。
8. `config/default_settings.json` に個人PCのパスが残っていないか確認する。
9. `run_windows.bat` で起動確認する。
10. 小さい画像で、画像一覧、タグ付け、出力作成を1回確認する。

## 関連ドキュメント

画像加工の追加仕様は、別ファイルの `TODO_IMAGE_PROCESSING.md` にまとめています。  
画像整形を改善する担当者は、必ずそちらも読んでください。
