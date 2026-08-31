# カメラストリーム Connection Reset エラーのトラブルシューティング

## 症状

- `curl http://localhost:8001/stream` で "Connection reset by peer" エラーが発生
- 外部からのアクセス（例: `http://pi-camera.local:8001/stream`）は正常
- `/health` や `/pir/status` などの他のエンドポイントは正常

## 原因

iptables のファイアウォールルールにより、ストリームエンドポイントへのアクセスがブロックされている可能性があります。

## 確認方法

```bash
# iptables ルールを確認
sudo iptables -L INPUT -n | grep -E '(8001|stream)'
```

以下のようなルールが表示された場合、これが原因です：

```
REJECT tcp -- 0.0.0.0/0 0.0.0.0/0 tcp dpt:8001 STRING match "/stream" ALGO name bm reject-with tcp-reset
```

## 解決方法

### 1. 問題のルールを特定

```bash
sudo iptables -L INPUT --line-numbers | grep 8001
```

### 2. ルールを削除

```bash
# 例: ルール番号が 2 の場合
sudo iptables -D INPUT 2
```

### 3. アクセスを確認

```bash
curl -s http://localhost:8001/stream | head -c 100
```

## 注意事項

- このルールが追加された理由を調査することを推奨
- セキュリティ要件がある場合は、アプリケーションレベルでアクセス制御を実装
- 再起動後にルールが復活する場合は、永続化設定を確認

## 関連情報

- Issue: #xxx (該当する Issue 番号)
- 発生日: 2025-09-17
- 影響範囲: localhost からのカメラストリームアクセスのみ
