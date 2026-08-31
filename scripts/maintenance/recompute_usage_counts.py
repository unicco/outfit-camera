#!/usr/bin/env python3
"""Recompute wardrobe usage_count values from recorded outfits.

This maintenance utility scans outfit_items to determine the actual number of
times each clothing item appears in recorded outfits, then updates the
clothing_items.usage_count column to reflect that total.

By default the script runs in dry-run mode and only reports the differences.
Use `--apply` to persist the updates.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

# Ensure project packages are importable before local imports
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "api"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables early so database module picks them up
try:
    from dotenv import load_dotenv

    env_common = PROJECT_ROOT / ".env.common"
    if env_common.exists():
        load_dotenv(env_common)
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
except ImportError:
    pass

from app.database import SessionLocal  # noqa: E402
from app.outfit_models import OutfitItem  # noqa: E402
from app.wardrobe_models import ClothingItem  # noqa: E402


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsageDelta:
    """Represents the difference between stored and expected usage counts."""

    item_id: str
    name: str
    current: int
    expected: int

    @property
    def delta(self) -> int:
        return self.expected - self.current


def _fetch_outfit_usage_counts(db: Session) -> dict[str, int]:
    """Return a mapping of clothing_item_id to recorded outfit occurrences."""
    results = db.execute(
        select(OutfitItem.clothing_item_id, func.count(OutfitItem.id))
        .group_by(OutfitItem.clothing_item_id)
    )
    return {item_id: count for item_id, count in results}


def _find_usage_deltas(db: Session) -> Iterable[UsageDelta]:
    """Yield usage differences for clothing items that need updating."""
    usage_map = _fetch_outfit_usage_counts(db)

    for item in db.scalars(select(ClothingItem)):
        current = item.usage_count or 0
        expected = usage_map.get(item.id, 0)
        if current != expected:
            yield UsageDelta(
                item_id=item.id,
                name=item.name,
                current=current,
                expected=expected,
            )


def recompute_usage_counts(db: Session, apply_changes: bool) -> list[UsageDelta]:
    """Recompute usage_count for every clothing item.

    Args:
        db: Active database session.
        apply_changes: Persist updated counts when True.

    Returns:
        List of UsageDelta entries that were detected (and possibly updated).

    """
    deltas = list(_find_usage_deltas(db))
    if not apply_changes:
        return deltas

    id_to_expected = {delta.item_id: delta.expected for delta in deltas}

    if id_to_expected:
        for item in db.scalars(
            select(ClothingItem).where(ClothingItem.id.in_(id_to_expected.keys()))
        ):
            item.usage_count = id_to_expected[item.id]

    db.commit()
    return deltas


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Recompute clothing_items.usage_count from outfit_items."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the recomputed usage counts. Default is dry-run.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    logger.info("Starting usage_count recomputation (apply=%s)", args.apply)

    with SessionLocal() as session:
        deltas = recompute_usage_counts(session, apply_changes=args.apply)

    if not deltas:
        logger.info("All clothing_items.usage_count values already match outfit records.")
        return

    total_delta = sum(delta.delta for delta in deltas)
    logger.info("Detected %d items with mismatched usage_count values.", len(deltas))
    logger.info("Total delta across items: %+d", total_delta)

    for delta in deltas[:20]:
        logger.info(
            "[%s] %s: usage_count=%d -> %d (Δ %+d)",
            delta.item_id,
            delta.name,
            delta.current,
            delta.expected,
            delta.delta,
        )
    if len(deltas) > 20:
        logger.info("... %d more items omitted from preview.", len(deltas) - 20)

    if args.apply:
        logger.info("Usage counts updated in database.")
    else:
        logger.info("Dry run complete. Re-run with --apply to persist changes.")


if __name__ == "__main__":
    main()
