#!/usr/bin/env python3
"""直接 SQL でdetection_results テーブルを作成（Issue #451）
Alembic マイグレーション問題回避のため.
"""

import sys
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.database import SessionLocal
from sqlalchemy import text


def create_detection_results_table() -> None:
    """detection_results テーブルを直接作成."""
    # テーブル作成 SQL
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS detection_results (
        id VARCHAR(36) PRIMARY KEY,
        photo_id VARCHAR(36) NOT NULL,
        detection_type VARCHAR(50) NOT NULL,
        model_name VARCHAR(100) NOT NULL,
        model_version VARCHAR(50),
        detection_results JSON,
        confidence_score FLOAT,
        processing_time_ms FLOAT,
        embedding_vector JSON,
        embedding_dimension INTEGER,
        status VARCHAR(20) NOT NULL DEFAULT 'completed',
        error_message VARCHAR(500),
        cache_hit BOOLEAN NOT NULL DEFAULT FALSE,
        cache_key VARCHAR(255),
        detected_at TIMESTAMP WITH TIME ZONE NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,

        FOREIGN KEY (photo_id) REFERENCES photos(id) ON DELETE CASCADE
    );
    """

    # インデックス作成 SQL
    create_indexes_sql = [
        "CREATE INDEX IF NOT EXISTS idx_detection_results_photo_id ON detection_results (photo_id);",
        "CREATE INDEX IF NOT EXISTS idx_detection_results_photo_type ON detection_results (photo_id, detection_type);",
        "CREATE INDEX IF NOT EXISTS idx_detection_results_detected_at ON detection_results (detected_at);",
        "CREATE INDEX IF NOT EXISTS idx_detection_results_model ON detection_results (model_name, model_version);",
        "CREATE INDEX IF NOT EXISTS idx_detection_results_status ON detection_results (status);",
        "CREATE INDEX IF NOT EXISTS idx_detection_results_cache_key ON detection_results (cache_key);",
    ]

    try:
        with SessionLocal() as db:
            # テーブル作成
            print("🔧 Creating detection_results table...")
            db.execute(text(create_table_sql))

            # インデックス作成
            print("🔧 Creating indexes...")
            for index_sql in create_indexes_sql:
                db.execute(text(index_sql))

            db.commit()
            print("✅ detection_results table and indexes created successfully!")

            # テーブル存在確認
            result = db.execute(text("""
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'detection_results'
                ORDER BY ordinal_position;
            """))

            columns = result.fetchall()
            if columns:
                print(f"✅ Verified table structure: {len(columns)} columns")
                for col in columns[:5]:  # Show first 5 columns
                    print(f"   - {col.column_name}: {col.data_type}")
                if len(columns) > 5:
                    print(f"   ... and {len(columns) - 5} more columns")
            else:
                print("❌ Table creation may have failed - no columns found")

    except Exception as e:
        print(f"❌ Error creating detection_results table: {e}")
        raise


if __name__ == "__main__":
    create_detection_results_table()
