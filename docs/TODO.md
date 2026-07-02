# TODO — 原図修正自動化（尚善 ep7）

最終更新: 2026-07-02（全体構造レビュー反映。根拠の詳細= `docs/code-review-2026-06.md`）
トランク=main。新セッションは main から。可変状況は `docs/sessions.md`。

## 🎯 ゴール
ep7 の 245カット/217原図を、コンソール上で「夜間に一括生成 → 朝に自動QCフラグつきで検品 →
指示付きリテイク」のループで完走させる。その後 ep8/他作品へ展開。

---

## 0. 事故防止の改修（機能より先に。詳細は code-review §A/B）
- [ ] server.py: STATE 変更をロック内に統一＋state保存のアトミック化＋読込フォールバック
      （console_state.json 破損→起動不能の芽を摘む）
- [ ] server.py: 生成失敗時に status を戻す／DL・CLI に timeout／running リセット導線
- [ ] batch/server: ledger の書き先を `<out>/ledger.jsonl` へ（git 管理の runs/ に直接追記しない）
- [ ] `_genzu_preview`: PSD mtime 比較＋ソース別ファイル名（Photoshop往復で古い絵が出る問題）
- [ ] cli.py: 既定を確定前提（切らない/Base）に統一するか廃止（batch と真逆のまま危険）

## S. 完走に直結する機能
- [ ] **S1 一括/並列生成**: 複数選択・「未生成を全部回す」・同時数上限(~8)・キュー・完了/失敗通知
- [ ] **S2 冪等バッチ**: 既生成スキップ／失敗のみリトライ（バックオフ）／途中再開（再実行=全額再課金を根絶）
- [ ] **S3 QC自動フラグの配線**: 生成完了時に qc.evaluate→ledger.qc 記録→コンソールカードに⚠。
      vision判定（人物残り等）は共通クライアント経由で自動化。OK/要修正も ledger に反映
- [ ] **S4 situation/remove の充足**: `prompt gen-info` を全担当245カットへ →
      **conte merge2（v2→cut_scene_info ブリッジ実装）** → EN対訳化。素材(conte_v2)は揃っている
- [ ] **S5 テイク履歴**: take_NN/ 保存・過去テイク切替・採用。上書き事故をなくす

## A. 品質・運用効率
- [ ] レイヤー手動オーバーライドUI（export_with_overrides 済み・モーダルに一覧選択を配線するだけ）
- [ ] 指示付きリテイク（要修正コメント→記録→次回プロンプト[CUT]末尾へ反映）
- [ ] コスト記録・可視化（cost_credits 自動記入・累計と完走見積をヘッダ表示）→ S1の予算ガード
- [ ] PSD無し7カット（星空/回想/イメージ）の方針決定→「対象外」状態を追加 ※ユーザー判断
- [ ] aspect 固定ルールの決定・強制（16:9/3:2 混在の根絶） ※ユーザー判断

## B. 基盤整理（並行して少しずつ）
- [ ] 共通化: `resolve.py`（cut→PSD解決×3実装を統合）／`anthropic_client.py`
      （REST×4実装: retry+timeout+画像縮小+JSON抽出を統一）／カット番号正規化×3
- [ ] pyproject.toml で `pip install -e .`（PYTHONPATH ハック恒久解消）＋ pytest 化
      （image_aspect ラウンドトリップ／psd_export レイヤー選択／prompt 3層／conte 突合の単体テスト）
- [ ] scene_understanding: バッチドライバ＋cut_scene_info への書き戻し＋アラートのコンソール表示
- [ ] ep8展開の脱ハードコード: プロジェクト設定JSON化＋香盤表→cut_board_map 生成ツール
- [ ] server.py PAGE / perspective_editor の HTML/JS を static/ へ分離

## C. 衛生（30分でできる系）
- [ ] handoff/ep7 の PNG 51MB を git rm（役目完了。今後は LFS or 都度削除）＋ gather にサイズ警告
- [ ] 旧CSV削除/archive（ep7_cut_board_map / cut_index.example / genzu_index の一本化）＋ runs/README.md
- [ ] conte_v2 変種整理（baseline=reocr はバイト同一→片方削除、overrides 空の扱い明記）
- [ ] work/conte_crops の git rm --cached（gitignore 矛盾解消）
- [ ] run_console.bat の ASCII 化・BOARDS/OUT 存在チェック／run_gather.bat の識別子ハードコード撤去
- [ ] docs 更新: NEXT-SESSION.md を archive／runbook のコンソール節を現UIに／sessions.md に
      wonderful-allen(パース系)を追記／CLAUDE.md 索引に perspective・conte ツールを追加
- [ ] 統合済みブランチの整理／死にコード削除（batch.build_prompt, dashboard.py の扱い明記）
- [ ] 束カット=離散を docs に明文化（naming.py の古いコメント更新）

## 未決（ユーザー判断待ち）
- ボード2枚入力の本採用（機構は実装済み・方針のみ）／cut240 のボード正誤／aspect 固定値／
  PSD無し7カットの扱い／perspective系（自動推定・エディタ・UXP）の位置づけ

---

### 推奨着手順
**0（事故防止）→ S1+S2+コスト → S3（自動QC）→ S4（CUT層充足）→ S5 → A のレイヤーUI/指示付きリテイク**。
この順で「夜間一括→朝検品→リテイク」のループが閉じ、245カット完走が現実的になる。
