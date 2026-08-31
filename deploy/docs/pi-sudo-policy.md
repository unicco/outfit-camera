# 玄関 Pi の sudo 方針 — `NOPASSWD: ALL` を狭めない

玄関 Pi の `unicco` は `/etc/sudoers.d/010_pi-nopasswd`（Raspberry Pi OS 標準）で `unicco ALL=(ALL) NOPASSWD: ALL` を持つ。**これを狭めないと決めた。** 細かい許可ファイルは残骸として削除し、方針をここに記録する。

- 判断日: 2026-07-31

## 狭めない理由

### 1. provisioning が root 相当を要求する

`coordinate-git-sync.service` は `User=pi` の oneshot で、**毎起動** `origin/main` へ `reset --hard` した後に `deploy/setup-pi.sh --provision-only` を走らせる。この中で次を実施する。

- `sudo cp <リポジトリ内のファイル> /etc/systemd/system/`
- `sudo rm /etc/systemd/system/*`・`sudo rm /etc/sudoers.d/*`
- `sudo systemctl` 各種

**`unicco` 所有のファイルを root の unit として配置する操作**を NOPASSWD で許した時点で、それは root と等価。`unicco` を取られた攻撃者は unit を書き換えて次の起動で root を取れる。sudoers の粒度をいくら細かくしても、この経路が閉じない限り `unicco`→root の距離は変わらない。

狭めるかどうかを決めるのは sudoers ではなく、**provisioning の実行ユーザー**。

### 2. 「細かい許可」が最小権限になっていなかった

削除した `kiosk-display-control` はこう書いていた。

```
unicco ALL=(ALL) NOPASSWD: /bin/sh -c echo * > /sys/class/backlight/*/brightness
```

sudoers の**コマンド引数**のマッチではワイルドカードが `/` にもマッチする（`man sudoers`: パス名部分と違い引数ではスラッシュも一致する）。加えて `sh -c` を許可した時点で引数の制限は原理的に成立しない。**最小権限に見えて root 相当**という、狭めた気になるだけの構成だった。

削除した `coordinate-display` はさらに直接的で、`unicco` 所有の `scripts/display-brightness.sh` **そのもの**に NOPASSWD を与えていた（＝任意コードの root 実行）。

### 3. 「SD 再構築時の保険」が成り立たない

`setup-sudoers.sh` の存在理由は「`010_pi-nopasswd` が無い状態での保険」だった。しかし `010_pi-nopasswd` は Raspberry Pi OS がユーザー作成時に自動生成する標準ファイルで、通常の再構築では自動的に復活する。保険が働く場面がほぼ無い一方、上記 2 の危険な行を毎起動で書き戻していた。

## 受容したリスク

Pi は LAN 内の自宅機だが、`camera.unicco.app`（Cloudflare Tunnel → `127.0.0.1:8001`）で**インターネットから到達する**。デモ用に意図的に残した経路（``）。

`camera_service.py` は `User=pi` で動く。したがって **このサービスに RCE があれば、そのまま root が取れる**。`NOPASSWD: ALL` はこの距離をゼロにしている。

これを受容する根拠。

- 機微なエンドポイントは共有トークンで 401（`camera-service-auth.md`）。無認証で通るのは `/health`・`/status` のみ
- 上記「狭めない理由 1」のとおり、sudoers を狭めても RCE→root の距離は実質縮まらない。縮めるには provisioning の作り替えが要る

**縮めたくなったら sudoers ではなく、下の前提から着手する。**

## 将来狭めるなら何が前提か

順序に意味がある。1 と 2 を済ませない限り 3 をやっても効果が無い。

1. ~~**バックライト制御から sudo を消す**~~ — **済。** `deploy/udev/99-coordinate-backlight.rules` を `deploy/setup-pi.sh` が配置し、`bl_power` を `video` グループ書き込み可にする（`brightness` は Raspberry Pi OS 標準の `60-backlight.rules` が既に開放している）。`camera_service.py` の `sudo sh -c "echo ..."` と `scripts/display-brightness.sh` の `sudo tee` は削除済
2. **provisioning を root 側へ移す** — `coordinate-git-sync.service` を `User=pi` のまま `sudo` を呼ばせる形をやめ、コード取得（unicco）と unit 配置（root の oneshot）を分ける
3. **残る sudo を限定許可にする** — `sudo shutdown -h now`（idle auto-shutdown）と `kiosk-health-monitor.sh` の `sudo systemctl restart <特定の unit>` のみ。ここまで来て初めて `010_pi-nopasswd` を外せる

`systemd/coordinate-camera.service` の `NoNewPrivileges=false` も 1〜3 に紐づく。`sudo shutdown` が残る限り `true` に戻せない。**unit だけ `true` にすると idle auto-shutdown が黙って止まる**（``）。

## 削除した残骸

`deploy/setup-pi.sh` の `OBSOLETE_SUDOERS` が毎起動で削除する。実機で手作業せず、SD を作り直しても再発しない形にしてある。

| ファイル | 由来 | 削除理由 |
|---|---|---|
| `kiosk-display-control` | `scripts/setup/setup-sudoers.sh` が毎起動生成 | `sh -c` + ワイルドカードで最小権限になっていない |
| `coordinate-display` | 2025-09-02 の手作業（生成元なし） | スクリプト自体への NOPASSWD＝任意コードの root 実行 |
| `coordinate-recorder-watchdog` | 2025-08-14 の手作業（生成元なし） | 中身が `root ALL=(root)` で最初から無効 |

リポジトリ側では `scripts/setup/setup-sudoers.sh` と、インストーラの無い孤児テンプレート `scripts/setup/sudoers-watchdog` を削除した。
