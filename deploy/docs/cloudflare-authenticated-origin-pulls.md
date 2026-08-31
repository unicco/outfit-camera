# Cloudflare Authenticated Origin Pulls（mTLS・多層防御 Layer 2）

オリジン(ConoHa VPS)が **Cloudflare の提示するクライアント証明書を検証**し、自ゾーンの Cloudflare を経由しないオリジン直アクセスを **TLS ハンドシェイク段階で遮断**する。Layer 1（IP レンジ制限）を暗号的に補強し、多層防御を完成させる。

- 対応設定: [`deploy/caddy/coordinate.caddy`](../caddy/coordinate.caddy) の `tls` ブロック（`import /etc/caddy/aop.d/*.caddy`）

## なぜ必要か（Layer 1 の限界）

Layer 1（`cloudflare-ingress-firewall.md`）は公開 `80/443` を Cloudflare の公開 IP レンジのみに許可するが、**同レンジは全 Cloudflare 顧客が共有**する。したがって「Cloudflare を経由した」ことは保証できても「**自ゾーンの設定（Access）を経由した**」ことまでは保証できない（他ゾーン経由の迂回が原理的に可能）。

per-hostname Authenticated Origin Pulls は、**自分だけが持つ CA が発行したクライアント証明書**を Cloudflare がオリジンに提示し、オリジンがそれを検証する。これにより「自ゾーンの Cloudflare を経由した」ことを暗号的に証明でき、迂回を封じる。

## 仕組み・スコープ（存在ゲート方式で auto-deploy 安全）

- 適用対象は **公開ブロック `coordinate.unicco.app :443`（`coordinate.caddy`）のみ**。
- **enforcement は `/etc/caddy/aop.d/client-auth.caddy` の存在で切り替わる**。
  - このスニペットが**無い**うちは `coordinate.caddy` の `import /etc/caddy/aop.d/*.caddy` が空展開され、**証明書のみ（mTLS なし）**。`deploy-vps.yml` → `setup-vps.sh` が本ファイルを毎デプロイ再配置しても**公開は断たれない**。
  - CF 側の準備が整ってから、**人間がスニペットを作成して初めて enforce** される（下記 手順5）。future の auto-deploy は `aop.d/` を触らないため enforcement は維持される。
- **影響を受けない経路**（意図的に対象外）:
  - `coordinate-tailscale.caddy :3000`（Pi キオスクブラウザ・`tls` 自体なし）
  - Pi カメラのアップロード（`BACKEND_API_URL` = VPS の Tailscale IP・公開 443 を通らない）
  - morning-brief 等の内部クライアント
  - これらは Tailscale ネットワーク分離で保護される。mTLS は公開経路の証明であり、内部経路には掛けない。
- per-hostname AOP は zone-level / global AOP と独立。全 Cloudflare プラン（Free 含む）で利用可。

> **秘密鍵の扱い**: CA 鍵・leaf 鍵は**各ホスト上で人間が生成・管理**し、AI・チャット・履歴に残さない（`30_System/secrets-rotation.md` 準拠）。leaf の秘密鍵のみ Cloudflare にアップロードする。CA の秘密鍵はローテーション用にオフラインで厳重保管する。API 応答は**値を出力せずステータス/ID のみ**確認する。

## 手順 0: 準備

```bash
# Caddy が trust_pool 構文（v2.8+）に対応しているか事前確認。未満なら更新するか、
# スニペットの trust_pool file 行を旧構文 trusted_ca_cert_file に読み替える。
caddy version

# CF API トークン（origin_tls_client_auth 編集権限を含む Zone スコープ）と Zone ID。
# 先頭スペースで履歴回避（HISTCONTROL=ignorespace 前提）。
 export CF_API_TOKEN='<token>'
 export ZONE_ID='<coordinate.unicco.app の zone id>'
```

作業マシン（ローカル or VPS）で `openssl` / `jq` / `curl` が使えること。

## 手順 1: CA と leaf 証明書を生成（人間・秘密鍵は手元管理）

