# CLAUDE.md — 尚善 原図修正自動化（全セッション共通）

このファイルはどのセッションでも自動で読まれる。**会話の記憶はセッション間で共有されない**ので、
事実は必ず git 上のファイルに書く。迷ったらまず下の索引を読む。

## 0. セッション間の鉄則（最重要）
- **トランクは `main`**。新セッションは `main` から始める（全部入り＝コンソール＋プロンプト＋コンテ）。
  作業は各セッションの feature ブランチで行い、まとまったら `main` へマージする。
- 並行する別セッションは**別コンテナ・別履歴**。互いの思考や経緯は一切見えない。
  「さっき決めた通り」は伝わらない。**ファイル＝唯一の事実**。
- 作業の前後で:
  1. **始める前に `git pull`**（相手の成果を取り込む）。該当ブランチは `docs/sessions.md`。
  2. **決めた方針・手順は docs/ に書く**（口頭でなく文書化）。再発明を止める。
  3. **成果はこまめに commit/push**。差分が記録になる。
- 別セッションに渡すときは「考えて」ではなく**「この手順をなぞって」**（該当 md / skill を指す）。
- 繰り返す共通ルールはこの CLAUDE.md に追記する（毎回説明し直さない）。

## 1. これは何のプロジェクトか
商用アニメ「尚善」の**背景原図(genzu)PSD** を、GPT Image 2(Higgsfield)で**白黒線画ドラフト**に
変換し、PSDへ「AI原図修正」レイヤーとして戻すパイプライン。ep7 で **245カット/217原図**。
- **登場人物/話の概要**は `runs/ep_overview.json`（コンソール上部にも表示）。

## 2. どこに何があるか（索引）
| 種類 | 場所 |
|---|---|
| パイプライン本体 | `src/genzu_fix/`（`psd_export` `image_aspect` `frame` `batch` `prompt` `server`） |
| パース注釈（アイレベル/消失点/キャラ垂直線） | `src/genzu_fix/perspective.py` ／ ラッパ `scripts/draw_perspective.py`（vision/cv/hybrid 比較） |
| パース編集エディタ(Flask/キャンバス) | `src/genzu_fix/perspective_editor.py` ／ 起動は `run_perspective_editor.bat` / `run_perspective_editor.py`（手置き＋自動推定でパース線） |
| 作業コンソール(Flask) | `src/genzu_fix/server.py` ／ 起動は `run_console.bat` / `run_console.py` |
| カット表・索引 | `runs/cut_board_map_ep7.csv`(245行/217原図) `runs/genzu_index_ep7.csv` |
| 話数概要 | `runs/ep_overview.json` |
| ロードマップ/現在地 | `docs/roadmap-genzu-prompt.md`（3観点→統合→プロンプトの進捗と次の一手） |
| 設計ノート | `docs/design-notes.md`（§20=レジスト解決の根拠） |
| プロンプト設計 | `docs/prompt-design.md` ＋ `runs/scene_profiles/`（great-edison主管） |
| コンテOCRの全体像/判断 | `docs/conte-ocr-overview.md`（パイプライン・列幾何・verifyの読み方） |
| 受け渡し依頼/回答 | `runs/handoff_DATA_README.md` `docs/handoff-prompt-design.md` |
| ローカル実行手順 | `docs/local-cli-runbook.md` |
| TODO | `docs/TODO.md` |
| セッション台帳（誰が何を/ブランチ/決定） | `docs/sessions.md` |
| スキル（再利用手順） | `.claude/skills/`（例 `read-genzu`） |

## 3. 確定した技術前提（解釈し直さない）
- **レジストずれは解決済み**: 入力=出力グリッド（GPT出力寸に合わせて入力を作る）。`design-notes §20.6`。
  ずれて見えるのは生成の描き直し由来。**原図をフレームで切らない**のが既定（ヘッダはプロンプトで除去）。
