#!/bin/bash

# 統一デプロイスクリプト - Issue #246 対応
# 本番環境へのデプロイを統一化し、混乱を防ぐ

set -euo pipefail

# 設定
PRODUCTION_HOST="pi-camera.local"
PRODUCTION_USER="pi"
PRODUCTION_PATH="/home/pi/coordinate-recorder"
BACKUP_PATH="/home/pi/coordinate-recorder-backup-$(date +%Y%m%d-%H%M%S)"

# カラー出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ヘルプ表示
show_help() {
    cat << EOF
🚀 統一デプロイスクリプト - Issue #246 対応

使用方法:
  $0 [OPTIONS] COMMAND

コマンド:
  deploy          本番環境にデプロイ (推奨)
  deploy-force    バックアップなしで強制デプロイ
  backup          本番環境のバックアップのみ
  status          本番環境の状態確認
  rollback        最新のバックアップにロールバック

オプション:
  -h, --help      このヘルプを表示
  --dry-run       実際のデプロイを行わず、実行予定の操作を表示
  --no-backup     バックアップを作成しない (非推奨)
  --branch BRANCH 指定されたブランチをデプロイ (デフォルト: main)

例:
  $0 deploy                    # 通常のデプロイ
  $0 deploy --branch feature/issue-246  # 特定ブランチのデプロイ
  $0 status                    # 本番環境の状態確認
  $0 rollback                  # ロールバック

⚠️  注意事項:
- 本番環境への SSH アクセスが必要です
- デプロイ前に必ずバックアップが作成されます
- サービス停止時間が発生します (約 30秒-1分)
EOF
}

# 本番環境の接続確認
check_production_connection() {
    print_info "本番環境への接続確認中..."

    if ! ssh -o ConnectTimeout=10 "${PRODUCTION_USER}@${PRODUCTION_HOST}" "echo 'Connection successful'" > /dev/null 2>&1; then
        print_error "本番環境 (${PRODUCTION_HOST}) への SSH 接続に失敗しました"
        print_error "以下を確認してください:"
        print_error "  1. SSH キーが正しく設定されているか"
        print_error "  2. 本番機が起動しているか"
        print_error "  3. ネットワーク接続に問題がないか"
        exit 1
    fi

    print_success "本番環境への接続確認完了"
}

# 本番環境の状態確認
check_production_status() {
    print_info "本番環境の状態確認中..."

    ssh "${PRODUCTION_USER}@${PRODUCTION_HOST}" << 'EOF'
echo "=== 本番環境状態レポート ==="
echo "ホスト名: $(hostname)"
echo "現在時刻: $(date)"
echo "作業ディレクトリ: $(pwd)"

echo -e "\n📁 プロジェクトディレクトリ確認:"
if [ -d "/home/pi/coordinate-recorder" ]; then
    echo "✅ プロジェクトディレクトリが存在"
    cd /home/pi/coordinate-recorder
    echo "現在のブランチ: $(git branch --show-current 2>/dev/null || echo 'Git情報なし')"
    echo "最新コミット: $(git log --oneline -1 2>/dev/null || echo 'Git情報なし')"
else
    echo "❌ プロジェクトディレクトリが存在しません"
fi

echo -e "\n🔧 サービス状態:"
echo "プロセス確認:"
ps aux | grep -E "(uvicorn|python.*app)" | grep -v grep || echo "API サーバーが動作していません"

echo -e "\n🌐 ポート使用状況:"
lsof -i :8000 2>/dev/null | head -5 || echo "ポート 8000 は使用されていません"
lsof -i :8001 2>/dev/null | head -5 || echo "ポート 8001 は使用されていません"
lsof -i :3000 2>/dev/null | head -5 || echo "ポート 3000 は使用されていません"

echo -e "\n💾 ディスク使用量:"
df -h /home/pi/coordinate-recorder 2>/dev/null || df -h /home/pi

echo "========================="
EOF
}

