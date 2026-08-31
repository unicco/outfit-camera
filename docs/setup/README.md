# 🔧 セットアップガイド

Coordinate Recorder の初期構築ドキュメント集です。

## システム構成（2 台）

```
[Raspberry Pi 5]  ~/coordinate-recorder      [ConoHa VPS]  ~/services/coordinate-recorder
  coordinate-camera.service                    coordinate-api.service (user)
  coordinate-kiosk.service                     coordinate-health-check.timer
  kiosk-health-monitor.service                 coordinate-db-backup.timer
  camera-pir-monitor.service                   Caddy + Cloudflare Origin Certificate
  システム Python 3.11.2（apt の picamera2）    PostgreSQL / React UI（静的ビルド配信）
                                               Python 3.12
```

- Pi → VPS 間は Tailscale で接続する
- 公開 URL は https://coordinate.unicco.app。**エンドユーザーの認証はエッジの Cloudflare Access が担う**（オリジンに再検証はない。前提と限界は [deploy/docs/cloudflare-ingress-firewall.md](../../deploy/docs/cloudflare-ingress-firewall.md)）
- DB は VPS のみ。Pi には PostgreSQL を置かない

## セットアップ手順

いずれも冪等なので、再実行してよい。詳細な手順は [system-setup.md](./system-setup.md) が正典。

<!-- verify: deploy/setup-pi.sh 2026-08-01 -->
<!-- verify: deploy/setup-vps.sh 2026-07-29 -->

### Raspberry Pi（カメラ）

```bash
ssh user@pi-camera.local   # Tailscale: ssh user@100.64.0.11
cd ~/coordinate-recorder
bash deploy/setup-pi.sh
```

前提: Raspberry Pi OS 64-bit (Debian 12 Bookworm) / Sony IMX500 AI カメラ接続済 / Tailscale 導入済 / `.env` に `BACKEND_API_URL`（VPS の Tailscale IP）を設定済 / システム Python で Picamera2 が使える。

`deploy/setup-pi.sh` がやること。冪等なので再実行してよい。

1. **1 台構成時代の遺物を停止・削除する** — `coordinate-recorder-*` / `coordinate-api` / `coordinate-ui` / `touchscreen-kiosk`（`@` 付きテンプレートと user unit を含む）/ `nginx` / PostgreSQL、および実機の棚卸しで見つかった実体のない unit 11 本（`cage-kiosk` / `camera-restart` / `display-*` 系など。）。system スコープと user スコープの両方を当たる
   - **役目を終えた `/etc/sudoers.d/` も削除する**（`kiosk-display-control` / `coordinate-display` / `coordinate-recorder-watchdog`）。`010_pi-nopasswd` が `NOPASSWD: ALL` を与えているため既に許可済の部分集合でしかなく、`sh -c` にワイルドカードを付けた行はむしろ危険だった。狭めない判断とその前提は [`deploy/docs/pi-sudo-policy.md`](../../deploy/docs/pi-sudo-policy.md)
2. **journal を上限つきで永続化する** — `deploy/journald/journald-coordinate.conf` を `/etc/systemd/journald.conf.d/` に置く。この Pi は撮影が済むと自分で halt するので、既定の `Storage=volatile` だと調べたい前回 boot のログが消える。内容が変わったときだけ `systemctl restart systemd-journald` + `journalctl --flush` を打つ
3. **`coordinate-camera.service` を配置・起動する**
4. **バックライトの udev rule と Kiosk・PIR モニターを配置する** — `deploy/udev/99-coordinate-backlight.rules`（`bl_power` を `video` グループ書き込み可にする。）と `coordinate-kiosk` / `kiosk-health-monitor` / `camera-pir-monitor`。Kiosk 系は `graphical.target` が使えるときだけ enable・start する
   - udev rule は**内容が変わったときだけ** `udevadm control --reload-rules` + `udevadm trigger --action=add` を打つ。`--action=add` を省くと既定の `change` が送られ、`ACTION=="add"` の rule は発火しない
5. 古いデータ・ディレクトリを掃除して結果を表示する

**apt・picamera2・Tailscale は扱わない**（上の前提として要求するだけ）。まっさらな Pi から組む手順は未整備。

#### 起動時の自動同期（通常はこちらが走る）

手で `setup-pi.sh` を叩く必要は普段ない。**Pi は起動するたびに自分で main へ追いつく。**

`coordinate-git-sync.service`（起動時 oneshot・camera や kiosk より前に実行）が `scripts/git-sync-on-boot.sh` を走らせ、`origin/main` へ `reset --hard` したうえで `deploy/setup-pi.sh --provision-only` を呼ぶ。

`--provision-only` は上の 1〜4 のうち**配置・enable・旧サービスと旧 sudoers の掃除だけ**を実施し、次を**しない**。

- **サービスの起動** — 起動は systemd の責務。unit は target から起こされる。`coordinate-git-sync` は `Before=` でそれらより前に順序づけられているため、ここで `systemctl start` すると start ジョブと相互に待ち合って boot が `TimeoutStartSec` まで固まる（実機で再現）
- **古いデータの掃除（5）** — 1 台構成からの移行で一度やれば済む処理。毎 boot で `rm` 系を回さない

