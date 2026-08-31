"""Wardrobe analytics API endpoints."""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from ..database import get_db
from ..wardrobe_models import ClothingCategory, ClothingItem, ClothingStatus
from ..outfit_models import OutfitItem, OutfitRecord
from ..utils.timezone_utils import TimezoneUtils

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/wardrobe", tags=["wardrobe-analytics"])


@router.get("/analytics/stats")
async def get_wardrobe_statistics(db: Session = Depends(get_db)) -> dict:
    """Get wardrobe statistics for dashboard."""
    # Get total items count
    total_items = (
        db.query(ClothingItem)
        .filter(ClothingItem.status == ClothingStatus.ACTIVE)
        .count()
    )

    # Get category counts
    category_counts = {}
    for category in ClothingCategory:
        count = (
            db.query(ClothingItem)
            .filter(
                ClothingItem.category == category,
                ClothingItem.status == ClothingStatus.ACTIVE,
            )
            .count()
        )
        if count > 0:
            category_counts[category.value] = count

    # Get recently added items (last 30 days)
    thirty_days_ago = TimezoneUtils.now_jst_naive() - timedelta(days=30)
    recently_added = (
        db.query(ClothingItem)
        .filter(
            ClothingItem.created_at >= thirty_days_ago,
            ClothingItem.status == ClothingStatus.ACTIVE,
        )
        .count()
    )

    # Calculate average price
    avg_price_result = (
        db.query(func.avg(ClothingItem.purchase_price))
        .filter(
            ClothingItem.status == ClothingStatus.ACTIVE,
            ClothingItem.purchase_price.isnot(None),
        )
        .scalar()
    )

    average_price = round(avg_price_result) if avg_price_result else 0

    return {
        "totalItems": total_items,
        "categories": category_counts,
        "recentlyAdded": recently_added,
        "averagePrice": average_price,
    }