# バックアップ作成
create_backup() {
    if [ "$NO_BACKUP" = true ]; then
        print_warning "バックアップをスキップしています (--no-backup が指定されました)"
        return 0
    fi

    print_info "本番環境のバックアップ作成中..."

    ssh "${PRODUCTION_USER}@${PRODUCTION_HOST}" << EOF
if [ -d "${PRODUCTION_PATH}" ]; then
    echo "バックアップ作成: ${PRODUCTION_PATH} -> ${BACKUP_PATH}"
    cp -r "${PRODUCTION_PATH}" "${BACKUP_PATH}"
    echo "✅ バックアップ作成完了: ${BACKUP_PATH}"

    # 古いバックアップの削除 (7日以上前)
    find /home/pi/coordinate-recorder-backup-* -maxdepth 0 -type d -mtime +7 -exec rm -rf {} + 2>/dev/null || true
    echo "🗑️  古いバックアップを削除しました"
else
    echo "⚠️  バックアップ対象ディレクトリが存在しません: ${PRODUCTION_PATH}"
fi
EOF

    print_success "バックアップ作成完了"
}

# デプロイ実行
deploy_to_production() {
    local branch="${DEPLOY_BRANCH:-main}"

    print_info "本番環境へのデプロイ開始 (ブランチ: ${branch})"

    if [ "$DRY_RUN" = true ]; then
        print_warning "DRY RUN モード - 実際のデプロイは行いません"
        print_info "実行予定の操作:"
        print_info "  1. 本番環境のサービス停止"
        print_info "  2. Git からの最新コード取得 (${branch})"
        print_info "  3. 依存関係の更新"
        print_info "  4. データベースマイグレーション"
        print_info "  5. サービス再起動"
        print_info "  6. 動作確認"
        return 0
    fi

    ssh "${PRODUCTION_USER}@${PRODUCTION_HOST}" << EOF
set -euo pipefail

echo "📍 作業ディレクトリに移動"
cd "${PRODUCTION_PATH}"

echo "🛑 既存サービスの停止"
# 新しいファイル名を使用（Issue #622 対応）
./scripts/stop-development.sh 2>/dev/null || echo "サービス停止スクリプトがない、または既に停止済"

# systemd サービスも停止（main ブランチからの追加機能）
sudo systemctl stop coordinate-api.service 2>/dev/null || echo "API サービス既に停止済"
sudo systemctl stop coordinate-camera.service 2>/dev/null || echo "Camera サービス既に停止済"
sudo systemctl stop coordinate-ui.service 2>/dev/null || echo "UI サービス既に停止済"

# 手動起動プロセスがあれば強制終了（systemd 移行期の対応）
echo "🔍 手動起動プロセスの確認・強制終了"
pkill -f "uvicorn.*app.main" 2>/dev/null || echo "手動 uvicorn プロセスなし"
pkill -f "python.*camera" 2>/dev/null || echo "手動 camera プロセスなし"

echo "🔄 Git からの最新コード取得"
git fetch origin

# ローカル変更をstashしてから最新コードを取得
echo "💾 ローカル変更を一時保存中..."
git add . 2>/dev/null || true
git stash push -m "Deploy: auto-stash before pull $(date)" 2>/dev/null || echo "Stash不要または失敗"

git checkout ${branch}
git pull origin ${branch}

# .env.common が stash されている場合は復元
echo "🔧 環境設定ファイルの復元確認..."
if git stash list | grep -q "Deploy: auto-stash"; then
    # .env.common のみを復元（競合が発生しないように）
    git show "stash@{0}:.env.common" > .env.common.backup 2>/dev/null || true
    if [ -f ".env.common.backup" ]; then
        echo "📝 .env.common の本番設定を復元"
        mv .env.common.backup .env.common
    fi
    # stash をクリア
    git stash drop 2>/dev/null || true
fi

echo "🔧 仮想環境シンボリックリンクの修正"
# 本番環境では既存のvenvシンボリックリンクがローカルパスを指している可能性があるため、
# 強制的に削除して正しいパスで再作成する
for dir in api camera; do
    if [ -d "$dir" ]; then
        (
            cd "$dir" || { echo "エラー: $dir ディレクトリに移動できません"; continue; }
            if [ -L "venv" ]; then
                local current_link=$(readlink venv 2>/dev/null || echo "なし")
                echo "削除: $dir/venv シンボリックリンク ($current_link)"
                rm -f venv
            fi
            # 新しいシンボリックリンクは python-setup.sh で作成される
        )
    fi
done

echo "📦 Python 依存関係の更新 (pip + requirements-api.txt)"
if [ ! -d "venv" ] || [ ! -f "venv/bin/activate" ]; then
    echo "🔧 仮想環境が見つかりませんでした。新規に作成します"
    python3 -m venv venv
fi

echo "🔧 仮想環境をアクティベート中..."
# shellcheck disable=SC1091
source venv/bin/activate
echo "🪪 使用中の Python: $(which python)"

echo "⬆️ pip をアップグレード"
pip install --upgrade pip

echo "📥 requirements-api.txt を適用"
if ! pip install -r requirements-api.txt; then
    echo "❌ AI 依存パッケージのインストールに失敗しました"
    deactivate || true
    exit 1
fi

echo "🗄️ データベースマイグレーション"
if [ -d "api" ]; then
    (
        cd api || exit 1
        if [ -f "alembic.ini" ]; then
            python -m alembic -c alembic.ini upgrade head 2>/dev/null || echo "⚠️  マイグレーション失敗 (続行)"
        else
            echo "⚠️  alembic.ini が見つからないためマイグレーションをスキップします"
        fi
    )
else
    echo "⚠️  api ディレクトリが見つからないためマイグレーションをスキップします"
fi

deactivate || true

echo "🚀 サービス再起動"
# 新しいファイル名を使用（Issue #622 対応）
nohup ./scripts/start-development.sh > /dev/null 2>&1 &

# systemd サービスも使用可能にする（main ブランチからの追加機能）
sudo cp systemd/*.service /etc/systemd/system/ 2>/dev/null || echo "⚠️  systemd ファイルのコピーに失敗（権限不足の可能性）"
sudo systemctl daemon-reload

# サービス開始
sudo systemctl start coordinate-api.service
sudo systemctl start coordinate-camera.service 2>/dev/null || echo "⚠️  camera サービス起動失敗（カメラなしの場合は正常）"
sudo systemctl start coordinate-ui.service 2>/dev/null || echo "⚠️  ui サービス起動失敗（UI なしの場合は正常）"

# 自動起動有効化
sudo systemctl enable coordinate-api.service
sudo systemctl enable coordinate-camera.service 2>/dev/null || true
sudo systemctl enable coordinate-ui.service 2>/dev/null || true

echo "⏱️  systemd サービス起動待機 (120秒 - カメラ初期化対応)"
sleep 120

# サービス状態確認
echo "📊 サービス状態確認："
sudo systemctl is-active coordinate-api.service || echo "❌ API サービス未起動"
sudo systemctl is-active coordinate-camera.service || echo "⚠️  Camera サービス未起動"
sudo systemctl is-active coordinate-ui.service || echo "⚠️  UI サービス未起動"

echo "✅ デプロイ完了"
EOF

    print_success "デプロイ完了"
}

# 動作確認
verify_deployment() {
    print_info "デプロイ後の動作確認中..."

    ssh "${PRODUCTION_USER}@${PRODUCTION_HOST}" << 'EOF'
echo "🔍 動作確認開始"

# API サーバー確認
echo "API サーバー (http://localhost:8000/health):"
if curl -f -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ API サーバー正常"
else
    echo "❌ API サーバー異常"
fi

# Camera サーバー確認（初期化時間を考慮して複数回試行）
echo "Camera サーバー (http://localhost:8001/health):"
camera_ready=false
for attempt in {1..5}; do
    if curl -f -s http://localhost:8001/health > /dev/null 2>&1; then
        echo "✅ Camera サーバー正常 (attempt $attempt/5)"
        camera_ready=true
        break
    else
        echo "⏳ Camera サーバー確認中... (attempt $attempt/5)"
        sleep 10
    fi
done

if [ "$camera_ready" != true ]; then
    echo "⚠️ Camera サーバー異常またはまだ初期化中"
fi

# AI 検出エンドポイント確認
echo "AI 検出エンドポイント (http://localhost:8000/api/v2/ai/detect): 手動で POST テストを実施してください"

echo "🔍 動作確認完了"
EOF

    print_success "動作確認完了"
}

# ロールバック実行
rollback_deployment() {
    print_info "ロールバック開始..."

    # 最新のバックアップを探す
    LATEST_BACKUP=$(ssh "${PRODUCTION_USER}@${PRODUCTION_HOST}" "ls -t /home/pi/coordinate-recorder-backup-* 2>/dev/null | head -1")

    if [ -z "$LATEST_BACKUP" ]; then
        print_error "利用可能なバックアップが見つかりません"
        exit 1
    fi

    print_info "最新のバックアップを使用: $LATEST_BACKUP"

    ssh "${PRODUCTION_USER}@${PRODUCTION_HOST}" << EOF
set -euo pipefail

echo "🛑 現在のサービス停止"
cd "${PRODUCTION_PATH}"
# 新しいファイル名を使用（Issue #622 対応）
./scripts/stop-development.sh 2>/dev/null || echo "サービス停止スクリプトがない、または既に停止済"

# systemd サービスも停止（main ブランチからの追加機能）
sudo systemctl stop coordinate-api.service 2>/dev/null || echo "API サービス既に停止済"
sudo systemctl stop coordinate-camera.service 2>/dev/null || echo "Camera サービス既に停止済"
sudo systemctl stop coordinate-ui.service 2>/dev/null || echo "UI サービス既に停止済"

echo "🔄 バックアップからの復元"
rm -rf "${PRODUCTION_PATH}"
cp -r "${LATEST_BACKUP}" "${PRODUCTION_PATH}"

echo "🚀 サービス再起動"
cd "${PRODUCTION_PATH}"
# 新しいファイル名を使用（Issue #622 対応）
./scripts/start-development.sh

# systemd サービスファイルの更新（main ブランチからの追加機能）
sudo cp systemd/*.service /etc/systemd/system/ 2>/dev/null || echo "⚠️  systemd ファイルのコピーに失敗（権限不足の可能性）"
sudo systemctl daemon-reload

# systemd サービス開始も可能にする
sudo systemctl start coordinate-api.service
sudo systemctl start coordinate-camera.service 2>/dev/null || echo "⚠️  camera サービス起動失敗（カメラなしの場合は正常）"
sudo systemctl start coordinate-ui.service 2>/dev/null || echo "⚠️  ui サービス起動失敗（UI なしの場合は正常）"

echo "✅ ロールバック完了"
EOF

    print_success "ロールバック完了"
}

# メイン処理
main() {
    # デフォルト値
    DRY_RUN=false
    NO_BACKUP=false
    COMMAND=""
    DEPLOY_BRANCH="main"

    # 引数解析
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --no-backup)
                NO_BACKUP=true
                shift
                ;;
            --branch)
                DEPLOY_BRANCH="$2"
                shift 2
                ;;
            deploy|deploy-force|backup|status|rollback)
                COMMAND="$1"
                shift
                ;;
            *)
                print_error "不明なオプション: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # コマンドが指定されていない場合
    if [ -z "$COMMAND" ]; then
        print_error "コマンドが指定されていません"
        show_help
        exit 1
    fi

    # force デプロイの場合はバックアップを無効化
    if [ "$COMMAND" = "deploy-force" ]; then
        NO_BACKUP=true
        COMMAND="deploy"
    fi

    print_info "統一デプロイスクリプト実行開始 - Issue #246"
    print_info "対象: ${PRODUCTION_HOST}"
    print_info "コマンド: ${COMMAND}"

    # 接続確認
    check_production_connection

    # コマンド実行
    case $COMMAND in
        deploy)
            create_backup
            deploy_to_production
            verify_deployment
            ;;
        backup)
            create_backup
            ;;
        status)
            check_production_status
            ;;
        rollback)
            rollback_deployment
            verify_deployment
            ;;
        *)
            print_error "不明なコマンド: $COMMAND"
            exit 1
            ;;
    esac

    print_success "統一デプロイスクリプト実行完了"

    # 通知音
    afplay /System/Library/Sounds/Sosumi.aiff 2>/dev/null || true
}

# スクリプト実行
main "$@"
