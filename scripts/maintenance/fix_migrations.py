#!/usr/bin/env python3
"""
マイグレーションファイルの整合性を修正するスクリプト
"""
import os
import re
from pathlib import Path

def analyze_migrations():
    """マイグレーションファイルを分析して修正案を提示"""
    migrations_dir = Path("api/alembic/versions")
    migration_files = list(migrations_dir.glob("*.py"))
    
    print("=== マイグレーションファイルの分析 ===\n")
    
    issues = []
    for file in sorted(migration_files):
        if file.name == "__pycache__" or file.name == "__init__.py":
            continue
        
        # ファイル名から revision ID を抽出
        filename_parts = file.name.split('_')
        filename_id = filename_parts[0]
        
        # ファイル内容を読む
        with open(file, 'r') as f:
            content = f.read()
        
        # revision 変数を抽出（複数のパターンに対応）
        revision_match = re.search(r'revision[:\s]*=\s*["\']([^"\']+)["\']', content)
        if not revision_match:
            # 型アノテーション付きのパターンを試す
            revision_match = re.search(r'revision:\s*str\s*=\s*["\']([^"\']+)["\']', content)
        if not revision_match:
            print(f"⚠️  {file.name}: revision 変数が見つかりません")
            continue
        
        file_revision = revision_match.group(1)
        
        # down_revision を抽出
        down_revision_match = re.search(r'down_revision[:\s]*=\s*["\']([^"\']+)["\']', content)
        if not down_revision_match:
            down_revision_match = re.search(r'down_revision:\s*Union\[.*\]\s*=\s*["\']([^"\']+)["\']', content)
        down_revision = down_revision_match.group(1) if down_revision_match else "None"
        
        print(f"ファイル: {file.name}")
        print(f"  filename ID: {filename_id}")
        print(f"  revision: {file_revision}")
        print(f"  down_revision: {down_revision}")
        
        # 問題をチェック
        if len(file_revision) > 32:
            issues.append({
                'file': file.name,
                'issue': f'revision が32文字を超えています ({len(file_revision)}文字)',
                'revision': file_revision,
                'filename_id': filename_id
            })
            print(f"  ❌ revision が32文字を超えています")
        
        if filename_id != file_revision:
            # 標準的な Alembic の命名規則（12文字のハッシュ）かチェック
            if len(filename_id) == 12 and re.match(r'^[a-f0-9]{12}$', filename_id):
                print(f"  ✅ 標準的な Alembic 形式")
            else:
                print(f"  ⚠️  filename ID と revision が一致しません")
        
        print()
    
    return issues

def suggest_fixes(issues):
    """修正案を提示"""
    if not issues:
        print("\n✅ 重大な問題は見つかりませんでした")
        return
    
    print("\n=== 修正が必要な問題 ===\n")
    
    for issue in issues:
        print(f"問題のあるファイル: {issue['file']}")
        print(f"問題: {issue['issue']}")
        print(f"現在の revision: {issue['revision']}")
        
        # 問題のあるマイグレーション
        if issue['revision'] == '20250924001_add_search_result_logging':
            print("\n修正案:")
            print("1. このマイグレーションは既に本番DBで '20250924001_add' として記録されています")
            print("2. 新しい環境でのセットアップ時に問題が発生する可能性があります")
            print("3. 以下の対処が必要です:")
            print("   - マイグレーションファイルの revision を '20250924001_add' に変更")
            print("   - または初期セットアップスクリプトで特別な処理を追加")
            
    print("\n=== 推奨される対処 ===")
    print("1. 問題のあるマイグレーションファイルの revision を修正")
    print("2. 本番DBの alembic_version テーブルとの整合性を保つ")
    print("3. 新規環境でのセットアップ手順を文書化")

if __name__ == "__main__":
    issues = analyze_migrations()
    suggest_fixes(issues)