@router.get("/analytics/detailed")
async def get_detailed_wardrobe_analytics(
    time_range: str = Query(
        "all",
        description="Time range: all, year, 6months, 3months, month",
        alias="range",
    ),
    db: Session = Depends(get_db),
) -> dict:
    """Get detailed wardrobe analytics data."""
    try:
        # Calculate date filter based on time_range
        date_filter = None
        if time_range == "year":
            date_filter = TimezoneUtils.now_jst_naive() - timedelta(days=365)
        elif time_range == "6months":
            date_filter = TimezoneUtils.now_jst_naive() - timedelta(days=180)
        elif time_range == "3months":
            date_filter = TimezoneUtils.now_jst_naive() - timedelta(days=90)
        elif time_range == "month":
            date_filter = TimezoneUtils.now_jst_naive() - timedelta(days=30)

        # Base query for items
        base_query = db.query(ClothingItem).filter(
            ClothingItem.status.in_([ClothingStatus.ACTIVE, ClothingStatus.DISPOSED])
        )

        if date_filter:
            base_query = base_query.filter(ClothingItem.created_at >= date_filter)

        total_wear_expr = func.coalesce(
            ClothingItem.default_usage_count, 0
        ) + func.coalesce(ClothingItem.usage_count, 0)

        # Use SQL aggregation for better performance
        stats_query = db.query(
            func.count(case((ClothingItem.status == ClothingStatus.ACTIVE, 1))).label(
                "active_count"
            ),
            func.count(case((ClothingItem.status == ClothingStatus.DISPOSED, 1))).label(
                "disposed_count"
            ),
            func.sum(
                case(
                    (
                        ClothingItem.status == ClothingStatus.ACTIVE,
                        ClothingItem.purchase_price,
                    ),
                    else_=0,
                )
            ).label("total_value"),
            func.sum(
                case(
                    (
                        ClothingItem.status == ClothingStatus.ACTIVE,
                        total_wear_expr,
                    ),
                    else_=0,
                )
            ).label("total_wears"),
        ).filter(
            ClothingItem.status.in_([ClothingStatus.ACTIVE, ClothingStatus.DISPOSED])
        )

        if date_filter:
            stats_query = stats_query.filter(ClothingItem.created_at >= date_filter)

        stats = stats_query.first()

        total_items = stats.active_count or 0
        stored_items = stats.disposed_count or 0
        total_value = float(stats.total_value or 0)
        total_wears = int(stats.total_wears or 0)
        average_wears_per_item = total_wears / total_items if total_items > 0 else 0
        average_cost_per_wear = total_value / total_wears if total_wears > 0 else 0

        # Find most and least worn items using SQL
        most_worn_query = (
            base_query.filter(
                ClothingItem.status == ClothingStatus.ACTIVE,
                total_wear_expr > 0,
            )
            .order_by(total_wear_expr.desc())
            .first()
        )

        least_worn_query = (
            base_query.filter(ClothingItem.status == ClothingStatus.ACTIVE)
            .order_by(total_wear_expr.asc())
            .first()
        )

        most_worn = most_worn_query
        least_worn = least_worn_query

        overview = {
            "total_items": total_items,
            "active_items": total_items,
            "stored_items": stored_items,
            "total_value": total_value,
            "total_wears": total_wears,
            "average_cost_per_wear": average_cost_per_wear,
            "average_wears_per_item": average_wears_per_item,
            "most_worn_item": (
                {
                    "id": most_worn.id,
                    "name": most_worn.name,
                    "wear_count": int(
                        (most_worn.default_usage_count or 0)
                        + (most_worn.usage_count or 0)
                    ),
                }
                if most_worn
                else {"id": "", "name": "なし", "wear_count": 0}
            ),
            "least_worn_item": (
                {
                    "id": least_worn.id,
                    "name": least_worn.name,
                    "wear_count": int(
                        (least_worn.default_usage_count or 0)
                        + (least_worn.usage_count or 0)
                    ),
                }
                if least_worn
                else {"id": "", "name": "なし", "wear_count": 0}
            ),
        }

        # Category breakdown using SQL aggregation
        category_query = db.query(
            ClothingItem.category,
            func.count(ClothingItem.id).label("count"),
            func.sum(ClothingItem.purchase_price).label("value"),
            func.sum(total_wear_expr).label("wear_count"),
        ).filter(ClothingItem.status == ClothingStatus.ACTIVE)

        if date_filter:
            category_query = category_query.filter(
                ClothingItem.created_at >= date_filter
            )

        category_query = category_query.group_by(ClothingItem.category)

        category_results = category_query.all()

        category_breakdown = []
        for result in category_results:
            cat = result.category.value if result.category else "その他"
            count = result.count or 0
            value = float(result.value or 0)
            wear_count = int(result.wear_count or 0)
            percentage = round((count / total_items * 100), 1) if total_items > 0 else 0
            cost_per_wear = value / wear_count if wear_count > 0 else 0

            category_breakdown.append(
                {
                    "category": cat,
                    "count": count,
                    "value": value,
                    "wear_count": wear_count,
                    "cost_per_wear": cost_per_wear,
                    "percentage": percentage,
                }
            )

        # Wear frequency by month based on outfit records
        wear_records_query = db.query(OutfitRecord.recorded_at).join(
            OutfitItem, OutfitRecord.id == OutfitItem.outfit_record_id
        )

        if date_filter:
            wear_records_query = wear_records_query.filter(
                OutfitRecord.recorded_at >= date_filter
            )

        wear_records = wear_records_query.all()

        wear_counts_by_month: Dict[str, int] = {}
        for (recorded_at,) in wear_records:
            if not recorded_at:
                continue
            jst_recorded = TimezoneUtils.to_jst(recorded_at)
            month_key = jst_recorded.strftime("%Y-%m")
            wear_counts_by_month[month_key] = wear_counts_by_month.get(month_key, 0) + 1

        def month_start(dt: datetime) -> datetime:
            jst_dt = TimezoneUtils.to_jst(dt)
            return jst_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        def previous_month(dt: datetime) -> datetime:
            first_day = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            previous = first_day - timedelta(days=1)
            return previous.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        end_month = month_start(TimezoneUtils.now_jst())
        months: List[datetime] = []

        if date_filter:
            start_month = month_start(date_filter)
            current_month = end_month
            while True:
                months.append(current_month)
                if (
                    current_month.year == start_month.year
                    and current_month.month == start_month.month
                ):
                    break
                current_month = previous_month(current_month)
        else:
            current_month = end_month
            for _ in range(12):
                months.append(current_month)
                current_month = previous_month(current_month)

        months.reverse()

        wear_frequency = [
            {
                "month": month.strftime("%Y-%m"),
                "wear_count": wear_counts_by_month.get(month.strftime("%Y-%m"), 0),
            }
            for month in months
        ]

        # Cost analysis - reuse category breakdown data
        cost_by_category = []
        for cat_data in category_breakdown:
            cost_per_wear = cat_data["cost_per_wear"]
            cost_by_category.append(
                {
                    "category": cat_data["category"],
                    "total_cost": cat_data["value"],
                    "average_cost": (
                        cat_data["value"] / cat_data["count"]
                        if cat_data["count"] > 0
                        else 0
                    ),
                    "cost_per_wear": cost_per_wear,
                }
            )

        # Brand analysis using SQL aggregation
        brand_query = db.query(
            func.coalesce(ClothingItem.brand, "ノーブランド").label("brand"),
            func.count(ClothingItem.id).label("item_count"),
            func.sum(ClothingItem.purchase_price).label("total_cost"),
        ).filter(ClothingItem.status == ClothingStatus.ACTIVE)

        if date_filter:
            brand_query = brand_query.filter(ClothingItem.created_at >= date_filter)

        brand_query = brand_query.group_by(ClothingItem.brand)
        brand_query = brand_query.order_by(func.sum(ClothingItem.purchase_price).desc())
        brand_query = brand_query.limit(10)

        brand_results = brand_query.all()

        cost_by_brand = []
        for result in brand_results:
            total_cost = float(result.total_cost or 0)
            item_count = result.item_count or 0
            average_cost = total_cost / item_count if item_count > 0 else 0

            cost_by_brand.append(
                {
                    "brand": result.brand,
                    "total_cost": total_cost,
                    "item_count": item_count,
                    "average_cost": average_cost,
                }
            )

        # Seasonal usage - need to handle array field properly
        # Get all active items with seasons to analyze
        season_items = db.query(ClothingItem).filter(
            ClothingItem.status == ClothingStatus.ACTIVE
        )

        if date_filter:
            season_items = season_items.filter(ClothingItem.created_at >= date_filter)

        season_items = season_items.all()

        season_stats = {}
        for item in season_items:
            if item.season:
                for season in item.season:
                    if season not in season_stats:
                        season_stats[season] = {"item_count": 0, "wear_count": 0}
                    season_stats[season]["item_count"] += 1
                    total_season_wears = (item.default_usage_count or 0) + (
                        item.usage_count or 0
                    )
                    season_stats[season]["wear_count"] += total_season_wears

        seasonal_usage = [
            {
                "season": season,
                "item_count": stats["item_count"],
                "wear_count": stats["wear_count"],
                "utilization_rate": (
                    stats["wear_count"] / (stats["item_count"] * 10)
                    if stats["item_count"] > 0
                    else 0
                ),  # Assuming 10 wears per season is good utilization
            }
            for season, stats in season_stats.items()
        ]

        # Brand distribution - reuse cost_by_brand data
        brand_distribution = []
        for brand_data in cost_by_brand[:10]:  # Top 10 brands by cost
            count = brand_data["item_count"]
            percentage = round((count / total_items * 100), 1) if total_items > 0 else 0

            brand_distribution.append(
                {"brand": brand_data["brand"], "count": count, "percentage": percentage}
            )

        # Purchase timeline (mock data for now)
        purchase_timeline = [
            {"month": f"{i}月", "count": 0, "value": 0} for i in range(1, 13)
        ]

        return {
            "overview": overview,
            "category_breakdown": category_breakdown,
            "wear_frequency": wear_frequency,
            "cost_analysis": {
                "by_category": cost_by_category,
                "by_brand": cost_by_brand,
            },
            "seasonal_usage": seasonal_usage,
            "brand_distribution": brand_distribution,
            "purchase_timeline": purchase_timeline,
        }
    except Exception as e:
        logger.error(
            f"Error in get_detailed_wardrobe_analytics: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Failed to get analytics data")


