"""JST（日本標準時）統一のためのタイムゾーンユーティリティ.

日本専用サービスのため、すべての時刻をJSTで統一処理する。
- データベース保存: JST
- API 送受信: JST
- UI 表示: JST
"""

from datetime import datetime, timedelta, timezone

import pytz

# JST タイムゾーン定義
JST = pytz.timezone("Asia/Tokyo")
JST_OFFSET = timezone(timedelta(hours=9))


class TimezoneUtils:
    """JST統一処理のためのユーティリティクラス."""

    @staticmethod
    def now_jst() -> datetime:
        """現在のJST時刻を取得（timezone-aware）."""
        return datetime.now(JST)

    @staticmethod
    def now_jst_naive() -> datetime:
        """現在のJST時刻を取得（timezone-naive）."""
        return datetime.now(JST).replace(tzinfo=None)

    @staticmethod
    def to_jst(dt: datetime) -> datetime:
        """任意の時刻をJSTに変換."""
        if dt.tzinfo is None:
            # timezone-naive の場合は JST として扱う
            return JST.localize(dt)
        return dt.astimezone(JST)

    @staticmethod
    def parse_date_as_jst_noon(date_str: str) -> datetime:
        """YYYY-MM-DD文字列をJST正午として解析
        データベース保存用（timezone-aware）.
        """
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            jst_noon = date_obj.replace(hour=12, minute=0, second=0, microsecond=0)
            return JST.localize(jst_noon)
        except ValueError as e:
            raise ValueError(
                f"Invalid date format: {date_str}. Expected YYYY-MM-DD"
            ) from e

    @staticmethod
    def format_jst(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
        """JSTでフォーマットした文字列を返す."""
        jst_dt = TimezoneUtils.to_jst(dt)
        return jst_dt.strftime(format_str)

    @staticmethod
    def format_jst_date(dt: datetime) -> str:
        """JST日付を YYYY-MM-DD 形式で返す."""
        return TimezoneUtils.format_jst(dt, "%Y-%m-%d")

    @staticmethod
    def format_jst_datetime(dt: datetime) -> str:
        """JST日時を YYYY-MM-DD HH:MM:SS 形式で返す."""
        return TimezoneUtils.format_jst(dt, "%Y-%m-%d %H:%M:%S")

    @staticmethod
    def format_jst_iso(dt: datetime) -> str:
        """JST日時をISO8601形式で返す."""
        jst_dt = TimezoneUtils.to_jst(dt)
        return jst_dt.isoformat()

    @staticmethod
    def is_same_jst_date(dt1: datetime, dt2: datetime) -> bool:
        """2つの日時が同じJST日付かどうかを判定."""
        jst_dt1 = TimezoneUtils.to_jst(dt1)
        jst_dt2 = TimezoneUtils.to_jst(dt2)
        return jst_dt1.date() == jst_dt2.date()

    @staticmethod
    def get_jst_date_range(date_str: str) -> tuple[datetime, datetime]:
        """YYYY-MM-DD文字列から、その日のJST開始時刻と終了時刻を取得
        データベースクエリでの日付範囲検索用.
        """
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            start = JST.localize(
                date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
            )
            end = JST.localize(
                date_obj.replace(hour=23, minute=59, second=59, microsecond=999999)
            )
            return start, end
        except ValueError as e:
            raise ValueError(
                f"Invalid date format: {date_str}. Expected YYYY-MM-DD"
            ) from e

    @staticmethod
    def validate_timezone_aware(dt: datetime) -> datetime:
        """timezone-aware な datetime を返す
        timezone-naive の場合は JST として扱う.
        """
        if dt.tzinfo is None:
            return JST.localize(dt)
        return dt

    @staticmethod
    def extract_date_part(dt: datetime) -> str:
        """Datetime から日付部分を YYYY-MM-DD 形式で抽出."""
        jst_dt = TimezoneUtils.to_jst(dt)
        return jst_dt.strftime("%Y-%m-%d")


# モデル用のデフォルト関数
def jst_now() -> datetime:
    """SQLAlchemy モデルのデフォルト値用関数."""
    return TimezoneUtils.now_jst()


def jst_now_naive() -> datetime:
    """SQLAlchemy モデルのデフォルト値用関数（timezone-naive）."""
    return TimezoneUtils.now_jst_naive()


# レガシー対応用のエイリアス
def now_jst() -> datetime:
    """既存コードとの互換性のため."""
    return TimezoneUtils.now_jst()


# JST統一のための定数エクスポート
__all__ = [
    "TimezoneUtils",
    "JST",
    "JST_OFFSET",
    "jst_now",
    "jst_now_naive",
    "now_jst",
]
