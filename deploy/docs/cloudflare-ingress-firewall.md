# Cloudflare-only ingress firewall（多層防御 Layer 1）

オリジン(ConoHa VPS)への公開 `80/443` を **Cloudflare の公開 IP レンジからのみ**許可し、CF を経由しないオリジン IP 直叩きを塞ぐ。全公開トラフィックを Cloudflare 経由に強制する多層防御の第 1 層（**単体では不十分・Layer 2 と併用が前提**。下記「保証範囲」参照）。

- 対応スクリプト: [`deploy/scripts/setup-firewall.sh`](../scripts/setup-firewall.sh)

## なぜ必要か

本番は Caddy + Cloudflare Origin 証明書で稼働し、認証は**エッジの Cloudflare Access に全面依存**している（オリジンに再検証がない）。UFW が `80/443` を Anywhere に開けているため、Cloudflare を経由しない直接リクエストがオリジンに到達しうる。オリジンはリクエストが Cloudflare Access を通過したことを検証していないため、エッジ認証が実質的に無効化される。

Layer 1 は **公開トラフィックを必ず Cloudflare 経由に強制する**ことでこの経路を塞ぐ。

### ⚠️ Layer 1 の保証範囲（重要・単体では不十分）

CF 公開レンジ許可は「Cloudflare を**経由**したこと」までしか保証しない。**同じ IP レンジは Cloudflare の全顧客が共有する**ため、自ゾーンの Access ポリシーを経由していないトラフィック（他ゾーン経由等）も、送信元 IP としてはこのレンジ許可を通過しうる。

つまり Layer 1 は「Cloudflare を通ったこと」は保証するが「**自ゾーンの Access ポリシーを通過したこと**」までは保証しない。**完全に迂回を封じるにはオリジン側の検証（Layer 2）が必須**:

- **Authenticated Origin Pulls（mTLS）** — Cloudflare が提示するクライアント証明書をオリジンで検証。自ゾーンのカスタム証明書を使えばアカウント単位で束縛できる
- または **オリジン側での Cloudflare Access JWT 署名検証**（`Cf-Access-Jwt-Assertion` を `<team>.cloudflareaccess.com` の公開鍵で検証）
- または Cloudflare 側で注入する**シークレットヘッダ**をオリジンで検証

Layer 2 は別 Issue の follow-up とする（下記「設計判断」参照）。Layer 1 は**攻撃面を大幅に縮小する必要条件**であり、Layer 2 と併用して初めて迂回が完全に塞がる。

## 設計判断

- **Layer 1（本スクリプト）のみを対象にした**。素朴なオリジン直アクセス（CF を経由しない到達）を塞ぎ、攻撃面を大幅に縮小する。App 層に触れないので現行動作を壊さない。
- ただし上記「保証範囲」の通り Layer 1 単体では不十分。**完全遮断には Layer 2（Authenticated Origin Pulls / オリジン側 Access JWT 検証）が必須**。Layer 2 は `ENVIRONMENT=production` 相当の有効化や TLS 設定変更が絡み現行運用（UI / Pi アップロード / morning-brief）を壊すリスクがあるため、影響を検証してから別 Issue で実施する。
- 段階導入する理由: Layer 1 は現行動作を壊さず即日入れられ攻撃面を縮小する。Layer 2 は破壊的変更の検証が必要なので分離する。両者は代替でなく併用。
- **auto-deploy（`setup-vps.sh`）には組み込まない**。毎デプロイでの UFW 変更はロックアウト事故のリスクがあるため、本スクリプトは人間が一度だけ手動で流す運用にする。

## 実行手順

VPS 上で実行する（`ssh conoha`）。

```bash
cd ~/services/coordinate-recorder
git pull

# 1. まず dry-run で実行内容を確認（変更なし）
#    冒頭に現在 listen 中のポート一覧が出るので、SSH(22)/Tailscale/80/443 以外に
#    外部公開が必要なポート（同居する life-log 等）がないか必ず目視確認する。
bash deploy/scripts/setup-firewall.sh

# 2. 問題なければ実適用（root 必須）
sudo bash deploy/scripts/setup-firewall.sh --apply

# 3. 結果確認
sudo ufw status verbose
```

