"""Initial schema aligned with production.

Revision ID: 0001_initial
Revises:
Create Date: 2025-10-04

"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA_ROOT = Path(__file__).resolve().parent.parent / "sql"
SCHEMA_FILE = SCHEMA_ROOT / "0001_initial_schema.sql"


def _load_schema_sql() -> str:
    if not SCHEMA_FILE.exists():
        raise FileNotFoundError(f"Missing schema file: {SCHEMA_FILE}")
    return SCHEMA_FILE.read_text(encoding="utf-8")


def upgrade() -> None:
    """Apply the initial database schema exported from production."""
    op.execute(_load_schema_sql())


def downgrade() -> None:
    """Drop all tables and enums associated with the initial schema."""
    statements = [
        "DROP TABLE IF EXISTS public.search_result_items CASCADE",
        "DROP TABLE IF EXISTS public.search_logs CASCADE",
        "DROP TABLE IF EXISTS public.item_pair_co_occurrences CASCADE",
        "DROP TABLE IF EXISTS public.category_co_occurrences CASCADE",
        "DROP TABLE IF EXISTS public.co_occurrence_learning_stats CASCADE",
        "DROP TABLE IF EXISTS public.daily_outfit_logs CASCADE",
        "DROP TABLE IF EXISTS public.learning_dataset CASCADE",
        "DROP TABLE IF EXISTS public.matching_accuracy_metrics CASCADE",
        "DROP TABLE IF EXISTS public.model_performance_history CASCADE",
        "DROP TABLE IF EXISTS public.outfit_items CASCADE",
        "DROP TABLE IF EXISTS public.outfit_records CASCADE",
        "DROP TABLE IF EXISTS public.detection_results CASCADE",
        "DROP TABLE IF EXISTS public.ai_detection_feedback CASCADE",
        "DROP TABLE IF EXISTS public.clothing_items CASCADE",
        "DROP TABLE IF EXISTS public.photos CASCADE",
    ]
    for stmt in statements:
        op.execute(stmt)
    for enum in (
        "feedbacktype",
        "confidencelevel",
        "clothingstatus",
        "clothingcategory",
    ):
        op.execute("DROP TYPE IF EXISTS public." + enum + " CASCADE")
