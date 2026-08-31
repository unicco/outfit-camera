# 📚 Coordinate Recorder ドキュメント

運用フェーズに最適化された Coordinate Recorder システムのドキュメント集です。

## 🎯 目的別ドキュメント

### 🚀 運用者向け

システムの日常運用・監視・メンテナンスを担当する方向け：

- **operations/** - 運用ガイド
  - deployment-checklist.md - デプロイメント手順
  - monitoring.md - システム監視
  - troubleshooting.md - 問題解決
  - maintenance.md - 定期メンテナンス

### 🔧 システム管理者向け

初期セットアップ・システム構築を担当する方向け：

- **[setup/](./setup/)** - セットアップガイド
  - [hardware-setup.md](./setup/hardware-setup.md) - ハードウェア設定
  - [system-setup.md](./setup/system-setup.md) - システム構成・サービス設定
  - [access-setup.md](./setup/access-setup.md) - ⚠️ Cloudflare Tunnel 時代の記述。現行は Caddy + Cloudflare Access（[setup/README.md](./setup/README.md) の「外部アクセスの正典」を参照）
  - [touchscreen-setup.md](./setup/touchscreen-setup.md) - タッチスクリーン設定
  - [kiosk-scripts-guide.md](./setup/kiosk-scripts-guide.md) - Kiosk 表示制御
  - [vertex-ai-setup.md](./setup/vertex-ai-setup.md) - Vertex AI セットアップ

### 🔌 API 利用者向け

システム API を利用する開発者・統合担当者向け：

- **[api/](./api/)** - API リファレンス
  - [endpoints.md](./api/endpoints.md) - エンドポイント仕様
  - [wardrobe-management.md](./api/wardrobe-management.md) - ワードローブ API

### 💻 開発者向け

- **[development/local-quality-checks.md](./development/local-quality-checks.md)** - ローカルで Fast Quality Checks を再現する手順

## 🔍 クイックナビゲーション

### 新規導入する場合

1. **全体像と手順の入口** → [setup/README.md](./setup/README.md)
2. **ハードウェア準備** → [setup/hardware-setup.md](./setup/hardware-setup.md)
3. **システム構築（Pi / VPS）** → [setup/system-setup.md](./setup/system-setup.md)
4. **運用開始** → operations/deployment-checklist.md

### 既存システムを運用する場合

1. **日常監視** → operations/monitoring.md
2. **問題が発生した場合** → operations/troubleshooting.md
3. **定期メンテナンス** → operations/maintenance.md

### API を利用する場合

1. **エンドポイント確認** → [api/endpoints.md](./api/endpoints.md)
2. **ワードローブ機能** → [api/wardrobe-management.md](./api/wardrobe-management.md)

## 🏗️ システム概要

Coordinate Recorder は、AI カメラを使用した服装記録システムです：

### 本番アーキテクチャ（2 台構成）

```
[Raspberry Pi 5]                    [ConoHa VPS]
  Camera サービスのみ                 API + UI + DB
  - coordinate-camera.service        - coordinate-api.service（user）
  - PIR センサー検知                  - coordinate-health-check.timer（5分間隔）
  - 撮影 → VPS の API へ送信          - coordinate-db-backup.timer（毎日 03:00）
                                     - Caddy（Cloudflare Origin Certificate）
                                     - PostgreSQL
                                     - React UI（ビルド済静的ファイル）

[Cloudflare]
  DNS: coordinate.unicco.app → VPS
  SSL: Full (Strict) + Origin Certificate
```

### デプロイ

- **IaC**: `deploy/setup-pi.sh`（Pi）、`deploy/setup-vps.sh`（VPS）が冪等にセットアップ
- **自動デプロイ**: main マージ時に GitHub Actions が Pi/VPS へ自動デプロイ
  - `.github/workflows/deploy-raspberry-pi.yml`（camera/ 変更時）
  - `.github/workflows/deploy-vps.yml`（api/src/ui/deploy/ 変更時）
- **接続**: GitHub Actions → Tailscale → SSH

### 主要コンポーネント

- **API サーバー** (FastAPI) - データ管理・AI 処理（VPS 上）
  - Roboflow AI による高精度衣類検出
  - GrabCut アルゴリズムによる背景除去
  - Jina API による 1024 次元埋め込み生成
- **Camera サーバー** (Python) - カメラ制御・ストリーミング（Raspberry Pi 上）
- **UI** (React) - Web インターフェース（VPS で Caddy 配信）
- **Database** (PostgreSQL) - データ永続化（VPS 上）

### 対応環境

- **開発環境**: macOS、Linux
- **本番環境（カメラ）**: Raspberry Pi 5 + Sony IMX500 AI カメラ
- **本番環境（サーバー）**: ConoHa VPS（Ubuntu）
- **外部アクセス**: Cloudflare DNS + Origin Certificate（Full Strict）

## 📁 その他のリソース

### その他のドキュメント

- **[deployment/](./deployment/)** - デプロイメント関連ドキュメント
  - [venv-management.md](./deployment/venv-management.md) - 仮想環境管理
  - [systemd-deployment.md](./deployment/systemd-deployment.md) - systemd デプロイ
- **[troubleshooting/](./troubleshooting/)** - トラブルシューティング
- **[security/](./security/)** - セキュリティ関連
  - [google-photos-oauth.md](./security/google-photos-oauth.md) - Google Photos OAuth 設定

### 機能ドキュメント

- **[api/features/](./api/features/)** - API 機能別詳細ドキュメント
  - [white_balance_correction.md](./api/features/white_balance_correction.md) - ホワイトバランス補正機能

## 🆘 サポート

### 緊急時の対応

1. **システム障害**: troubleshooting.md の緊急対応手順を実行
2. **データ消失の恐れ**: バックアップ手順を最優先で実行
3. **解決できない場合**: 開発チームへ連絡（GitHub Issue 作成）

### 改善提案

ドキュメントの改善提案や新規追加要望は GitHub Issue でお知らせください。

---

**最終更新**: VPS 移行・IaC 化・コードリファクタリング (#1442)
