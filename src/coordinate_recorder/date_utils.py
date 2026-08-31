"""日付関連のユーティリティ関数."""

from datetime import date, datetime, timedelta


def get_effective_date(
    reference_datetime: datetime = None, cutoff_hour: int = 7
) -> date:
    """午前7時を日付の切り替え時刻として、実効的な日付を返す.

    Args:
        reference_datetime: 基準となる日時（Noneの場合は現在時刻）
        cutoff_hour: 日付切り替え時刻（デフォルト: 7時 = 午前7時）

    Returns:
        実効的な日付（午前7時前は前日扱い）

    """
    if reference_datetime is None:
        reference_datetime = datetime.now()

    if reference_datetime.hour < cutoff_hour:
        # 切り替え時刻前なら前日扱い
        return reference_datetime.date() - timedelta(days=1)
    else:
        # 切り替え時刻以降なら当日
        return reference_datetime.date()
