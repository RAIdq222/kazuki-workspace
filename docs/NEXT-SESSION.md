# 次セッションへの引き継ぎ (2026-06-19)

## 状況サマリ
- GitHub push: ✅ 解決（Claude GitHub App をインストール済み。push 可能）
- Higgsfield ネットワーク許可: ✅ ユーザーが設定済み（このセッションから有効なはず）
- 目的: 背景原図の修正を画像生成(Higgsfield GPT Image 2)で行う。詳細は `docs/design-notes.md`。

## まずやること（自動お試し生成の続き）
前セッションで「Drive取得→パディング→Higgsfieldアップロード→GPT Image 2生成→余白復元」を
組んだが、Higgsfield アップロード先が egress 未許可で最後だけ詰まっていた。今は許可済みのはず。

### 手順
1. Drive から原図を取得（MCP: `mcp__Google_Drive__download_file_content`）
   - 原図 fileId: `1ivcEnsk5Mtzlaq2qLRQlx9DsA3X7bCr2`
     （`shz_02_143_genzu_kari.png`, 2104x1464, RGBA）
   - 置き場フォルダ: `https://drive.google.com/drive/folders/1xlQPVqPMGI30zBmHYq-IbHla0uJLptIm`
   - バックアップmd fileId: `1iRN6ScdeW9Ssu_LLzluJl6p6MX72DLQm`
2. base64 を decode して PNG 保存（`work/` は .gitignore 済み）
3. `src/genzu_fix/image_aspect.py` の `build_input_image()` で 3:2 にパディング
   （2104x1464 → 3:2, canvas 2196x1464, 左右46px余白）
4. Higgsfield へアップロード（MCP）:
   - `mcp__Higgsfield__media_upload`(filename, content_type=image/png) で presigned URL 取得
   - `curl -X PUT --data-binary @work/genzu_input.png '<upload_url>'`
     ※前回はここが `403 Host not in allowlist`。今回は許可済みのはず。通らなければ
       環境の Network access が新セッションに反映されているか確認。
   - `mcp__Higgsfield__media_confirm`(type=image, media_id) で確定
5. `mcp__Higgsfield__generate_image`:
   - model_id: `gpt_image_2`, aspect_ratio: `3:2`, resolution: `2k`, quality: `high`
   - medias: [{ value: <media_id>, role: image }]
   - プロンプト（指示遵守の検証用 = 配置維持・指示書き/補助線/タップ穴は無視・パース修正）:
     下記「生成プロンプト」を使用
6. 結果画像を取得 → `restore_output_image()` で余白を切り戻して元画角へ
7. 原図と並べて「配置維持/文字・補助線除去/パース修正」を評価して報告

### 生成プロンプト（英語推奨）
```
This is a rough background layout drawing (an animation "genzu") for an anime,
drawn in pencil on green paper. Redraw it as a clean, corrected line drawing.
KEEP EXACTLY THE SAME: overall composition and camera angle; position, scale and
depth of every building on left and right; the small gate building and trees in
the center distance; the street receding to the central vanishing point.
FIX: straighten perspective so all edges converge to one vanishing point; correct
the proportions/details of the traditional East-Asian street architecture.
REMOVE/IGNORE completely: all handwritten text and notes (titles, "BG", numbers,
TIME); the black registration tap-hole marks at top; frame border lines and thin
perspective guide lines; any margin markings.
Output: a clean corrected line drawing of the street scene only, no text, no marks.
```

## 確認済みの環境メモ
- Higgsfield 残高: ~6153 credits / plan creator
- GPT Image 2: 入力画像(編集)可 / 比率は 1:1,4:3,3:4,16:9,9:16,3:2,2:3 / 解像度 1k,2k,4k / 品質 low,med,high
- MCP は許可リスト不要（Anthropic経由）。直接 egress（PUT）は環境の Network access に依存。
- PDF添付は /root/.claude/uploads に保存されるが、画像のチャット貼付は保存されない
  → 画像は Google Drive 経由で受け渡す。

## 次フェーズ（お試し成功後）
- 香盤表 .xlsx 入手 → パーサ（カット番号レンジ展開・欠番除外・場所抽出）
- 「場所名→美術ボード」対応表フォーマット
- 原図理解(GPT) v1 の観点JSON
- 本番: Higgsfield CLI 呼び出しラッパ / 300カットバッチ（途中再開・リテイク最大3）