> ⚠️ **この VPS は life-log 等と同居している。** `default deny incoming` を適用すると、
> スクリプトが許可する SSH / Tailscale / 80 / 443 以外の公開ポートは締め出される。
> dry-run 冒頭の `ss -tlnp` 出力で、他サービスが外部公開しているポートがないか必ず確認すること。
> 必要なら適用前にスクリプトへ許可ルールを追記する。

### スクリプトの挙動

- Cloudflare の現在の IP レンジを `https://www.cloudflare.com/ips-v4` / `ips-v6` から取得
- **ロックアウト防止**: `tailscale0` インターフェースを許可し、既存の SSH 許可ルールは削除しない。管理 SSH は Tailscale 経由（`ssh conoha`）を前提とし、**公開 SSH(`22/tcp`) は既定で追加しない**（既存の SSH 露出を広げない）。Tailscale を使わず公開 SSH が必要な場合のみ `sudo ALLOW_PUBLIC_SSH=true bash deploy/scripts/setup-firewall.sh --apply` で opt-in（`sudo` は既定で環境変数をリセットするため、変数は `sudo` の**後ろ**に置くこと）
- **egress 非改変**: `default deny incoming` のみ設定し、outgoing ポリシーには触れない（既存の egress 制御を弱めない）
- 既存の `cf-ingress-web` ルールを削除してから現在の CF レンジで貼り直す（**冪等**）
- `80/443` を CF レンジのみ許可、Anywhere の広域 80/443 ルールを**番号指定で**撤去（`--force`）、`default deny incoming`
- **フェイルセーフ**: CF レンジの取得に失敗（IPv4/IPv6 いずれかが 0 件）したら何も変更せず中断（空の許可リストで自分を締め出さない）
- **事後検証（送信元照合方式・コメント非依存）**: 適用後にオリジンへの inbound を許してよいのは **(1) 送信元が実際に Cloudflare CIDR かつ宛先が `80/443`（web） (2) SSH（`22/tcp` または `OpenSSH` プロファイル） (3) Tailscale インターフェース (4) `EXTRA_ALLOW_EXEMPT_RE` で明示除外したもの** のいずれか。判定は各ルールの**送信元・宛先カラムを突き合わせて**行い、コメント文字列やポート表記（数値/アプリプロファイル）を一切信頼しない（コメントは照合前に除去）。これにより `# cf-ingress-web` を騙る偽装 broad ルール・特定 IP 直許可・アプリプロファイル開放・`5432/tcp ALLOW IN <CF CIDR>` のような非 web ポート露出をすべて漏れなく捕捉し、1 つでも残れば `ERROR` で停止する。数値 `80/443` の `Anywhere` は自動撤去するが、特定 IP 直許可・アプリプロファイル形式は誤削除防止のため自動削除せず検出で停止し人間が判断する

### 影響がないことの確認済事項

- **Pi のアップロード**: `BACKEND_API_URL`（Tailscale 経由）で到達するため、公開 `443` の制限を受けない
- **auto-deploy の SSH**: Tailscale SSH 経由（`tailscale0` を許可済）
- **Caddy `/camera/` プロキシ**: Pi へは Tailscale IP 直で到達するため影響なし

## CF レンジ更新時の再実行

Cloudflare の IP レンジが変わったら、同じコマンドを再実行するだけで最新レンジに貼り直される（冪等）。定期的（例: 四半期）に流すか、Cloudflare のレンジ変更告知時に実行する。

## ⚠️ 残タスク（人間・Cloudflare ダッシュボード）

このスクリプトは「Cloudflare を必ず経由させる」ことしか保証しない。**Cloudflare Access のポリシー自体**が全 ingress hostname に適用されているかは別途ダッシュボードで確認する必要がある。

- 対象: `coordinate.` / `api.` / `app.` / `camera.` の全 hostname
- 確認: 各 hostname に Access ポリシー（許可メール）が実際に適用されているか
- **1 つでも未適用なら**、Cloudflare は通すが認証なしで素通しになるため、該当サービスが引き続き無防備になる
