#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID=""
TOPIC=""
QUEUE=""
REGION="asia-northeast1"
MESSAGE='{"job_id":"smoke-test","source":"cli"}'
ATTRIBUTES=()

usage() {
  cat <<USAGE
Usage: $0 --project <PROJECT_ID> --topic <TOPIC> [options]

Options:
  --queue <QUEUE_ID>           Cloud Tasks のキュー名（例: wardrobe-dev-preprocess）
  --region <REGION>            Cloud Tasks のリージョン（既定: asia-northeast1）
  --message <JSON>             送信するメッセージ本文（JSON 文字列）
  --attr key=value             Pub/Sub 属性を追加（複数指定可）
  --help                       このヘルプを表示
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT_ID="$2"
      shift 2
      ;;
    --topic)
      TOPIC="$2"
      shift 2
      ;;
    --queue)
      QUEUE="$2"
      shift 2
      ;;
    --region)
      REGION="$2"
      shift 2
      ;;
    --message)
      MESSAGE="$2"
      shift 2
      ;;
    --attr)
      ATTRIBUTES+=("$2")
      shift 2
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$PROJECT_ID" || -z "$TOPIC" ]]; then
  echo "--project と --topic は必須です" >&2
  usage
  exit 1
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI が見つかりません" >&2
  exit 1
fi

echo "🚀 Publishing smoke-test message to Pub/Sub"
PUBLISH_ARGS=("pubsub" "topics" "publish" "$TOPIC" "--project" "$PROJECT_ID" "--message" "$MESSAGE")

for attribute in "${ATTRIBUTES[@]}"; do
  PUBLISH_ARGS+=("--attribute" "$attribute")
done

gcloud "${PUBLISH_ARGS[@]}"

echo "✅ Publish request sent"

if [[ -n "$QUEUE" ]]; then
  printf "\n🔎 Checking Cloud Tasks queue backlog\n"
  gcloud tasks queues describe "$QUEUE" \
    --project "$PROJECT_ID" \
    --location "$REGION" \
    --format "value(stats.tasksCount)" \
    || true
  echo "(上記が空欄でも数秒後に再実行すると反映されます)"
fi

cat <<NEXT

次の確認ポイント:
  1. Cloud Run > サービス で dispatcher / runner のログに smoke-test の記録があるか
  2. Cloud Tasks > キュー ${QUEUE:-wardrobe-<env>-preprocess} にタスクが生成されたか
  3. (任意) Pub/Sub トピック ${TOPIC} のサブスクリプションでエラーがないか
NEXT
