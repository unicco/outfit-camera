"""date_utils モジュールのテスト."""

from datetime import datetime, date
from coordinate_recorder.date_utils import get_effective_date


DEFAULT_CUTOFF = 7


def test_before_cutoff():
    """切り替え時刻前は前日扱い."""
    # 切り替え時刻直前
    test_datetime = datetime(2025, 8, 20, DEFAULT_CUTOFF - 1, 59, 0)
    effective_date = get_effective_date(test_datetime)
    assert effective_date == date(2025, 8, 19)

    # 深夜帯
    test_datetime = datetime(2025, 8, 20, 0, 0, 0)
    effective_date = get_effective_date(test_datetime)
    assert effective_date == date(2025, 8, 19)


def test_after_cutoff():
    """切り替え時刻以降は当日扱い."""
    # 切り替え時刻ちょうど
    test_datetime = datetime(2025, 8, 20, DEFAULT_CUTOFF, 0, 0)
    effective_date = get_effective_date(test_datetime)
    assert effective_date == date(2025, 8, 20)

    # 深夜直前
    test_datetime = datetime(2025, 8, 20, 23, 59, 59)
    effective_date = get_effective_date(test_datetime)
    assert effective_date == date(2025, 8, 20)


def test_daytime():
    """日中は当日扱い."""
    for hour in (12, 17):
        test_datetime = datetime(2025, 8, 20, hour, 0, 0)
        effective_date = get_effective_date(test_datetime)
        assert effective_date == date(2025, 8, 20)


def test_custom_cutoff_hour():
    """カスタム切り替え時刻."""
    # 午前6時を切り替え時刻にした場合
    test_datetime = datetime(2025, 8, 20, 6, 30, 0)

    # デフォルト（7時）では前日扱い
    effective_date = get_effective_date(test_datetime)
    assert effective_date == date(2025, 8, 19)

    # 6時切り替えでは当日扱い
    effective_date = get_effective_date(test_datetime, cutoff_hour=6)
    assert effective_date == date(2025, 8, 20)


def test_none_datetime():
    """reference_datetime が None の場合は現在時刻を使用."""
    # 現在時刻での動作確認（実際の値は確認できないが、エラーが出ないことを確認）
    effective_date = get_effective_date(None)
    assert isinstance(effective_date, date)
