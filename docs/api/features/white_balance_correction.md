# ホワイトバランス補正機能

## 概要

全身写真のホワイトバランスと色調整を行い、ワードローブ画像との色味の統一を図る機能です。

## 機能

1. **ホワイトバランス補正**
   - 固定 ROI（Region of Interest）による白基準検出
   - 自動 ROI 検出（フォールバック）
   - sRGB 色空間での正規化

2. **色調整**
   - 彩度調整（デフォルト: 0.9）
   - コントラスト調整（デフォルト: 1.05）
   - 明度調整（デフォルト: 0.0）

## 使用方法

### API エンドポイント

#### v1 API
```json
POST /api/v2/ai/detect
{
  "photo_id": "photo_20250916_105153",
  "apply_wb_correction": true  // ホワイトバランス補正を適用（デフォルト: true）
}
```

#### v2 API
```json
POST /api/v2/ai/detect
{
  "photo_id": "photo_20250916_105153",
  "apply_wb_correction": true  // ホワイトバランス補正を適用（デフォルト: true）
}
```

### 設定ファイル

`api/config/wb_config.json`:
```json
{
  "white_balance": {
    "roi": [0.1, 0.1, 0.3, 0.3],  // 左上 10%〜30% の領域を白基準として使用
    "fallback_lab_threshold": {
      "l_min": 70,
      "l_max": 100,
      "a_max": 6,
      "b_max": 6
    }
  },
  "tone_adjustment": {
    "saturation": 0.9,    // 彩度（0.85-0.95推奨）
    "contrast": 1.05,     // コントラスト（1.03-1.08推奨）
    "brightness": 0.0     // 明度（-20〜+20）
  }
}
```

### テストスクリプト

```bash
# 基本的なテスト
python api/scripts/test_wb_correction.py

# 特定の画像でテスト
python api/scripts/test_wb_correction.py --images photos/test1.jpg photos/test2.jpg

# ROI 選択モード（インタラクティブ）
python api/scripts/test_wb_correction.py --roi
```

### プログラムでの使用

```python
from api.app.utils.wb_and_tone import ImageColorProcessor

# プロセッサーを初期化
processor = ImageColorProcessor("config/wb_config.json")

# 画像を処理
result = processor.process_image(
    "path/to/image.jpg",
    apply_wb=True,      # ホワイトバランス補正
    apply_tone=True     # 色調整
)

# 処理して保存
output_path = processor.process_and_save(
    "path/to/image.jpg",
    suffix="_corrected",
    apply_wb=True,
    apply_tone=True,
    quality=85
)
```

## ROI の設定方法

1. **固定 ROI 方式**（推奨）
   - 撮影環境の白い壁やドアなど、常に同じ位置にある白い領域を選択
   - 画像サイズに対する比率で指定（0.0〜1.0）
   - 例：左上の壁の領域 `[0.1, 0.1, 0.3, 0.3]`

2. **ROI 選択ツール**
   ```bash
   python api/scripts/test_wb_correction.py --roi
   ```
   - 画像をクリック＆ドラッグして白基準領域を選択
   - 選択後、比率が表示されるので設定ファイルに記載

3. **自動検出**（フォールバック）
   - 固定 ROI が無効な場合に自動的に発動
   - Lab 色空間でのしきい値に基づいて白い領域を検出

## トラブルシューティング

### ホワイトバランス補正がスキップされる

- 固定 ROI の明度が適切でない（暗すぎる/明るすぎる）
- 固定 ROI の彩度が高すぎる
- 自動検出でも白基準領域が見つからない

**対処法**：
1. ROI 選択ツールで適切な白基準領域を再選択
2. 撮影環境の照明を改善
3. `apply_wb_correction: false` で補正を無効化

### 色が不自然になる

- 彩度やコントラストの設定値が極端

**対処法**：
1. 設定値を調整（彩度: 0.85-0.95、コントラスト: 1.03-1.08）
2. 色調整のみ無効化（`apply_tone: false`）

## パフォーマンスへの影響

- 処理時間：画像1枚あたり約 50-100ms 追加
- メモリ使用量：画像サイズに依存（通常は問題なし）

## 今後の改善予定

- [ ] バッチ処理の最適化
- [ ] 機械学習による自動パラメータ調整
- [ ] 複数の照明条件に対応したプロファイル管理