@router.get("/analytics/rankings")
async def get_wardrobe_rankings(
    range: str = Query("all", pattern="^(all|year|6months|3months|month)$"),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    """Get various rankings for wardrobe items.

    Args:
        range: Time range filter (all, year, 6months, 3months, month)
        category: Filter by category (optional)
        status: Filter by status (optional)
        limit: Number of items to return per ranking

    """
    start_time = time.time()
    logger.debug(
        f"Starting get_wardrobe_rankings: range={range}, category={category}, status={status}, limit={limit}"
    )
    # Build base query with filters
    query = db.query(ClothingItem).filter(ClothingItem.status == ClothingStatus.ACTIVE)

    # Apply category filter
    if category:
        try:
            category_enum = ClothingCategory(category)
            query = query.filter(ClothingItem.category == category_enum)
        except ValueError:
            pass  # Ignore invalid category

    # Apply status filter
    if status and status != "ACTIVE":
        try:
            status_enum = ClothingStatus(status)
            query = query.filter(ClothingItem.status == status_enum)
        except ValueError:
            pass  # Ignore invalid status

    # Apply date range filter
    if range != "all":
        cutoff_date = datetime.now()
        if range == "year":
            cutoff_date = cutoff_date - timedelta(days=365)
        elif range == "6months":
            cutoff_date = cutoff_date - timedelta(days=180)
        elif range == "3months":
            cutoff_date = cutoff_date - timedelta(days=90)
        elif range == "month":
            cutoff_date = cutoff_date - timedelta(days=30)

        query = query.filter(ClothingItem.purchase_date >= cutoff_date)

    # Note: We don't need to get all items anymore since we use SQL queries for rankings

    # Calculate rankings using SQL for better performance
    total_wear_expr = func.coalesce(
        ClothingItem.default_usage_count, 0
    ) + func.coalesce(ClothingItem.usage_count, 0)

    # 1. Most worn ranking (よく着るランキング)
    query_start = time.time()
    most_worn = (
        query.filter(total_wear_expr > 0)
        .order_by(total_wear_expr.desc())
        .limit(limit)
        .all()
    )
    logger.debug(
        f"Most worn query took {time.time() - query_start:.3f}s (items: {len(most_worn)})"
    )

    # 2. Least worn ranking (着ていないランキング)
    query_start = time.time()
    least_worn = query.order_by(total_wear_expr.asc()).limit(limit).all()
    logger.debug(
        f"Least worn query took {time.time() - query_start:.3f}s (items: {len(least_worn)})"
    )

    # 3. Most expensive ranking (高額ランキング)
    query_start = time.time()
    most_expensive = (
        query.filter(ClothingItem.purchase_price > 0)
        .order_by(ClothingItem.purchase_price.desc())
        .limit(limit)
        .all()
    )
    logger.debug(
        f"Most expensive query took {time.time() - query_start:.3f}s (items: {len(most_expensive)})"
    )

    # 4. Best cost performance ranking (コスパランキング)
    # Calculate cost per wear using SQL
    query_start = time.time()
    best_cost_performance = (
        query.filter(ClothingItem.purchase_price > 0, total_wear_expr > 0)
        .order_by((ClothingItem.purchase_price / total_wear_expr).asc())
        .limit(limit)
        .all()
    )
    logger.debug(
        f"Cost performance query took {time.time() - query_start:.3f}s (items: {len(best_cost_performance)})"
    )

    # Format response
    def format_item_ranking(item: ClothingItem, additional_data: dict = None) -> dict:
        total_wear_count = (item.default_usage_count or 0) + (item.usage_count or 0)
        cost_per_wear = (
            float(item.purchase_price) / total_wear_count
            if item.purchase_price and total_wear_count > 0
            else None
        )
        data = {
            "id": item.id,
            "name": item.name,
            "category": item.category.value if item.category else None,
            "subcategory": item.subcategory,
            "brand": item.brand,
            "purchase_price": item.purchase_price,
            "default_usage_count": item.default_usage_count or 0,
            "usage_count": item.usage_count or 0,
            "total_wear_count": int(total_wear_count),
            "cost_per_wear": cost_per_wear,
            "purchase_date": (
                item.purchase_date.isoformat() if item.purchase_date else None
            ),
            "last_used_date": (
                item.last_used_date.isoformat() if item.last_used_date else None
            ),
            "image_urls": item.image_urls,
            "colors_palette": item.colors_palette,
        }
        if additional_data:
            data.update(additional_data)
        return data

    # Log timing for each query
    query_start = time.time()
    result = {
        "rankings": {
            "most_worn": [format_item_ranking(item) for item in most_worn],
            "least_worn": [format_item_ranking(item) for item in least_worn],
            "most_expensive": [format_item_ranking(item) for item in most_expensive],
            "best_cost_performance": [
                format_item_ranking(
                    item,
                    {
                        "cost_per_wear": (
                            item.purchase_price
                            / (
                                (item.default_usage_count or 0)
                                + (item.usage_count or 0)
                            )
                            if (
                                (item.default_usage_count or 0)
                                + (item.usage_count or 0)
                            )
                            > 0
                            else 0
                        )
                    },
                )
                for item in best_cost_performance
            ],
        },
        "filters": {
            "range": range,
            "category": category,
            "status": status,
            "limit": limit,
        },
        "total_items": query.filter(
            ClothingItem.status == ClothingStatus.ACTIVE
        ).count(),
    }

    total_time = time.time() - start_time
    logger.debug(f"get_wardrobe_rankings completed in {total_time:.3f}s")
    return result


@router.get("/analytics/category-season-matrix")
async def get_category_season_matrix(db: Session = Depends(get_db)) -> dict:
    """Get a matrix of item counts by category and season."""
    start_time = time.time()
    logger.debug("Starting get_category_season_matrix")

    # Get all active items
    items = (
        db.query(ClothingItem)
        .filter(ClothingItem.status == ClothingStatus.ACTIVE)
        .all()
    )

    # Initialize matrix
    categories = [
        category.value for category in ClothingCategory if category.value != "UNDERWEAR"
    ]
    seasons = ["Spring", "Summer", "Autumn", "Winter"]

    # Create matrix structure
    matrix = {category: {season: 0 for season in seasons} for category in categories}

    # Also track totals
    category_totals = {category: 0 for category in categories}
    season_totals = {season: 0 for season in seasons}

    # Count items
    for item in items:
        if item.category and item.season:
            category_value = item.category.value
            if category_value not in matrix:
                continue
            # season is a list of season names
            if isinstance(item.season, list):
                for season_value in item.season:
                    # Capitalize the season to match our seasons list
                    season_capitalized = (
                        season_value.capitalize()
                        if isinstance(season_value, str)
                        else None
                    )
                    if season_capitalized in seasons:
                        matrix[category_value][season_capitalized] += 1
                        season_totals[season_capitalized] += 1
                # Count item only once per category
                category_totals[category_value] += 1

    # Format response
    formatted_matrix = []
    for category in categories:
        row = {
            "category": category,
            "seasons": matrix[category],
            "total": category_totals[category],
        }
        formatted_matrix.append(row)

    result = {
        "matrix": formatted_matrix,
        "seasonTotals": season_totals,
        "categories": categories,
        "seasons": seasons,
        "totalItems": sum(category_totals.values()),
    }

    total_time = time.time() - start_time
    logger.debug(
        f"get_category_season_matrix completed in {total_time:.3f}s (items: {len(items)})"
    )
    return result


@router.get("/analytics/color-distribution")
async def get_color_distribution(
    category: Optional[str] = Query(None, description="Filter by category"),
    db: Session = Depends(get_db),
) -> dict:
    """Get color distribution across wardrobe items.

    Returns hex colors from VLM detection (vlm_color_hex in colors_palette).
    """
    start_time = time.time()

    query = db.query(ClothingItem).filter(
        ClothingItem.status == ClothingStatus.ACTIVE,
        ClothingItem.colors_palette.isnot(None),
    )
    if category:
        try:
            cat_enum = ClothingCategory(category.upper())
            query = query.filter(ClothingItem.category == cat_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid category: {category}")

    items = query.all()

    # Aggregate colors
    color_counts: Dict[str, int] = {}
    color_by_category: Dict[str, Dict[str, int]] = {}
    total_with_color = 0

    for item in items:
        palette = item.colors_palette
        if not isinstance(palette, dict):
            continue

        hex_color = palette.get("vlm_color_hex")
        if not hex_color:
            # Fallback: first color from palette array
            palette_list = palette.get("palette", [])
            if palette_list and isinstance(palette_list, list):
                hex_color = palette_list[0].get("hex")

        if not hex_color:
            continue

        total_with_color += 1
        hex_lower = hex_color.lower()
        color_counts[hex_lower] = color_counts.get(hex_lower, 0) + 1

        cat_name = (
            item.category.value
            if hasattr(item.category, "value")
            else str(item.category)
        )
        if cat_name not in color_by_category:
            color_by_category[cat_name] = {}
        color_by_category[cat_name][hex_lower] = (
            color_by_category[cat_name].get(hex_lower, 0) + 1
        )

    # Sort by count descending
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)

    total_time = time.time() - start_time
    logger.debug(f"get_color_distribution completed in {total_time:.3f}s")

    return {
        "total_items": len(items),
        "total_with_color": total_with_color,
        "colors": [
            {
                "hex": hex_color,
                "count": count,
                "percentage": (
                    round(count / total_with_color * 100, 1) if total_with_color else 0
                ),
            }
            for hex_color, count in sorted_colors
        ],
        "by_category": {
            cat: sorted(
                [{"hex": h, "count": c} for h, c in colors.items()],
                key=lambda x: x["count"],
                reverse=True,
            )
            for cat, colors in color_by_category.items()
        },
    }
