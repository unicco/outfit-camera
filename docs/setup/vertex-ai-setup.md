# Vertex AI Imagen API セットアップガイド

## 1. Google Cloud プロジェクトの準備

### Step 1: Google Cloud Console にログイン

1. https://console.cloud.google.com にアクセス
2. Google アカウントでログイン

### Step 2: 新規プロジェクトを作成

1. 画面上部のプロジェクトセレクタをクリック
2. 「新しいプロジェクト」をクリック
3. プロジェクト名を入力（例：`coordinate-recorder-imagen`）
4. 「作成」をクリック

## 2. 請求先アカウントの設定（必須）

### Step 1: 請求先アカウントを作成

1. 左側メニューから「請求」をクリック
2. 「請求先アカウントを管理」を選択
3. 「アカウントを作成」をクリック
4. クレジットカード情報を入力

**注意**: 無料トライアルで $300 のクレジットがもらえます

## 3. Vertex AI API の有効化

### Step 1: API ライブラリへ移動

1. 左側メニューから「API とサービス」→「ライブラリ」
2. 検索バーに「Vertex AI」と入力

### Step 2: 必要な API を有効化

以下の API を有効化してください：

- **Vertex AI API**
- **Cloud Vision API**（オプション）

各 API の画面で「有効にする」ボタンをクリック

## 4. サービスアカウントの作成

### Step 1: サービスアカウントページへ

1. 「IAM と管理」→「サービスアカウント」
2. 「サービスアカウントを作成」をクリック

### Step 2: サービスアカウントの詳細

```
名前: coordinate-recorder-imagen
ID: coordinate-recorder-imagen
説明: Vertex AI Imagen API 用のサービスアカウント
```

### Step 3: 権限の付与

以下のロールを追加：

- **Vertex AI ユーザー**
- **Storage オブジェクト管理者**（画像保存用）

### Step 4: キーの作成

1. 作成したサービスアカウントをクリック
2. 「キー」タブを選択
3. 「キーを追加」→「新しいキーを作成」
4. 「JSON」を選択して「作成」
5. **重要**: ダウンロードされた JSON ファイルを安全に保管

## 5. 環境変数の設定

`.env` ファイルに追加：

```bash
# Google Cloud 設定
GOOGLE_CLOUD_PROJECT_ID="your-project-id"
GOOGLE_APPLICATION_CREDENTIALS="path/to/service-account-key.json"
VERTEX_AI_LOCATION="us-central1"
```

## 6. Python SDK のインストール

```bash
pip install google-cloud-aiplatform
pip install google-cloud-storage
```

## 7. 動作確認

```python
import os
from google.cloud import aiplatform

# 環境変数から設定を読み込み
project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
location = os.getenv("VERTEX_AI_LOCATION", "us-central1")

# 初期化
aiplatform.init(project=project_id, location=location)

print("✅ Vertex AI の設定が完了しました！")
```

## 💰 コスト管理

### 予算アラートの設定（推奨）

1. 「請求」→「予算とアラート」
2. 「予算を作成」
3. 月額予算を設定（例：$50）
4. 50%、90%、100% でアラートメールを設定

### 使用量の確認

- 「請求」→「レポート」で日次の使用量を確認
- Imagen API の使用量は「Vertex AI」セクションに表示

## 🔗 便利なリンク

- [Vertex AI 料金計算ツール](https://cloud.google.com/products/calculator)
- [Imagen API ドキュメント](https://cloud.google.com/vertex-ai/docs/generative-ai/image/overview)
- [サンプルコード](https://github.com/GoogleCloudPlatform/python-docs-samples/tree/main/generative_ai/imagen)

## トラブルシューティング

### エラー: "API が有効になっていません"

→ 上記の Step 3 を確認して API を有効化

### エラー: "認証に失敗しました"

→ サービスアカウントキーのパスを確認

### エラー: "請求先アカウントが必要です"

→ Step 2 で請求先アカウントを設定
