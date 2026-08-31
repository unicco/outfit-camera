#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/coordinate-recorder}"
TARGET_ENV_FILE="${TARGET_ENV_FILE:-$PROJECT_ROOT/.env}"
SSH_USER="${SSH_USER:-unicco}"
# LAN_CIDRS = ufw が SSH/サービスポートを許可する LAN サブネット。**スペース区切りで複数**。
# ⚠️ **実際のサブネットと違うと LAN 全 TCP が drop されてロックアウトする。**Tailscale が
# 同時に落ちると物理復旧しか手段が無くなる（docs/operations/pi-security-hardening.md）。
# 引っ越し等でルーターのサブネットが変わったら必ず更新する。
# 別ネットワークで実行するときは LAN_CIDRS="..." で上書きする。
#
# 複数を受けるのは、Pi を持ち出すあいだ**自宅と持ち出し先の両方を許す**必要があるため。
# ⚠️ ICMP は既定で許可されるので、外した帯からは **ping は通るのに TCP が全部落ちる**。
LAN_CIDRS_GIVEN="${LAN_CIDRS:-}"
# ⚠️ 旧名で呼ばれても黙って既定へ落とさない。落とすと指定したはずの帯が許可されない
LAN_CIDRS="${LAN_CIDRS:-${LAN_CIDR:-192.168.1.0/24}}"
TS_CIDR="${TS_CIDR:-100.64.0.0/10}"

if [ -n "${LAN_CIDR:-}" ]; then
  if [ -n "$LAN_CIDRS_GIVEN" ]; then
    echo "⚠️ LAN_CIDRS があるので LAN_CIDR='${LAN_CIDR}' は無視します" >&2
  else
    echo "⚠️ LAN_CIDR は LAN_CIDRS に変わりました（スペース区切りで複数書けます）" >&2
  fi
fi

# 🚨 **検証は `ufw --force reset` より前で終わらせる。** reset は ufw を*無効*にする。
# そこから先で `set -e` に落ちると `ufw --force enable` に届かず、**フィルタが全部
# 外れた状態**で放置される。ufw に値を渡してから直すのでは手遅れ。
# ⚠️ **裸の `$LAN_CIDRS` で分割しない。** 単語分割と一緒にパス名展開まで走るので、
# `*` を含む値がカレントディレクトリのファイル名に化けて allow ルールになる。
# `read -a` は IFS で切るだけでグロブを踏まない
read -r -a LAN_CIDR_LIST <<<"$LAN_CIDRS"
if [ "${#LAN_CIDR_LIST[@]}" -eq 0 ]; then
  echo "ERROR: LAN_CIDRS が空です。許可する LAN が 1 つも無くなります" >&2
  exit 1
fi

CIDR_OCTET='(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])'
CIDR_RE="^${CIDR_OCTET}(\.${CIDR_OCTET}){3}/(3[0-2]|[12][0-9]|[0-9])$"
for cidr in "${LAN_CIDR_LIST[@]}"; do
  if ! printf '%s' "$cidr" | grep -qE "$CIDR_RE"; then
    echo "ERROR: LAN_CIDRS の '${cidr}' が CIDR の形をしていません" >&2
    exit 1
  fi
  # /0〜/7 は打ち間違いでしか出てこない広さ（/8 でも 1,600 万台）。
  # ⚠️ 単一の帯だったころは間違えれば即座に繋がらなくなって気づけたが、
  # 複数にすると**片方が生きているせいで気づけない**
  if [ "${cidr#*/}" -lt 8 ]; then
    echo "ERROR: LAN_CIDRS の '${cidr}' が広すぎます（/8 以上にしてください）" >&2
    exit 1
  fi
done

cd "$PROJECT_ROOT"

if [ -f "$TARGET_ENV_FILE" ]; then
  chmod 600 "$TARGET_ENV_FILE"
fi

if [ -f "$HOME/.ssh/authorized_keys" ]; then
  awk '!seen[$0]++' "$HOME/.ssh/authorized_keys" > "$HOME/.ssh/authorized_keys.new"
  mv "$HOME/.ssh/authorized_keys.new" "$HOME/.ssh/authorized_keys"
  chmod 600 "$HOME/.ssh/authorized_keys"
fi

set_kv() {
  local key="$1" value="$2"
  if sudo grep -qiE "^[#[:space:]]*${key}[[:space:]]+" /etc/ssh/sshd_config; then
    sudo sed -i -E "s|^[#[:space:]]*${key}[[:space:]]+.*|${key} ${value}|I" /etc/ssh/sshd_config
  else
    echo "${key} ${value}" | sudo tee -a /etc/ssh/sshd_config >/dev/null
  fi
}

set_kv "PermitRootLogin" "no"
set_kv "PubkeyAuthentication" "yes"
set_kv "PasswordAuthentication" "no"
set_kv "MaxAuthTries" "3"

if sudo grep -qiE "^[#[:space:]]*AllowUsers[[:space:]]+" /etc/ssh/sshd_config; then
  if ! sudo grep -qiE "^[#[:space:]]*AllowUsers[[:space:]].*\b${SSH_USER}\b" /etc/ssh/sshd_config; then
    sudo sed -i -E "s|^[#[:space:]]*AllowUsers[[:space:]]+.*|& ${SSH_USER}|I" /etc/ssh/sshd_config
  fi
else
  echo "AllowUsers ${SSH_USER}" | sudo tee -a /etc/ssh/sshd_config >/dev/null
fi

sudo sshd -t
sudo systemctl reload ssh || sudo systemctl reload sshd

if ! command -v ufw >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y ufw
fi

sudo ufw --force reset
sudo ufw default deny incoming
sudo ufw default allow outgoing

sudo ufw allow from "$TS_CIDR" to any port 22 proto tcp

for cidr in "${LAN_CIDR_LIST[@]}"; do
  sudo ufw allow from "$cidr" to any port 22 proto tcp
  for port in 3000 8000 8001 3100; do
    sudo ufw allow from "$cidr" to any port "$port" proto tcp
  done
done

sudo ufw --force enable

echo "=== hardening summary ==="
# ⚠️ **ここを読んでから帰る。**冒頭の `ufw --force reset` で手で足したルールは消えている
echo "許可した LAN: ${LAN_CIDR_LIST[*]}"
stat -c "%a %U:%G %n" "$TARGET_ENV_FILE" "$HOME/.ssh/authorized_keys" 2>/dev/null || true
sudo grep -nE "^(AllowUsers|PermitRootLogin|PasswordAuthentication|PubkeyAuthentication|MaxAuthTries)" /etc/ssh/sshd_config
sudo ufw status verbose
