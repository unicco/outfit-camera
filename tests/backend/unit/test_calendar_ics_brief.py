"""朝ブリーフ「今日会う人」の ICS パーサ (app.services.calendar_ics) のテスト.

Issue #287 Phase 1。タイトル末尾 `@名前` の抽出と、今日（JST）の予定だけを
拾う挙動を検証する。ネットワークは叩かず ICS 本文を直接 parse する。
"""

from __future__ import annotations

from datetime import date, datetime

from app.services.calendar_ics import (
    _parse_range,
    _parse_today,
    events_by_date_from_texts,
    events_today_from_texts,
    extract_attendees,
    fetch_attendees_by_date,
    fetch_events_by_date,
    strip_attendee_suffix,
)
from app.utils.timezone_utils import JST


def _today_window(now: datetime):
    now_jst = now.astimezone(JST)
    start = now_jst.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(hour=23, minute=59, second=59)
    return start, end


# --- extract_attendees（規約: calendar-naming-convention.md）-----------------


def test_extract_attendees_multiple():
    assert extract_attendees("ランチ @太郎, 花子") == ["太郎", "花子"]


def test_extract_attendees_single():
    assert extract_attendees("打ち合わせ @太郎") == ["太郎"]


def test_extract_attendees_no_space():
    assert extract_attendees("飲み会 @太郎,花子") == ["太郎", "花子"]


def test_extract_attendees_without_at():
    assert extract_attendees("ジム") is None


def test_extract_attendees_skips_empty():
    assert extract_attendees("ランチ @太郎, , 花子") == ["太郎", "花子"]


def test_extract_attendees_at_per_name_space():
    # 名前ごとに @、空白区切り
    assert extract_attendees("ランチ @bob @alice") == ["bob", "alice"]


def test_extract_attendees_at_per_name_comma():
    # 名前ごとに @、カンマ区切り
    assert extract_attendees("自宅訪問 @bob, @alice") == ["bob", "alice"]


def test_extract_attendees_fullwidth_at_and_comma():
    # 全角 ＠ と全角カンマ
    assert extract_attendees("飲み会 ＠太郎、花子") == ["太郎", "花子"]


def test_extract_attendees_at_in_body_ignored():
    # 本文中の @（直前が非空白）は参加者扱いしない。地名 "代官山@渋谷" 等
    assert extract_attendees("代官山@渋谷の店 @太郎") == ["太郎"]


def test_extract_attendees_at_only():
    assert extract_attendees("ランチ @") is None


def test_strip_attendee_suffix():
    assert strip_attendee_suffix("ランチ @太郎, 花子") == "ランチ"
    assert strip_attendee_suffix("ランチ @bob @alice") == "ランチ"
    assert strip_attendee_suffix("代官山@渋谷の店 @太郎") == "代官山@渋谷の店"
    assert strip_attendee_suffix("ジム") == "ジム"


# --- _parse_today ----------------------------------------------------------


def _ics(*vevents: str) -> str:
    body = "\n".join(vevents)
    return f"BEGIN:VCALENDAR\n{body}\nEND:VCALENDAR\n"


def _vevent(uid: str, summary: str, dtstart: str, extra: str = "") -> str:
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"SUMMARY:{summary}",
        f"DTSTART;TZID=Asia/Tokyo:{dtstart}",
    ]
    if extra:
        lines.append(extra)
    lines.append("END:VEVENT")
    return "\n".join(lines)


def test_parse_today_picks_today_with_attendees():
    now = JST.localize(datetime(2026, 5, 10, 7, 0))
    start, end = _today_window(now)
    text = _ics(
        _vevent("a", "ランチ @太郎, 花子", "20260510T120000"),
        _vevent("b", "明日の予定 @太郎", "20260511T120000"),
    )

    events = _parse_today(text, start, end, [])

    assert len(events) == 1
    ev = events[0]
    assert ev["title"] == "ランチ"
    assert ev["time"] == "12:00"
    assert ev["all_day"] is False
    assert ev["attendees"] == ["太郎", "花子"]


def test_parse_today_unescapes_ics_comma_in_summary():
    # ICS は SUMMARY のカンマを `\,` にエスケープする。アンエスケープしないと
    # 参加者名に "\" が混ざる（@bob\, @alice → bob\）。
    now = JST.localize(datetime(2026, 5, 10, 7, 0))
    start, end = _today_window(now)
    text = _ics(_vevent("z", "自宅訪問 @bob\\, @alice", "20260510T150000"))

    events = _parse_today(text, start, end, [])

    assert events[0]["attendees"] == ["bob", "alice"]
    assert events[0]["title"] == "自宅訪問"


