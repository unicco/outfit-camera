# outfit-camera：今日なに着た？

Raspberry Pi のカメラが、毎日の服装を自動で撮って記録するシステムです。撮った写真は VLM が読んで、何を着ていたかをワードローブと照合します。玄関に置くことを想定したものです。

> **A Raspberry Pi camera at your door that records what you wore, every day.**
> It photographs you on the way out, has a VLM identify the garments, and matches them
> against your wardrobe. The UI is Japanese-only. Documentation is in Japanese.

## 概要

実際に自宅で動いているシステムの、ある時点のスナップショットです。開発は別の非公開リポジトリで続いており、ここへは随時反映されません。

- issue や Pull Request への対応は約束できません。動かし方の質問にも速やかに回答できないことがあります
- 自宅のインフラに依存した設定値（IP アドレス、ホスト名、ストレージのバケット名など）は例示値に置き換えてあります
- CI の定義は独自の環境専用のため含めていません

## 主要機能

- **自動撮影** — PIR センサーで人を検知し、玄関を通るときに全身を撮る
- **衣類の検出** — VLM（Gemini 2.5-flash）が写真から衣類・色を読み、登録済のワードローブと突き合わせる
- **履歴とワードローブの管理** — Web UI でコーディネート履歴を辿り、手持ちの服を管理する
- **玄関のタッチスクリーン** — その場で今日の記録を確認できる
- **外部連携** — Google Photos への保存、Google Cloud Storage で画像を管理する

## 構成

2 台に分かれています。

| 役割 | 機材 | 動くもの |
|------|------|---------|
| カメラ | Raspberry Pi 5（8GB） | 人物検出・撮影 |
| アプリケーション | VPS | FastAPI + React + PostgreSQL |

Pi と VPS は Tailscale で繋ぎ、VPS は Caddy をリバースプロキシに置いて公開しています。

### 技術スタック

- **Backend** — FastAPI / Python 3.12 / SQLAlchemy 2.x / PostgreSQL
- **Frontend** — React 19 / TypeScript 5.9 / Vite / Tailwind CSS v4
- **AI** — VLM（Gemini 2.5-flash）。フォールバック先は持ちません
- **Camera** — Raspberry Pi 5 + Picamera2 + Sony IMX500
- **Infra** — Caddy / Tailscale / systemd
- **Test** — Pytest / Vitest / Playwright

## 動作環境

- Raspberry Pi 5
- [CSI カメラ](https://www.switch-science.com/products/8702)
- [タッチスクリーン](https://www.amazon.co.jp/dp/B08HCF61YR)
- [PIR センサー](https://www.amazon.co.jp/dp/B09WVMKB2X)
- 常時稼働のサーバー（VPS OR 自宅のマシン）と PostgreSQL
- Gemini の API キー、Google Cloud Storage のバケット
- 玄関に機材を設置できる住環境

ローカルで UI と API だけ触るならカメラなしで起動できます。

```bash
./scripts/start-development.sh --skip-camera
# Frontend: http://localhost:3000
# API docs: http://localhost:8000/docs
```

設定は `.env.template` を写して埋めてください。中の値はすべて例示なので、自分の環境のものに置き換える必要があります。

## デバイスが入る箱を作りたい場合

[`kit/`](kit/) に箱のレーザーカット用の図面（4 面ぶんの PDF と寸法表）と設置の実測値を置いています。

## ドキュメント

`docs/` に設計と手順があります。ただし自宅の運用に密着した部分（バックアップの転送先、機材の物理配置、SD カードの交換手順など）は公開版から外してあります。目次に名前だけ残っている項目があるのはそのためです。

## ライセンス

コードは MIT ライセンスです。`LICENSE` を参照してください。

`kit/` に置いた筐体の図面と寸法表は CC BY-SA 4.0 です。`kit/LICENSE` を参照してください。
