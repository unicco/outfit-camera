# PIR センサー問題対応ガイド

## 問題の概要

PIR センサーが検知を停止する問題と、その解決策について説明します。

## 🔍 症状

- PIR センサーが一度検知した後、その後の動きに反応しなくなる
- カメラサービスのログに PIR 検知のエントリが出力されない
- systemd サービス起動時に AI 関連モジュールのエラー

## 🔧 根本原因

1. **依存関係の問題**: Poetry 環境で AI 関連モジュールが不足
2. **サービス起動失敗**: systemd サービスが正常に起動せずPIRスレッドが初期化されない
3. **プロセス競合**: 複数のカメラサービスプロセスが GPIO を奪い合う

## ✅ 解決策

### 1. systemd サービス設定の修正

**修正内容:**

- `DISABLE_AI_FEATURES=true` を追加（AI機能を無効化して軽量動作）
- Poetry ではなく直接 Python3 を使用
- 適切な環境変数設定

```ini
# /etc/systemd/system/coordinate-camera.service（実体は systemd/coordinate-camera.service）
[Service]
Environment="DISABLE_AI_FEATURES=true"
Environment="PYTHONPATH=/home/pi/coordinate-recorder/src"
ExecStart=/usr/bin/python3 camera/camera_service.py
```

### 2. カメラサービス起動スクリプトの改善

**修正点:**

- AI機能を無効化して軽量動作
- Poetry 依存関係を回避
- 適切なデフォルト値設定

### 3. PIR 健康監視システムの追加

**新機能:**

- PIR センサーの継続的な健康チェック
- 長期間無音の場合の自動復旧
- カメラサービスの自動再起動

## 🚀 デプロイ手順

### 自動デプロイ

```bash
# プロジェクトルートで実行
./scripts/deploy-pir-fixes.sh
```

### 手動デプロイ

1. **systemd サービス更新**

   unit を手で `cp` しない。`deploy/setup-pi.sh` が `systemd/` の unit を配置する。

   ```bash
   cd ~/coordinate-recorder
   bash deploy/setup-pi.sh
   ```

2. **PIR 監視サービス設定**

   ```bash
   # PIR 監視は camera-pir-monitor.service で統合済
   sudo systemctl enable camera-pir-monitor.service
   ```

3. **サービス再起動**
   ```bash
   sudo systemctl restart coordinate-camera.service
   sudo systemctl start camera-pir-monitor.service
   ```

## 🔍 監視・デバッグ

### ログ確認

```bash
# カメラサービスのログ
sudo journalctl -f -u coordinate-camera.service

# PIR 監視ログ（統合サービス）
sudo journalctl -f -u camera-pir-monitor.service

# 専用 PIR 監視ログ
tail -f /home/pi/coordinate-recorder/logs/pir-monitor.log
```

### 健康状態チェック

```bash
# カメラサービス健康チェック
curl -s http://pi-camera.local:8001/health | python3 -m json.tool

# PIR ステータス確認
curl -s http://pi-camera.local:8001/pir/status | python3 -m json.tool
```

### 手動テスト

```bash
# PIR センサーの物理的テスト
# センサーの前で手を振って検知をテスト

# ログでの確認
tail -f /home/pi/coordinate-recorder/logs/camera\ server-service.log | grep "PIR"
```

## 📋 予防策

1. **定期監視**: PIR 監視サービスが継続的に健康状態をチェック
2. **自動復旧**: 問題検出時の自動再起動機能
3. **軽量モード**: 重い依存関係を避けて安定性を向上
4. **適切なログ**: 問題診断のための詳細なログ出力

## 🚨 トラブルシューティング

### PIR 検知が復旧しない場合

1. **GPIO 使用状況確認**

   ```bash
   sudo lsof /dev/gpiomem
   ```

2. **プロセス重複チェック**

   ```bash
   ps aux | grep camera_service
   ```

3. **手動再起動**
   ```bash
   sudo systemctl restart coordinate-camera.service
   ```

### サービス起動失敗

1. **詳細エラー確認**

   ```bash
   sudo journalctl -u coordinate-camera.service --since="5 minutes ago"
   ```

2. **環境変数確認**

   ```bash
   sudo systemctl show coordinate-camera.service --property=Environment
   ```

3. **手動起動テスト**
   ```bash
   cd /home/pi/coordinate-recorder
   DISABLE_AI_FEATURES=true python3 camera/camera_service.py
   ```

## 📈 改善された機能

1. **安定性向上**: AI機能無効化による依存関係問題の解決
2. **自動監視**: PIR 検知の継続性を自動監視
3. **自動復旧**: 問題発生時の自動復旧機能
4. **詳細ログ**: 問題診断のための包括的なログ
5. **簡単デプロイ**: ワンコマンドでの修正適用
