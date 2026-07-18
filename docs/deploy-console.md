# コンソールのチーム共有 — セットアップ手順（間借り機/ローカル共通）

> 方針（2026-07-18 黒江さん）: GPU不要（生成はHiggsfieldクラウド）。AWSは素材持ち出しと
> Techチーム調整が増えるだけなので使わない。**社内の常時稼働マシン（生成用マシンの間借り）を
> ホストにし、ネットワークは Tailscale**（社内ネットワーク設定に触らない＝Tech調整不要）。
> ローカル（黒江さんPC）でも同じ手順で共有できる（PCが起きている間だけ）。

## 1. ホスト機の準備（1回だけ・30分）
1. **リポジトリ**: `git clone https://github.com/RAIdq222/kazuki-workspace.git` → 以後 `git pull origin main`
2. **Python**: 3.11+ / `pip install flask psd-tools pillow numpy waitress`
   （**waitress必須**＝複数人アクセス用の本番サーバ。無いと開発サーバで警告が出る）
3. **素材**: OneDrive をホスト機にも同期（黒江さんと同じ共有フォルダ）。
   `runs/project_*.json` のパスがホスト機で解決できることを確認
   （パスが違う場合は project json をホスト機のパスに合わせる。git管理なので注意——
   ホスト専用に変える場合は `runs/project_*.local.json` 等のコピー運用を検討）
4. **Higgsfield CLI**: インストール → `higgsfield auth login`（生成に使うアカウントで）
5. **APIキー**: 環境変数 `ANTHROPIC_API_KEY`（検品レポート・staging・パース注入に必要）
6. **共有トークン**: 環境変数 `CONSOLE_TOKEN=<推測されない文字列>`

## 2. 起動
```bat
set CONSOLE_TOKEN=<トークン>
set ANTHROPIC_API_KEY=<キー>
set PYTHONPATH=src
python -m genzu_fix.server --host 0.0.0.0 --port 8765
```
- 常駐化（Windows）: タスクスケジューラ「ログオン時」に上記batを登録（電源設定=スリープ無効）
- `[serve] waitress で 0.0.0.0:8765 待受` と `[auth] 共有トークン認証: 有効` が出ればOK

## 3. ネットワーク（Tailscale・Tech調整不要）
1. https://tailscale.com → チーム用アカウント（無料枠で可）
2. ホスト機とメンバー各PCにTailscaleを入れ、同じテールネットにログイン
3. メンバーへの配布URL: `http://<ホストのTailscale名 or 100.x.x.x>:8765/?token=<トークン>`
   （初回のみtoken付きで開く→以後Cookieで素通し）
- 社内LANだけで良いなら Tailscale 無しで `http://<ホストのLAN IP>:8765/?token=…` でも可
  （その場合はWindowsファイアウォールで8765の受信許可を1つ足す）

## 4. 複数人運用の仕様（v1）
- **判定者の記録**: 初回のOK/要修正時にブラウザが名前を聞く（localStorage保存）。
  判定は「誰が・いつ・何にしたか」が console_state.json に履歴で残り、詳細画面に判定者表示
- **同時編集**: 最後に書いた人が勝ち（判定履歴で追跡可能）。同カットの同時操作は運用で回避
- **生成の権限**: v1は全員可。クレジット誤爆が問題になったら「生成可能ユーザー」制を足す（TODO）
- **セキュリティ前提**: 共有トークン＋Tailscale私設網。インターネットへの直接公開はしない

## 5. トラブルシュート
- 開けない → ホストで起動ログ確認／Tailscale接続確認／token付きURLか確認
- 画像が出ない → ホスト機のOneDrive同期状態（project json のパスが実在するか）
- 生成が失敗 → ホスト機で `higgsfield auth login` し直し（トークン失効）。
  カードの赤帯とコンソールログ `[gen] … 失敗:` に理由が出る