```bash
# 1-1. 独自 CA（この鍵で将来の leaf を再発行できる。オフライン厳重保管）
openssl genrsa -out aop-ca-key.pem 2048
openssl req -x509 -new -nodes -key aop-ca-key.pem -sha256 -days 3650 \
  -out aop-ca-cert.pem -subj "/CN=coordinate-aop-ca"

# 1-2. leaf 証明書（CF に提示させる。CA で署名）
openssl genrsa -out aop-leaf-key.pem 2048
openssl req -new -key aop-leaf-key.pem -out aop-leaf.csr \
  -subj "/CN=coordinate-origin-aop"
openssl x509 -req -in aop-leaf.csr -CA aop-ca-cert.pem -CAkey aop-ca-key.pem \
  -CAcreateserial -out aop-leaf-cert.pem -days 3650 -sha256
```

生成物:
- `aop-ca-cert.pem` … CA 公開証明書 → **オリジン(Caddy)が信頼する**（手順 4）
- `aop-ca-key.pem` … CA 秘密鍵 → **オフライン保管**（ローテーション用・どこにも配置しない）
- `aop-leaf-cert.pem` / `aop-leaf-key.pem` … leaf 証明書＋鍵 → **Cloudflare にアップロード**（手順 2）

## 手順 2: leaf 証明書を Cloudflare にアップロード（応答は ID のみ確認）

```bash
# 応答本文には private_key がエコーされうるため、画面に出さず id/success のみ抽出する。
resp=$(curl -sS -X POST \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/origin_tls_client_auth/hostnames/certificates" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data @- <<JSON
{
  "certificate": "$(awk 'BEGIN{ORS="\\n"}1' aop-leaf-cert.pem)",
  "private_key": "$(awk 'BEGIN{ORS="\\n"}1' aop-leaf-key.pem)",
  "bundle_method": "ubiquitous"
}
JSON
)
export CERT_ID=$(printf '%s' "$resp" | jq -r '.result.id')
printf 'success=%s cert_id=%s\n' "$(printf '%s' "$resp" | jq -r '.success')" "$CERT_ID"
unset resp   # 応答（private_key を含みうる）を残さない
```

> ⚠️ アップロードするのは **leaf 証明書**（`aop-leaf-cert.pem`）。root CA を送ると `missing leaf certificate` エラーになる。`success=true` と `cert_id` が得られたか確認する。

## 手順 3: hostname に per-hostname AOP を有効化

```bash
curl -sS -o /dev/null -w 'http=%{http_code}\n' -X PUT \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/origin_tls_client_auth/hostnames" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data @- <<JSON
{
  "config": [
    { "hostname": "coordinate.unicco.app", "cert_id": "${CERT_ID}", "enabled": true }
  ]
}
JSON
```

この時点で Cloudflare は `coordinate.unicco.app` へのオリジン接続時に leaf 証明書を提示する（オリジンはまだ検証していないので無害）。

> ⏳ **エッジ伝播を待つ**。per-hostname 設定が全 PoP に行き渡るまで数分かかりうる。行き渡る前にオリジンで enforce すると、未反映 PoP 経由のリクエストがハンドシェイク失敗（地域限定の一時断）になる。**数分待ってから**手順 5 に進み、待機中に `https://coordinate.unicco.app` が引き続き正常なことをブラウザで確認する。

## 手順 4: オリジン(VPS)に CA 証明書を配置

`ssh conoha` で入り、CA 公開証明書を Caddy が読める場所に置く（**秘密鍵ではなく `aop-ca-cert.pem`**）。

```bash
# aop-ca-cert.pem を VPS に転送済として
sudo install -m 644 -o root -g root aop-ca-cert.pem /etc/caddy/certs/cloudflare-aop-ca.pem
```

この時点でもまだ enforce されない（スニペット未作成のため import は空）。

## 手順 5: mTLS を enforce（スニペット作成・validate → reload）

