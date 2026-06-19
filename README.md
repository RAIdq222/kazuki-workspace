# 背景原図 修正支援ツール（genzu_fix）

商業アニメの背景原図（美術依頼用ラフ）を、美術ボードを参照しつつ配置を保ったまま、
パースの狂いや設定との齟齬を画像生成（Higgsfield 経由 GPT Image 2）で修正する PoC。
詳細設計は `docs/design-notes.md`。

## セットアップ
```
pip install -r requirements.txt
export PYTHONPATH=src
```

## パイプライン（CLI）
生成ステップだけ環境で認証経路が違うため prep / finish の2フェーズに分割。

```
# 1) PSD → 表示合成PNG → 比率パディング → manifest
python -m genzu_fix.cli prep path/to/genzu.psd \
    --prompt-file prompt.txt --board board.png --out-dir work/cut

# 2) work/cut/padded.png（＋board）を GPT Image 2 で生成し、結果を result.png に保存
#    （Claude Code on web では MCP 経由、本番環境では Higgsfield CLI/API）

# 3) 結果 → 切り戻し → 元PSDへ「AI原図修正」レイヤー差し込み → 台帳記録
python -m genzu_fix.cli finish work/cut/manifest.json --result result.png \
    --out-psd genzu_AI.psd --job-id <id> --result-url <url> --cost 7
```

## モジュール
- `image_aspect` … 許容比率への余白パディングと、相対座標での切り戻し。
- `psd_export` … PSDの表示レイヤー合成PNG / レイヤー一覧 / 結果のPSDレイヤー差し込み（リテイク枝番）。
- `ledger` … 生成台帳（原図/ボード/プロンプト/結果を1行=1生成で追記）。
- `cli` … prep / finish の2フェーズ・オーケストレーション。
