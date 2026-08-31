"""Morning brief API — 玄関ディスプレイの起床ブリーフ画面用エンドポイント.

Issue #424: 起床時に「今日の天気・傘・気温が近い過去のコーデ例」を 1 画面に出す。
Pi の起動直後の短い表示窓で 1 回叩けば全部揃うよう、天気・ヒーロー写真・構成
アイテムを 1 レスポンスにまとめる。
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import exists
from sqlalchemy.orm import Session, load_only

from ..auth import AuthenticatedActor, require_external_rental_auth
from ..dependencies import get_db
from ..models import OutfitItem, OutfitRecord, Photo
from ..storage.storage_factory import get_storage_handler
from ..wardrobe_models import ClothingItem
from ..services.calendar_ics import (
    events_by_date_from_texts,
    events_today_from_texts,
    fetch_ics_texts,
    unique_attendees,
)
from ..services.environment import WeatherService
from ..settings import Settings, get_settings
from ..utils.timezone_utils import jst_now

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2", tags=["morning-brief"])


def _hero_photo_url(photo_id: str) -> Optional[str]:
    """hero 写真の公開 URL を返す（取れなければ None）.

    本番（GCS）では公開 URL（CF Access 不要・署名不要）を返すため、HA push の
    `image` やスマホ詳細ページ（/today）がそのまま読める。まず get_storage_handler()
    に委譲する（UUID 形式の新しい写真はこれで通る）。

    旧い写真 ID（UUID 非準拠の `photo_YYYYMMDD_HHMMSS` 等）は get_photo_url の
    UUID バリデーションで弾かれるが、実体は GCS に公開保存されているので、バケットから
    直接 URL を組んで表示できるようにする（photo_id は DB 由来で信頼でき、念のため
    安全な文字種だけ許可）。GCS 以外（ローカル開発）や不正な ID は None。
    """
    try:
        return get_storage_handler().get_photo_url(photo_id)
    except Exception:
        handler = get_storage_handler()
        bucket = getattr(handler, "bucket_name", None)
        pid = photo_id.split(".")[0]
        if bucket and re.fullmatch(r"[A-Za-z0-9_\-]+", pid):
            return f"https://storage.googleapis.com/{bucket}/photos/{pid}.jpg"
        logger.warning("Could not build hero photo URL for photo_id=%s", photo_id)
        return None


def _pick_image_url(image_urls: Any) -> Optional[str]:
    """ClothingItem.image_urls から正方形表示に使う 1 枚の URL を選ぶ.

    保存形式が dict（thumbnails 付き）/ list の両方を想定して正規化する。
    """
    if isinstance(image_urls, dict):
        thumbs = image_urls.get("thumbnails") or {}
        return (
            thumbs.get("thumb_200")
            or thumbs.get("thumb_400")
            or image_urls.get("original")
            or image_urls.get("url")
        )
    if isinstance(image_urls, list) and image_urls:
        first = image_urls[0]
        if isinstance(first, dict):
            return first.get("thumb_200") or first.get("original") or first.get("url")
        if isinstance(first, str):
            return first
    return None


def _hero_items(db: Session, photo_id: str) -> List[Dict[str, Any]]:
    """ヒーロー写真の構成アイテム（衣類）を id 重複を除いて返す."""
    rows = (
        db.query(ClothingItem)
        .join(OutfitItem, OutfitItem.clothing_item_id == ClothingItem.id)
        .join(OutfitRecord, OutfitRecord.id == OutfitItem.outfit_record_id)
        .filter(OutfitRecord.photo_id == photo_id)
        .all()
    )

    items: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for ci in rows:
        cid = str(ci.id)
        if cid in seen:
            continue
        seen.add(cid)
        items.append(
            {
                "id": cid,
                "name": ci.name,
                "category": ci.category.value if ci.category else "OTHER",
                "image_url": _pick_image_url(ci.image_urls),
            }
        )
    return items


# /today の人別セクションで 1 人あたりに出す過去コーデの最大件数。
# 着衣被り回避は直近を見れば足りる。写真ごとに _hero_items を引く（写真数だけ追加
# クエリが出る）ので、件数を絞ってレスポンス肥大と追加クエリ総数を抑える。
_MAX_WORN_HISTORY_PER_ATTENDEE = 10


def _worn_history_by_attendee(
    db: Session, attendees: List[str], day_start: Any
) -> List[Dict[str, Any]]:
    """今日会う人ごとに「その人と会った日の過去コーデ全件」を新しい順で引く.

    撮影時に photos.attendees へ記録した履歴から、今日より前の outfit 写真を人ごとに
    まとめる。/today の人別セクション用。1 人あたり最大 _MAX_WORN_HISTORY_PER_ATTENDEE 件。
    過去バックフィル（scripts/maintenance/backfill_photo_attendees.py）で遡って埋められる。

    Returns:
        attendees の順に並んだ [{"name": str, "photos": [outfit, ...]}, ...]。
        履歴の無い人も photos=[] で含める（/today で「該当なし」を空表示するため）。
        dict でなく list なのは、apiClient の camelCase 変換が人名キー（日本語・スペース
        含み得る）を壊さないようにするため。
    """
    if not attendees:
        return []

    # 今日より前の outfit 付き・attendees 記録あり写真を新しい順に少数だけ取る
    # （1 日 1 枚程度なので 200 件 ≒ 直近 200 日で十分遡れる。JSON 包含は DB 非依存に
    # Python 側で判定する）。load_only で必要列だけ読む（embedding_vector 等の巨大 JSON を
    # 200 件ぶんデシリアライズすると数秒かかるため・ 速度改善）
    has_outfit = exists().where(OutfitRecord.photo_id == Photo.id)
    candidates = (
        db.query(Photo)
        .options(
            load_only(Photo.id, Photo.captured_at, Photo.attendees, Photo.deleted_at)
        )
        .filter(
            Photo.deleted_at.is_(None),
            has_outfit,
            Photo.attendees.isnot(None),
            Photo.captured_at < day_start,
        )
        .order_by(Photo.captured_at.desc())
        .limit(200)
        .all()
    )

    result: List[Dict[str, Any]] = []
    for name in attendees:
        photos: List[Dict[str, Any]] = []
        for photo in candidates:
            if len(photos) >= _MAX_WORN_HISTORY_PER_ATTENDEE:
                break
            if photo.attendees and name in photo.attendees:
                captured = photo.captured_at
                pid = str(photo.id)
                photos.append(
                    {
                        "photo_id": pid,
                        "photo_url": _hero_photo_url(pid),
                        "captured_date": (
                            captured.date().isoformat() if captured else None
                        ),
                        "items": _hero_items(db, pid),
                    }
                )
        result.append({"name": name, "photos": photos})
    return result


def _annotate_meet_titles(
    worn_history: List[Dict[str, Any]],
    settings: Settings,
    ics_texts: List[str],
) -> None:
    """worn_history の各写真に「その日その人と一緒だった予定名」を付ける（#463）.

    撮影日の ICS から、その人を含む予定のタイトルを引いて `meet_title` に入れる。
    タイトルは DB に保存していないので ICS から引く。ICS 本文は呼び出し側が 1 回取得して
    渡す（fetch_today_events と二重 fetch しないため・#463 速度改善）。パース失敗でも
    worn_history 自体は壊さないよう、ここで握りつぶす。
    """
    dates = [
        p["captured_date"]
        for entry in worn_history
        for p in entry["photos"]
        if p["captured_date"]
    ]
    if not dates or not ics_texts:
        return

    try:
        events_by_date = events_by_date_from_texts(
            ics_texts,
            date.fromisoformat(min(dates)),
            date.fromisoformat(max(dates)),
            redact_title_keywords=settings.calendar_redact_title_keywords,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to parse event titles for worn history: %s", exc)
        return

    for entry in worn_history:
        name = entry["name"]
        for photo in entry["photos"]:
            events = events_by_date.get(photo["captured_date"], [])
            # その人を含む予定のうち、タイトルがある最初のものを採用。
            # センシティブ予定は fetch 側で title=None なので meet_title も None（出さない）
            photo["meet_title"] = next(
                (
                    ev["title"]
                    for ev in events
                    if name in ev["attendees"] and ev["title"]
                ),
                None,
            )


def _build_schedule(db: Session, settings: Settings) -> Dict[str, Any]:
    """今日の予定の参加者（`@名前`）＋前回その人と会った時のコーデを組み立てる.

    Issue #287 Phase 1/Slice 2。schedule は補助情報なので、ICS 取得・DB クエリの
    どこで失敗してもブリーフ全体（天気・hero）を壊さないよう、構築全体を try で囲んで
    空の schedule を返す（#463: 旧実装は DB クエリが try の外にあり、参加者がいる日に
    過去コーデ取得が raise すると /today が 500＝「コーデを取得できませんでした」に
    なっていた）。push にはタイトルでなく参加者名のみ出す方針（プライバシー）。
    """
    empty: Dict[str, Any] = {
        "attendees": [],
        "events": [],
        "last_worn": {},
        "worn_history": [],
    }
    if not settings.calendar_ics_urls:
        return empty

    try:
        # ICS フィードは 1 回だけ取得して使い回す（今日の予定 + 予定名で同じフィードを使う・
        # 1 本 ~4 秒かかるため二重 fetch は致命的・#463 速度改善）
        ics_texts = fetch_ics_texts(settings.calendar_ics_urls)
        events = events_today_from_texts(
            ics_texts,
            redact_title_keywords=settings.calendar_redact_title_keywords,
        )
        attendees = unique_attendees(events)
        day_start = jst_now().replace(hour=0, minute=0, second=0, microsecond=0)
        # 過去全件（/today の人別セクション）を 1 回引き、push 用 last_worn はその先頭から導く
        worn_history = _worn_history_by_attendee(db, attendees, day_start)
        # 各写真に「その日その人と一緒だった予定名」を付ける（失敗しても worn_history は残す）
        _annotate_meet_titles(worn_history, settings, ics_texts)
        last_worn = {
            entry["name"]: entry["photos"][0]
            for entry in worn_history
            if entry["photos"]
        }
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to build schedule for morning brief: %s", exc)
        return empty

    return {
        "attendees": attendees,
        "events": events,
        "last_worn": last_worn,
        "worn_history": worn_history,
    }


_EMPTY_SCHEDULE: Dict[str, Any] = {
    "attendees": [],
    "events": [],
    "last_worn": {},
    "worn_history": [],
}


async def _build_brief(
    db: Session, settings: Settings, include_schedule: bool = True
) -> Dict[str, Any]:
    """今日の天気 + 気温が近い過去コーデ + 構成アイテムをまとめて組み立てる.

    玄関ディスプレイ用（公開）と HA push 用（Bearer 認証）の両エンドポイントが
    同じデータを使うため、本体をここに切り出して共有する。

    include_schedule=False のときは schedule（今日会う人・過去コーデ）を組まない。
    schedule は ICS フェッチ（~4 秒）が要るので、/today は本体（天気・ヒーロー）を先に
    出してから schedule を別途遅延ロードする（#463 体感速度改善）。
    """
    # --- 今日の天気（OpenWeather・既存 WeatherService）---
    snapshot = await WeatherService(settings).get_current_weather()
    weather_available = snapshot.condition not in ("unavailable", "unknown")
    target_temp = (
        snapshot.temp_max if snapshot.temp_max is not None else snapshot.temperature
    )

    weather = {
        "condition": snapshot.condition,
        "temperature": snapshot.temperature,
        "temp_max": snapshot.temp_max,
        "temp_min": snapshot.temp_min,
        "precipitation_mm": snapshot.precipitation_mm,
        "umbrella_required": snapshot.umbrella_required,
        "available": weather_available,
    }

    # --- ヒーロー写真（気温が近い過去のコーデ記録）---
    # 構成アイテムを出すため outfit_record を持つ写真のみ候補にする。
    # Photo は JSON カラム（embedding 等）を持ち DISTINCT できないため、
    # join+distinct でなく EXISTS で絞り込む。
    # load_only で気温・撮影日・id だけ読む（全 outfit 写真の embedding_vector 等の巨大
    # JSON をデシリアライズすると数秒かかるため・ 速度改善）。
    has_outfit = exists().where(OutfitRecord.photo_id == Photo.id)
    candidates = (
        db.query(Photo)
        .options(
            load_only(
                Photo.id,
                Photo.captured_at,
                Photo.temperature_max,
                Photo.temperature_min,
                Photo.deleted_at,
            )
        )
        .filter(Photo.deleted_at.is_(None), has_outfit)
        .all()
    )

    hero: Optional[Dict[str, Any]] = None
    items: List[Dict[str, Any]] = []

    if candidates:
        temped = [p for p in candidates if p.temperature_max is not None]
        if target_temp is not None and temped:
            # 今日の最高気温に最も近い過去の記録
            chosen = min(temped, key=lambda p: abs(p.temperature_max - target_temp))
            matched = True
        else:
            # 気温が未 backfill / 天気取得不可のときは直近の記録で代用
            chosen = max(candidates, key=lambda p: p.captured_at or jst_now())
            matched = False

        captured = chosen.captured_at
        photo_id = str(chosen.id)
        hero = {
            "photo_id": photo_id,
            "photo_url": _hero_photo_url(photo_id),
            "captured_date": captured.date().isoformat() if captured else None,
            "temperature_max": chosen.temperature_max,
            "temperature_min": chosen.temperature_min,
            "matched_by_temperature": matched,
        }
        items = _hero_items(db, photo_id)

    return {
        "date": jst_now().date().isoformat(),
        "weather": weather,
        "hero": hero,
        "items": items,
        "schedule": (
            _build_schedule(db, settings) if include_schedule else _EMPTY_SCHEDULE
        ),
    }


@router.get("/morning-brief")
async def get_morning_brief(
    schedule: str = "include",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """玄関ディスプレイ / スマホ詳細ページ用（CF Access 配下のブラウザから取得）.

    `?schedule=skip` で schedule を省いた軽量レスポンス（ICS フェッチなし・~1 秒）を返す。
    /today はまずこれで天気・ヒーローを描画し、人別コーデは /morning-brief/schedule で
    遅延ロードする。
    """
    return await _build_brief(db, settings, include_schedule=schedule != "skip")


@router.get("/morning-brief/schedule")
async def get_morning_brief_schedule(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """今日会う人ごとの過去コーデ（schedule）だけを返す（/today の遅延ロード用）.

    ICS フェッチ（~4 秒）が要る重い部分。/today は本体取得と並列でこれを叩き、
    返ってきたら人別セクションを差し込む。
    """
    return _build_schedule(db, settings)


@router.get("/morning-brief/external")
async def get_morning_brief_external(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    actor: AuthenticatedActor = Depends(require_external_rental_auth),
) -> Dict[str, Any]:
    """HA など外部クライアント用（Bearer トークン認証）.

    `/morning-brief` と同じデータを返すが、CF Access を持たない HA から叩けるよう
    require_external_rental_auth（EXTERNAL_RENTAL_API_TOKEN の Bearer）で保護する。
    本番では CF 側でこのパスだけ Access Bypass を当て、アプリ層の Bearer で守る。
    """
    logger.info("morning-brief/external requested via %s", actor.source)
    return await _build_brief(db, settings)