制約が 2 つある。

- **新規に追加した unit は、その boot では起動しない。** enable した時点で target のジョブ集合は確定しているため、有効になるのは次の起動から
- 同期の結果は `~/coordinate-recorder/.git-sync-status` に残る（`ok <sha>` / `fetch-failed <sha>` / `reset-failed <sha>`）。`setup-pi.sh` の [6/6] が表示する

`.github/workflows/deploy-raspberry-pi.yml` は **push では発火しない**。Pi の稼働時間と main への push は無関係で、push で回すと SSH が届かず失敗し続けるため。「今すぐ反映したい」ときに人間が手動 dispatch する経路として残してある。

### ConoHa VPS（API + UI + DB）

```bash
ssh conoha                     # ~/.ssh/config のエイリアス（専用鍵が要る）
cd ~/services/coordinate-recorder
bash deploy/setup-vps.sh
```

前提: Ubuntu 22.04+ / Tailscale・Caddy・PostgreSQL 導入済 / `coordinate_db` 作成済 / `libgl1` `libglib2.0-0` 導入済（OpenCV 用）/ `.env` 設定済 / `coordinate.unicco.app` の A レコードと Cloudflare Origin Certificate 設定済。

`deploy/setup-vps.sh` は `deploy/systemd/` の user unit を入れ、Caddy の `sites-enabled` に設定を配置する。

## 動作確認

```bash
# Pi
sudo systemctl status coordinate-camera
sudo journalctl -u coordinate-camera -f
libcamera-hello --list-cameras
curl -I http://localhost:8001/stream

# VPS
systemctl --user status coordinate-api
curl -f http://localhost:8000/health

# 公開経路
curl -I https://coordinate.unicco.app
```

## ドキュメント一覧

| ドキュメント | 内容 |
|---|---|
| [system-setup.md](./system-setup.md) | **2 台構成のセットアップ手順（正典）** |
| [hardware-setup.md](./hardware-setup.md) | Pi のハードウェア接続・カメラ・PIR センサー |
| [touchscreen-setup.md](./touchscreen-setup.md) | タッチスクリーン全画面表示 |
| [kiosk-scripts-guide.md](./kiosk-scripts-guide.md) | Kiosk（Chromium 全画面）管理スクリプト |
| [database.md](./database.md) | Alembic による DB 初期構築・再構築 |
| [vertex-ai-setup.md](./vertex-ai-setup.md) | Vertex AI 設定 |
| [google-photos-auth-guide.md](./google-photos-auth-guide.md) | Google Photos 認証 |
| [access-setup.md](./access-setup.md) | ⚠️ Cloudflare Tunnel 時代の記述。**現行構成には当てはまらない**（下記） |

### 外部アクセスの正典

`access-setup.md` が書いている Pi 上の `cloudflared tunnel` は現行構成では使っていない（`deploy/setup-pi.sh` が `cloudflare-tunnel.service` を廃止対象として削除する）。現行は VPS の Caddy + Cloudflare Origin Certificate で、認証はエッジの Cloudflare Access が担う。

- [deploy/caddy/coordinate.caddy](../../deploy/caddy/coordinate.caddy) — Caddy の実設定
- [deploy/docs/cloudflare-ingress-firewall.md](../../deploy/docs/cloudflare-ingress-firewall.md) — Cloudflare 経由を強制する ingress 制限
- [deploy/docs/cloudflare-authenticated-origin-pulls.md](../../deploy/docs/cloudflare-authenticated-origin-pulls.md) — mTLS による経路認証
- deploy/docs/camera-service-auth.md — カメラサービスのトークン認証（経路認証であってユーザー認証ではない）

## よくある問題

### カメラが認識されない

```bash
dmesg | grep -i camera
libcamera-hello --list-cameras
```

Picamera2 は apt（`python3-picamera2`）で入れる。pip 版を入れると `~/.local` に二重に入って apt 版と競合する。詳細は [troubleshooting/picamera2-setup.md](../troubleshooting/picamera2-setup.md)。

### サービスが起動しない

```bash
sudo journalctl -u coordinate-camera -n 50      # Pi
journalctl --user -u coordinate-api -n 50       # VPS
```

依存関係の不足が疑われるときは、Pi はシステム Python + apt、VPS は `requirements-api.txt` の venv という前提を確認する（[deployment/venv-management.md](../deployment/venv-management.md)）。Poetry は使っていない。

### 公開 URL にアクセスできない

Caddy とオリジンの疎通、および Cloudflare Access のポリシー適用を分けて切り分ける。

```bash
sudo systemctl status caddy
curl -f http://localhost:8000/health   # オリジン単体
```

## 次のステップ

1. **運用準備** → operations/deployment-checklist.md
2. **監視設定** → operations/monitoring.md
3. **メンテナンス計画** → operations/maintenance.md
4. **API 利用** → [api/endpoints.md](../api/endpoints.md)
