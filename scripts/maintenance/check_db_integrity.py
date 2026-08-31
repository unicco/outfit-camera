#!/usr/bin/env python3
"""
本番環境のデータベース整合性チェックスクリプト
alembic_version テーブルと実際のマイグレーションファイルの整合性を確認
"""
import os
import sys
import subprocess
from pathlib import Path

def check_local_migrations():
    """ローカルのマイグレーションファイルをチェック"""
    print("=== ローカルマイグレーションファイル ===")
    migrations_dir = Path("api/alembic/versions")
    migration_files = list(migrations_dir.glob("*.py"))
    
    issues = []
    for file in migration_files:
        if file.name == "__pycache__":
            continue
        
        # ファイル名から revision ID を抽出
        revision_id = file.name.split('_')[0]
        
        # ファイル内の revision 変数を確認
        with open(file, 'r') as f:
            content = f.read()
            for line in content.split('\n'):
                if line.startswith('revision = '):
                    if '"' in line:
                        file_revision = line.split('"')[1]
                    else:
                        file_revision = line.split('=')[1].strip().strip("'")
                    print(f"ファイル: {file.name}")
                    print(f"  ファイル名ID: {revision_id}")
                    print(f"  revision変数: {file_revision}")
                    
                    # ID の長さチェック
                    if len(file_revision) > 32:
                        issues.append(f"  ⚠️  警告: revision '{file_revision}' が32文字を超えています ({len(file_revision)}文字)")
                    
                    # ファイル名とrevision変数の一致チェック
                    if revision_id != file_revision:
                        issues.append(f"  ⚠️  警告: ファイル名ID '{revision_id}' と revision変数 '{file_revision}' が一致しません")
                    
                    break
    
    if issues:
        print("\n発見された問題:")
        for issue in issues:
            print(issue)
    else:
        print("\n✅ ローカルマイグレーションファイルに問題はありません")

def generate_ssh_check_script():
    """本番環境で実行するチェックスクリプトを生成"""
    script_content = '''#!/bin/bash
echo "=== 本番環境データベース整合性チェック ==="
echo ""

# 環境変数を読み込み
cd ~/coordinate-recorder
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# alembic_version テーブルの内容を確認
echo "=== alembic_version テーブルの内容 ==="
export PGPASSWORD="${DB_PASSWORD}"
psql -h "${DB_HOST}" -p "${DB_PORT:-5432}" -U "${DB_USER}" -d "${DB_NAME}" -c "SELECT version_num, LENGTH(version_num) as length FROM alembic_version ORDER BY version_num;" 2>/dev/null || echo "alembic_version テーブルが見つかりません"

echo ""
echo "=== マイグレーションファイル一覧 ==="
cd ~/coordinate-recorder/api
ls -la alembic/versions/*.py 2>/dev/null | grep -v __pycache__ | while read -r line; do
    if [[ "$line" == *.py ]]; then
        filename=$(echo "$line" | awk '{print $NF}')
        basename=$(basename "$filename")
        revision_id=$(echo "$basename" | cut -d'_' -f1)
        echo "ファイル: $basename (ID: $revision_id)"
    fi
done

echo ""
echo "=== Alembic 履歴 ==="
cd ~/coordinate-recorder/api
source ~/coordinate-recorder/venv/bin/activate
alembic history -v 2>&1 | head -20 || echo "Alembic 履歴の取得に失敗しました"

echo ""
echo "=== 現在の Alembic HEAD ==="
alembic current 2>&1 || echo "現在の状態を取得できませんでした"
'''
    
    with open('/tmp/check_db_integrity.sh', 'w') as f:
        f.write(script_content)
    
    os.chmod('/tmp/check_db_integrity.sh', 0o755)
    print("\n本番環境チェックスクリプトを生成しました: /tmp/check_db_integrity.sh")

if __name__ == "__main__":
    check_local_migrations()
    print("\n" + "="*50 + "\n")
    generate_ssh_check_script()
    
    print("本番環境をチェックするには以下を実行してください:")
    print("scp /tmp/check_db_integrity.sh user@pi-camera.local:/tmp/")
    print("ssh user@pi-camera.local 'bash /tmp/check_db_integrity.sh'")