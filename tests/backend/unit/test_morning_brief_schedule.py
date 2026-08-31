"""morning-brief の Slice 2（その人と会った時のコーデ）のテスト.

`unique_attendees`（純粋関数）と
`_worn_history_by_attendee`（撮影時に記録した photos.attendees から過去コーデを
人別に引く DB クエリ）を検証する。
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, OutfitItem, OutfitRecord, Photo
from app.routers.morning_brief import (
    _MAX_WORN_HISTORY_PER_ATTENDEE,
    _worn_history_by_attendee,
)
from app.services.calendar_ics import unique_attendees
from app.utils.timezone_utils import JST
from app.wardrobe_models import ClothingCategory, ClothingItem, ClothingStatus

# --- unique_attendees ------------------------------------------------------


def test_unique_attendees_dedup_and_order():
    events = [
        {"attendees": ["太郎", "花子"]},
        {"attendees": ["花子", "次郎"]},
        {"attendees": []},
    ]
    assert unique_attendees(events) == ["太郎", "花子", "次郎"]


def test_unique_attendees_empty():
    assert unique_attendees([]) == []


# --- _worn_history_by_attendee 共通フィクスチャ ------------------------------


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _add_outfit_photo(db, photo_id, captured_at, attendees):
    """outfit（衣類 1 点）付きの写真を 1 枚作る."""
    item = ClothingItem(
        name=f"item-{photo_id}",
        category=ClothingCategory.TOPS,
        status=ClothingStatus.ACTIVE,
    )
    db.add(item)
    db.flush()
    photo = Photo(
        id=photo_id,
        filename=f"{photo_id}.jpg",
        file_path=f"/p/{photo_id}.jpg",
        source="upload",
        captured_at=captured_at,
        attendees=attendees,
    )
    db.add(photo)
    record = OutfitRecord(photo_id=photo_id, manual_selection=True)
    db.add(record)
    db.flush()
    db.add(OutfitItem(outfit_record_id=record.id, clothing_item_id=item.id))
    db.commit()
    return photo


# --- _worn_history_by_attendee（today 人別・過去全件）-----------


def test_worn_history_returns_all_past_per_attendee_newest_first(db_session):
    _add_outfit_photo(
        db_session, "p1", JST.localize(datetime(2026, 5, 3, 9, 0)), ["太郎"]
    )
    _add_outfit_photo(
        db_session, "p2", JST.localize(datetime(2026, 5, 8, 9, 0)), ["太郎", "花子"]
    )
    day_start = JST.localize(datetime(2026, 5, 10, 0, 0))

    history = _worn_history_by_attendee(db_session, ["太郎", "花子"], day_start)

    # attendees 順に並び、太郎 は 2 件（新しい順）、花子 は 1 件
    assert [h["name"] for h in history] == ["太郎", "花子"]
    midori = history[0]
    assert [p["captured_date"] for p in midori["photos"]] == [
        "2026-05-08",
        "2026-05-03",
    ]
    assert [p["captured_date"] for p in history[1]["photos"]] == ["2026-05-08"]
    # 各写真に構成アイテムが付く
    assert len(midori["photos"][0]["items"]) == 1


def test_worn_history_excludes_exact_midnight_boundary(db_session):
    # ちょうど day_start（今日の 00:00）の写真は「今日」扱いで除外（フィルタは <）
    _add_outfit_photo(
        db_session, "midnight", JST.localize(datetime(2026, 5, 10, 0, 0)), ["太郎"]
    )
    day_start = JST.localize(datetime(2026, 5, 10, 0, 0))

    assert _worn_history_by_attendee(db_session, ["太郎"], day_start) == [
        {"name": "太郎", "photos": []}
    ]


def test_worn_history_includes_attendee_with_no_records(db_session):
    _add_outfit_photo(
        db_session, "p1", JST.localize(datetime(2026, 5, 3, 9, 0)), ["太郎"]
    )
    day_start = JST.localize(datetime(2026, 5, 10, 0, 0))

    history = _worn_history_by_attendee(db_session, ["太郎", "知らない人"], day_start)

    # 履歴の無い人も空 photos で含める（/today で「まだ記録がありません」を出すため）
    assert [h["name"] for h in history] == ["太郎", "知らない人"]
    assert history[1]["photos"] == []


def test_worn_history_caps_per_attendee(db_session):
    # 上限（_MAX_WORN_HISTORY_PER_ATTENDEE）件でクリップする
    for i in range(_MAX_WORN_HISTORY_PER_ATTENDEE + 5):
        _add_outfit_photo(
            db_session,
            f"p{i}",
            JST.localize(datetime(2026, 4, 1 + i, 9, 0)),
            ["太郎"],
        )
    day_start = JST.localize(datetime(2026, 5, 1, 0, 0))

    history = _worn_history_by_attendee(db_session, ["太郎"], day_start)

    assert len(history[0]["photos"]) == _MAX_WORN_HISTORY_PER_ATTENDEE


def test_worn_history_excludes_today(db_session):
    _add_outfit_photo(
        db_session, "today", JST.localize(datetime(2026, 5, 10, 9, 0)), ["太郎"]
    )
    day_start = JST.localize(datetime(2026, 5, 10, 0, 0))

    history = _worn_history_by_attendee(db_session, ["太郎"], day_start)

    assert history == [{"name": "太郎", "photos": []}]


def test_worn_history_empty_attendees(db_session):
    day_start = JST.localize(datetime(2026, 5, 10, 0, 0))
    assert _worn_history_by_attendee(db_session, [], day_start) == []


# --- _annotate_meet_titles（その人と一緒だった予定名・#463）------------------


def test_annotate_meet_titles_attaches_matched_title(monkeypatch):
    from app.routers import morning_brief as morning_brief_api
    from app.settings import Settings

    worn_history = [
        {
            "name": "太郎",
            "photos": [
                {"photo_id": "p1", "captured_date": "2026-02-03"},
                {"photo_id": "p2", "captured_date": "2026-01-10"},
            ],
        },
        {"name": "bob", "photos": []},
    ]

    def fake_parse(texts, start, end, redact_title_keywords=None):
        # 2026-02-03 は緑を含む予定あり、2026-01-10 は予定なし
        return {"2026-02-03": [{"attendees": ["太郎"], "title": "ランチ"}]}

    monkeypatch.setattr(morning_brief_api, "events_by_date_from_texts", fake_parse)

    morning_brief_api._annotate_meet_titles(
        worn_history, Settings(calendar_ics_urls=["https://x"]), ["ICS-TEXT"]
    )

    assert worn_history[0]["photos"][0]["meet_title"] == "ランチ"
    assert worn_history[0]["photos"][1]["meet_title"] is None


def test_annotate_meet_titles_redacted_is_none(monkeypatch):
    # redaction で title=None の予定しかなければ meet_title も None（出さない）
    from app.routers import morning_brief as morning_brief_api
    from app.settings import Settings

    worn_history = [
        {"name": "太郎", "photos": [{"photo_id": "p1", "captured_date": "2026-02-03"}]}
    ]
    monkeypatch.setattr(
        morning_brief_api,
        "events_by_date_from_texts",
        lambda *a, **k: {"2026-02-03": [{"attendees": ["太郎"], "title": None}]},
    )

    morning_brief_api._annotate_meet_titles(
        worn_history, Settings(calendar_ics_urls=["https://x"]), ["ICS-TEXT"]
    )

    assert worn_history[0]["photos"][0]["meet_title"] is None


def test_annotate_meet_titles_no_texts_noop(monkeypatch):
    # ICS 本文が無ければ（取得失敗等）何もしない
    from app.routers import morning_brief as morning_brief_api
    from app.settings import Settings

    def boom(*a, **k):
        raise AssertionError("should not parse")

    monkeypatch.setattr(morning_brief_api, "events_by_date_from_texts", boom)
    worn_history = [
        {"name": "太郎", "photos": [{"photo_id": "p1", "captured_date": "2026-02-03"}]}
    ]
    morning_brief_api._annotate_meet_titles(
        worn_history, Settings(calendar_ics_urls=["https://x"]), []
    )
    assert "meet_title" not in worn_history[0]["photos"][0]


def test_annotate_meet_titles_no_photos_noop(monkeypatch):
    from app.routers import morning_brief as morning_brief_api
    from app.settings import Settings

    def boom(*a, **k):  # 写真が無ければパースしない
        raise AssertionError("should not parse")

    monkeypatch.setattr(morning_brief_api, "events_by_date_from_texts", boom)
    worn_history = [{"name": "太郎", "photos": []}]
    morning_brief_api._annotate_meet_titles(
        worn_history, Settings(calendar_ics_urls=["https://x"]), ["ICS-TEXT"]
    )
    assert worn_history == [{"name": "太郎", "photos": []}]


# --- _record_today_attendees（撮影時の参加者記録・capture フック）-------------


def test_record_today_attendees_no_config(monkeypatch):
    # _record_today_attendees は関数内で source module から import するため、
    # patch 先は api 名前空間でなく app.settings / app.services.calendar_ics。
    from app import api_shared as api
    from app.settings import Settings

    monkeypatch.setattr(
        "app.settings.get_settings", lambda: Settings(calendar_ics_urls=None)
    )
    assert api._record_today_attendees() is None


def test_record_today_attendees_dedups(monkeypatch):
    from app import api_shared as api
    from app.settings import Settings

    monkeypatch.setattr(
        "app.settings.get_settings",
        lambda: Settings(calendar_ics_urls=["https://x"]),
    )
    monkeypatch.setattr(
        "app.services.calendar_ics.fetch_today_events",
        lambda *a, **k: [{"attendees": ["太郎", "花子"]}, {"attendees": ["太郎"]}],
    )
    assert api._record_today_attendees() == ["太郎", "花子"]


def test_record_today_attendees_failure_isolated(monkeypatch):
    from app import api_shared as api
    from app.settings import Settings

    def boom(*a, **k):
        raise RuntimeError("ICS down")

    monkeypatch.setattr(
        "app.settings.get_settings",
        lambda: Settings(calendar_ics_urls=["https://x"]),
    )
    monkeypatch.setattr("app.services.calendar_ics.fetch_today_events", boom)
    # 取得失敗でも撮影を止めない（None を返すだけ）
    assert api._record_today_attendees() is None
