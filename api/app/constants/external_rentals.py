"""Constants for external rental integrations."""

from decimal import Decimal

# 月額プラン費用 example_rental (税込み)
EXAMPLE_RENTAL_MONTHLY_PLAN_JPY = Decimal("9999")

# 1 ヶ月あたりの日数換算に使用（UI 側での補助向け）
EXAMPLE_RENTAL_BILLING_CYCLE_DAYS = 30

__all__ = [
    "EXAMPLE_RENTAL_MONTHLY_PLAN_JPY",
    "EXAMPLE_RENTAL_BILLING_CYCLE_DAYS",
]