> 別ターミナルの `ssh conoha` を開いたまま作業する（ロックアウト時の復旧用）。
> **coordinate.caddy 自体は編集しない**（auto-deploy で上書きされるため）。enforce は
> `aop.d` スニペットの作成で行い、これは auto-deploy が触らないので維持される。

```bash
sudo mkdir -p /etc/caddy/aop.d
sudo tee /etc/caddy/aop.d/client-auth.caddy >/dev/null <<'CADDY'
client_auth {
	mode require_and_verify
	trust_pool file /etc/caddy/certs/cloudflare-aop-ca.pem
}
CADDY

# CA ファイル欠落や文法エラーはここで落ちる → reload されない（既存設定を維持）
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl reload caddy
```

## 手順 6: 検証（値を出力しない）

```bash
# (a) Cloudflare 経由の実ユーザー → 引き続き 200
#     ブラウザで https://coordinate.unicco.app を開き、UI/API/カメラが動くか目視。

# (b) CF を経由しない直アクセス → TLS ハンドシェイク拒否（= enforce 成功）
#     VPS 上から localhost の Caddy に SNI 付きで直接叩く（Layer1 firewall を迂回して
#     TLS 層のみ検証する）。クライアント証明書がないのでハンドシェイクが失敗するはず。
curl -sS -o /dev/null -w '%{http_code}\n' --max-time 5 \
  --resolve coordinate.unicco.app:443:127.0.0.1 \
  https://coordinate.unicco.app/health
#   → 期待: curl: (35/58) SSL/handshake エラーで失敗（HTTP コードが返らない）
#     もし 200 が返る場合、mTLS が効いていない（設定/CA を再確認）。
```

## ロールバック（enforce を即解除）

公開が意図せず断たれた場合、スニペットを削除して即復旧する（`coordinate.caddy` は触らない）。

```bash
sudo rm -f /etc/caddy/aop.d/client-auth.caddy
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl reload caddy
```

CF 側の per-hostname AOP は残っていても、オリジンが検証しなければ無害（CF は証明書を提示するだけ）。恒久的に無効化するなら手順 3 を `"enabled": false` で再実行する。

## ローテーション

`30_System/secrets-rotation.md` のチェックリストに従う。

- **leaf 証明書の更新（期限切れ前・CA は据え置き）**: 手順 1-2 で同じ CA から新しい leaf を発行 → 手順 2 で再アップロード（新 `cert_id`）→ 手順 3 で hostname を新 `cert_id` に張り替え。**オリジン側は CA が同じなので無変更**。
- **CA ごと更新**: 新 CA を生成 → `/etc/caddy/certs/cloudflare-aop-ca.pem` を新旧連結（`trust_pool file` は複数 PEM を許容）→ 新 CA の leaf を発行・切替 → 検証後に旧 CA を除去。

## 保証範囲と残リスク

- **経路認証であり、単体でユーザー認証ではない**。mTLS は「自ゾーンの Cloudflare を経由した」ことを保証する。**エンドユーザーの認証は上流の Cloudflare Access が担う**。したがって Layer 2 の効果は「全 ingress hostname に Access ポリシーが適用されていること」が前提。
  - 要人間確認: `coordinate.` / `api.` / `app.` / `camera.` の全 hostname に Access ポリシー（許可メール）が適用済か（`cloudflare-ingress-firewall.md` の「残タスク」と同じ）。1 つでも未適用なら、mTLS を通せた誰でも該当サービスに到達しうる。
- **Pi 経路（Tailscale）は本 Layer の対象外**。Pi は公開 443 を通らないため mTLS の保護外だが、Tailscale ネットワーク分離で守られる。Pi 経路にアプリ層認証を掛けると本番のカメラ取込が壊れるため、意図的に据え置く（`` の残リスク方針を継承）。
- **CA 秘密鍵の保管が要**。`aop-ca-key.pem` が漏れると攻撃者が有効な leaf を発行できる。オフラインで厳重保管する。
- Layer 1（firewall）と併用が前提。Layer 2 は迂回を暗号的に封じるが、Layer 1 は攻撃面（オリジン直到達の試行自体）を縮小する。両者は代替でなく併用。