- **原図の取り出し** = `psd_export.export_background_layer`(背景のみ=Base, 既定) /
  `export_visible_to_png`(見たまま)。レイヤー選択は **BG→LO→背景**。指示/セル参考/Camera等は除外。
- **コンソールも別セッションの原図取り出しも同じ関数**を使う（→ `/read-genzu`）。
- 生成は **Higgsfield 公式CLI**（`gpt_image_2` / 2k / high）。最終結果は `restored_full.png`（原図画角）。

## 4. よくある作業の入口
- **原図を見たい/読みたい** → スキル `/read-genzu`。`python scripts/render_genzu.py <cut> --genzu-dir <00.原図>`。
  PSDはバイナリでRead不可→必ずPNG化。コンソールと1:1で同じ絵が出る。
- **コンソールで作業** → `run_console.bat`（PYTHONPATH不要。原図=`..\00.原図`, 出力=`..\10.生成結果` 既定）。
- **一括生成(担当別)** → `python -m genzu_fix.batch --genzu-dir <dir> --assignee <名>`（runbook参照）。
- **原図/コンテをgitで配る**（PSDアクセスが無い相手向けの代替） → `scripts/gather_handoff_ep7.py`。
  PSDが手元にあるなら不要。
- **画像にパース線を引く（アイレベル/消失点/キャラ垂直線）** → `python scripts/draw_perspective.py <画像>`。
  3手法を比較できる: `cv`(numpyのみ・決定的・人物識別不可) / `vision`(Claude・ラフ線に強い) /
  `hybrid`(Visionのキャラ＋CVで消失点を最小二乗精密化)。既定 `--method all` で
  `work/_perspective/<stem>/` に各オーバーレイPNG＋JSON＋`compare.png` を出す。
  vision/hybrid は `ANTHROPIC_API_KEY` が要る（cv は不要）。
- **パースを手で詰める/直す（エディタ）** → `python run_perspective_editor.py`（既定 :8770）。
  「ファイルを開く…」(ブラウザの `<input type=file>`) か画像のドラッグ&ドロップで開く
  （どちらも内部で `/api/upload`→`work/_uploads` に保存しサーバ側パスを得る＝自動推定/保存に使う）。
  アイレベル・消失点をドラッグで配置すると消失点へ収束するパースガイドを自動描画
  （1点〜複数消失点＝ジブリ風にも対応、鉛直消失点/人物垂直線も可）。アイレベルを掴んで
  画像の外へカーソルを出すと傾けられる（消失点も連動回転、傾け中は半透明の水平基準線を表示し
  誤差1°未満は自動で水平へ補正）。線の太さ・ガイド密度はスライダ（生成参照用に太め既定）。
  「自動推定(cv/vision/hybrid)」で初期値を流し込み微調整→保存はブラウザのダウンロード:
  「PNG保存」=`/api/render` がフルレゾの焼き込みPNG（太さ・密度を反映）、「JSON保存」=正規化座標。
  **背景がキャラ想定のパースと食い違う時は手置きで正す**。

## 5. 規約
- **src レイアウト**。`python -m genzu_fix.*` には PYTHONPATH=src が要るので、ランチャ
  (`run_*.py/.bat`)か `scripts/*.py`(自前で src を通す)を使う。
- Windows の .bat は**コメント/echoはASCII**（SJISで文字化けするため）。日本語パスは set 値のみ。
- git 識別子が未設定だと commit が失敗する → `git config user.email/user.name` を入れる。
- 一時ファイルは `work/`（.gitignore 除外）。**共有したいものは work/ の外に置く**。
- コミット末尾に `Co-Authored-By:` と `Claude-Session:` を付ける（既存コミット参照）。

> このファイルは「安定した索引と規約」。可変な状況（誰が今何を/ブランチ/未決事項）は
> `docs/sessions.md` に書く。新しい再利用手順を作ったら `.claude/skills/` に置き、ここの索引に足す。