def test_parse_today_all_day_event():
    now = JST.localize(datetime(2026, 5, 10, 7, 0))
    start, end = _today_window(now)
    text = _ics(
        "BEGIN:VEVENT\nUID:c\nSUMMARY:旅行 @次郎\nDTSTART;VALUE=DATE:20260510\nEND:VEVENT"
    )

    events = _parse_today(text, start, end, [])

    assert len(events) == 1
    assert events[0]["all_day"] is True
    assert events[0]["time"] is None
    assert events[0]["attendees"] == ["次郎"]


def test_parse_today_redacts_sensitive_title():
    now = JST.localize(datetime(2026, 5, 10, 7, 0))
    start, end = _today_window(now)
    text = _ics(_vevent("d", "打合せ @三郎", "20260510T100000"))

    events = _parse_today(text, start, end, ["打合せ"])

    assert len(events) == 1
    assert events[0]["title"] == "(予定)"
    assert events[0]["attendees"] == []


def test_parse_today_skips_cancelled():
    now = JST.localize(datetime(2026, 5, 10, 7, 0))
    start, end = _today_window(now)
    text = _ics(_vevent("e", "中止 @太郎", "20260510T120000", extra="STATUS:CANCELLED"))

    assert _parse_today(text, start, end, []) == []


def test_parse_today_expands_recurring_event():
    # 毎週日曜の予定。2026-05-10 は日曜なので当日分が展開される。
    now = JST.localize(datetime(2026, 5, 10, 7, 0))
    start, end = _today_window(now)
    text = _ics(
        _vevent(
            "f",
            "定例 @太郎",
            "20260503T090000",
            extra="RRULE:FREQ=WEEKLY;BYDAY=SU",
        )
    )

    events = _parse_today(text, start, end, [])

    assert len(events) == 1
    assert events[0]["time"] == "09:00"
    assert events[0]["attendees"] == ["太郎"]


def test_parse_today_recurring_with_exdate_cancellation():
    # 今日（2026-05-10 09:00 JST）の回が EXDATE でキャンセルされていれば出さない。
    now = JST.localize(datetime(2026, 5, 10, 7, 0))
    start, end = _today_window(now)
    text = _ics(
        "BEGIN:VEVENT\nUID:g\nSUMMARY:定例 @太郎\n"
        "DTSTART;TZID=Asia/Tokyo:20260503T090000\n"
        "RRULE:FREQ=WEEKLY;BYDAY=SU\n"
        "EXDATE;TZID=Asia/Tokyo:20260510T090000\n"
        "END:VEVENT"
    )

    assert _parse_today(text, start, end, []) == []


def test_parse_today_all_day_event_at_jst_midnight():
    # 深夜（00:30 JST）に評価しても、当日の終日予定を拾えること。
    now = JST.localize(datetime(2026, 5, 10, 0, 30))
    start, end = _today_window(now)
    text = _ics(
        "BEGIN:VEVENT\nUID:h\nSUMMARY:旅行 @次郎\n"
        "DTSTART;VALUE=DATE:20260510\nEND:VEVENT"
    )

    events = _parse_today(text, start, end, [])

    assert len(events) == 1
    assert events[0]["all_day"] is True
    assert events[0]["attendees"] == ["次郎"]


# --- _parse_range（過去 backfill 用・期間展開）-------------------------------


def _range(start: date, end: date):
    return (
        JST.localize(datetime(start.year, start.month, start.day, 0, 0, 0)),
        JST.localize(datetime(end.year, end.month, end.day, 23, 59, 59)),
    )


def test_parse_range_single_event_in_window():
    rs, re_ = _range(date(2026, 2, 1), date(2026, 2, 28))
    text = _ics(_vevent("a", "ランチ @alice", "20260203T120000"))

    assert _parse_range(text, rs, re_) == [("2026-02-03", ["alice"], "ランチ")]


def test_parse_range_excludes_outside_window():
    rs, re_ = _range(date(2026, 2, 1), date(2026, 2, 10))
    text = _ics(_vevent("a", "ランチ @太郎", "20260215T120000"))

    assert _parse_range(text, rs, re_) == []


def test_parse_range_event_without_attendees_skipped():
    rs, re_ = _range(date(2026, 2, 1), date(2026, 2, 28))
    text = _ics(_vevent("a", "ジム", "20260203T120000"))

    assert _parse_range(text, rs, re_) == []


def test_parse_range_no_redaction_for_sensitive_title():
    # _parse_range は redaction をかけない（呼び出し側で判断）。打合せでも参加者・タイトルを返す
    rs, re_ = _range(date(2026, 2, 1), date(2026, 2, 28))
    text = _ics(_vevent("a", "打合せ @三郎", "20260203T100000"))

    assert _parse_range(text, rs, re_) == [("2026-02-03", ["三郎"], "打合せ")]


def test_parse_range_expands_recurring_across_window():
    # 毎週日曜の予定を 1 か月の窓で全展開する。2026-02 の日曜は 1/8/15/22。
    rs, re_ = _range(date(2026, 2, 1), date(2026, 2, 28))
    text = _ics(
        _vevent("f", "定例 @太郎", "20260201T090000", extra="RRULE:FREQ=WEEKLY;BYDAY=SU")
    )

    result = _parse_range(text, rs, re_)
    dates = [d for d, _, _ in result]

    assert dates == ["2026-02-01", "2026-02-08", "2026-02-15", "2026-02-22"]
    assert all(names == ["太郎"] for _, names, _ in result)
    assert all(title == "定例" for _, _, title in result)


def test_parse_range_skips_cancelled():
    rs, re_ = _range(date(2026, 2, 1), date(2026, 2, 28))
    text = _ics(_vevent("e", "中止 @太郎", "20260203T120000", extra="STATUS:CANCELLED"))

    assert _parse_range(text, rs, re_) == []


# --- fetch_attendees_by_date（日付ごとの集約・重複除去）----------------------


def test_fetch_attendees_by_date_aggregates_and_dedups(monkeypatch):
    # 同日に複数予定 → 名前を初出順で一意化して 1 日にまとめる。ネットは monkeypatch。
    text = _ics(
        _vevent("a", "朝会 @太郎, 花子", "20260203T090000"),
        _vevent("b", "夜会 @太郎", "20260203T190000"),
        _vevent("c", "別日 @bob", "20260204T120000"),
    )

    class _Resp:
        def __init__(self, body):
            self.text = body

        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        "app.services.calendar_ics.requests.get", lambda *a, **k: _Resp(text)
    )

    result = fetch_attendees_by_date(
        ["https://example/ics"], date(2026, 2, 1), date(2026, 2, 28)
    )

    assert result == {
        "2026-02-03": ["太郎", "花子"],
        "2026-02-04": ["bob"],
    }


# --- fetch_events_by_date（日付ごとの参加者 + タイトル）----------------------


class _Resp:
    def __init__(self, body):
        self.text = body

    def raise_for_status(self):
        return None


def test_fetch_events_by_date_returns_titles(monkeypatch):
    text = _ics(
        _vevent("a", "ランチ @太郎", "20260203T120000"),
        _vevent("b", "打ち合わせ @bob", "20260203T150000"),
    )
    monkeypatch.setattr(
        "app.services.calendar_ics.requests.get", lambda *a, **k: _Resp(text)
    )

    result = fetch_events_by_date(
        ["https://example/ics"], date(2026, 2, 1), date(2026, 2, 28)
    )

    assert result == {
        "2026-02-03": [
            {"attendees": ["太郎"], "title": "ランチ"},
            {"attendees": ["bob"], "title": "打ち合わせ"},
        ]
    }


def test_fetch_events_by_date_redacts_sensitive_title(monkeypatch):
    # redact キーワードに一致する予定はタイトルを None に（参加者は残す）
    text = _ics(_vevent("a", "打合せ @三郎", "20260203T100000"))
    monkeypatch.setattr(
        "app.services.calendar_ics.requests.get", lambda *a, **k: _Resp(text)
    )

    result = fetch_events_by_date(
        ["https://example/ics"],
        date(2026, 2, 1),
        date(2026, 2, 28),
        redact_title_keywords=["打合せ"],
    )

    assert result == {"2026-02-03": [{"attendees": ["三郎"], "title": None}]}


# --- 取得済テキストからの派生（ICS 1 回取得で使い回す・#463 速度改善）---------


def test_events_today_from_texts():
    # 取得済 ICS 本文から今日の予定を組み立てる（ネット非依存）
    now = JST.localize(datetime(2026, 5, 10, 7, 0))
    text = _ics(
        _vevent("a", "ランチ @太郎", "20260510T120000"),
        _vevent("b", "明日 @太郎", "20260511T120000"),
    )

    events = events_today_from_texts([text], now=now)

    assert len(events) == 1
    assert events[0]["title"] == "ランチ"
    assert events[0]["attendees"] == ["太郎"]


def test_events_by_date_from_texts():
    text = _ics(_vevent("a", "ランチ @太郎", "20260203T120000"))

    result = events_by_date_from_texts([text], date(2026, 2, 1), date(2026, 2, 28))

    assert result == {"2026-02-03": [{"attendees": ["太郎"], "title": "ランチ"}]}
