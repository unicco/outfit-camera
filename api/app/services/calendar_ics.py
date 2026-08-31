"""今日の予定の参加者を Google Calendar の ICS フィードから読む.

朝ブリーフ（morning_brief）の「今日会う人」表示用。Google カレンダーの
secret ICS URL を直読みし、タイトル末尾の `@名前1, 名前2` から参加者を抽出する。

なぜ ICS か:
- service account は個人 Gmail のカレンダーを読めない
- OAuth は personal scope が Testing mode で週次再認証になり運用負担が大きい
- life-log が同じ理由で ICS 経路を本番運用中（このパーサはその実装に倣う）

参加者の表記規約: brain `30_System/calendar-naming-convention.md`
- タイトル末尾に参加者を `@名前` で書く。名前ごとに `@` を付けてもよく
  （`@a @b` / `@a, @b` / `@a, b`）、区切りは空白でもカンマでも可。

このモジュールは life-log `life_log/connectors/self/calendar_ics.py` の最小移植版。
life-log は全期間のイベントを DB へ取り込むが、ここは「今日 1 日・参加者抽出」に
絞っているため軽量。両者の `@名前` 抽出ロジックは同一に保つこと（規約 doc が契約）。
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from dateutil.rrule import rrulestr

from ..utils.timezone_utils import JST

logger = logging.getLogger(__name__)

BEGIN_EVENT = "BEGIN:VEVENT"
END_EVENT = "END:VEVENT"

# 参加者セクションの開始 = 「空白・行頭・カンマの直後」の @ / ＠ のみ。
# こうすると本文中の @（地名 "代官山@渋谷" 等・直前が非空白）は参加者扱いせず、
# 名前ごとに @ を付ける書き方（@a @b / @a, @b）も拾える。
_ATTENDEE_START = re.compile(r"(?:^|(?<=\s)|(?<=[,、]))[@＠]")
# 名前同士の区切り = @ / ＠ / 半角カンマ / 全角カンマ（空白だけでは区切らない）
_ATTENDEE_SEP = re.compile(r"[@＠,、]")


def extract_attendees(summary: str) -> Optional[List[str]]:
    """タイトルの `@名前` から参加者名を抽出する.

    規約: brain `30_System/calendar-naming-convention.md`。
    名前ごとに @ を付けてよい（`@a @b` / `@a, @b` / `@a, b`）。区切りは空白でも
    カンマ（半角/全角）でも可。参加者の @ が無ければ None を返す。
    """
    match = _ATTENDEE_START.search(summary)
    if match is None:
        return None
    names_part = summary[match.start() :]
    attendees = [
        name.strip() for name in _ATTENDEE_SEP.split(names_part) if name.strip()
    ]
    return attendees or None


def strip_attendee_suffix(summary: str) -> str:
    """タイトルから参加者セクション（`@名前...`）を除いた本文を返す."""
    match = _ATTENDEE_START.search(summary)
    if match is None:
        return summary.strip()
    return summary[: match.start()].strip()


def unique_attendees(events: List[Dict[str, Any]]) -> List[str]:
    """予定リストから参加者名を初出順で一意化する."""
    names: List[str] = []
    for event in events:
        for name in event.get("attendees", []):
            if name not in names:
                names.append(name)
    return names


def fetch_ics_texts(ics_urls: List[str], timeout: int = 10) -> List[str]:
    """各 ICS フィードを 1 回だけ取得して本文リストを返す（取得失敗ぶんは除外）.

    ICS フィードの取得は数秒かかる（Google の secret URL・実測 ~4 秒/本）。morning-brief
    は「今日の予定」と「過去の予定タイトル」で同じフィードを使うため、ここで 1 回取得して
    本文を使い回し、二重 fetch を避ける（速度改善）。
    """
    texts: List[str] = []
    for url in ics_urls:
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            # 例外メッセージには secret な ICS URL が入るため型名だけログする
            logger.warning("Failed to fetch ICS feed: %s", type(exc).__name__)
            continue
        texts.append(resp.text)
    return texts


def events_today_from_texts(
    texts: List[str],
    redact_title_keywords: Optional[List[str]] = None,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """取得済 ICS 本文から今日（JST）の予定を組み立てる（fetch_today_events の本体）."""
    now_jst = (now or datetime.now(JST)).astimezone(JST)
    day_start = now_jst.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1) - timedelta(seconds=1)
    keywords = [k.lower() for k in (redact_title_keywords or [])]

    events: List[Dict[str, Any]] = []
    for text in texts:
        try:
            events.extend(_parse_today(text, day_start, day_end, keywords))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to parse ICS feed: %s", exc)

    events.sort(key=lambda e: (e["time"] is None, e["time"] or ""))
    return events


def fetch_today_events(
    ics_urls: List[str],
    redact_title_keywords: Optional[List[str]] = None,
    now: Optional[datetime] = None,
    timeout: int = 10,
) -> List[Dict[str, Any]]:
    """設定された ICS フィードから今日（JST）の予定を取得する.

    Returns:
        時刻順の予定リスト。各要素:
          - title: 参加者サフィックスを除いた予定名（redact 対象なら "(予定)"）
          - time: "HH:MM"（JST）。終日予定は None
          - all_day: bool
          - attendees: list[str]（無ければ空リスト）
        ネットワーク失敗・パース失敗は warning ログのみで、取れたぶんだけ返す。
    """
    texts = fetch_ics_texts(ics_urls, timeout)
    return events_today_from_texts(texts, redact_title_keywords, now)


def fetch_attendees_by_date(
    ics_urls: List[str],
    start_date: date,
    end_date: date,
    timeout: int = 10,
) -> Dict[str, List[str]]:
    """指定期間の各日（JST）について、予定タイトルの `@名前` から参加者を集約する.

    photos.attendees の過去 backfill 用。撮影日に対応する
    「その日会った人」を後から埋めるため、`fetch_today_events` を期間版に一般化したもの。

    `fetch_today_events` との違い:
    - redaction を適用しない。保存するのは名前のみで「誰と会ったか」の記録なので、
      センシティブ予定（打合せ等）でも参加者名は拾う。
    - 繰り返し予定は期間内の全発生日に展開する（今日 1 回でなく全件）。

    Returns:
        {"2026-02-03": ["alice"], "2026-04-23": ["bob", "太郎"], ...}
        参加者がいる日のみ。名前は初出順に一意化。ネット/パース失敗は取れたぶんだけ返す。
    """
    range_start = JST.localize(
        datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0)
    )
    range_end = JST.localize(
        datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)
    )

    by_date: Dict[str, List[str]] = {}
    for url in ics_urls:
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            # 例外メッセージには secret な ICS URL が入るため型名だけログする
            logger.warning("Failed to fetch ICS feed: %s", type(exc).__name__)
            continue
        try:
            triples = _parse_range(resp.text, range_start, range_end)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to parse ICS feed: %s", exc)
            continue
        for date_iso, attendees, _title in triples:
            bucket = by_date.setdefault(date_iso, [])
            for name in attendees:
                if name not in bucket:
                    bucket.append(name)
    return by_date


def events_by_date_from_texts(
    texts: List[str],
    start_date: date,
    end_date: date,
    redact_title_keywords: Optional[List[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """取得済 ICS 本文から期間の `参加者 + 予定タイトル` を集約する（fetch_events_by_date の本体）."""
    keywords = [k.lower() for k in (redact_title_keywords or [])]
    range_start = JST.localize(
        datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0)
    )
    range_end = JST.localize(
        datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)
    )

    by_date: Dict[str, List[Dict[str, Any]]] = {}
    for text in texts:
        try:
            triples = _parse_range(text, range_start, range_end)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to parse ICS feed: %s", exc)
            continue
        for date_iso, attendees, title in triples:
            is_sensitive = any(k in title.lower() for k in keywords)
            by_date.setdefault(date_iso, []).append(
                {"attendees": attendees, "title": None if is_sensitive else title}
            )
    return by_date


def fetch_events_by_date(
    ics_urls: List[str],
    start_date: date,
    end_date: date,
    redact_title_keywords: Optional[List[str]] = None,
    timeout: int = 10,
) -> Dict[str, List[Dict[str, Any]]]:
    """指定期間の各日（JST）について `参加者 + 予定タイトル` を集約する.

    /today の人別セクションで「いつ・何の予定で一緒だったか」を出すため、撮影日に
    対応する予定（その人を含むイベント）のタイトルを引けるようにする（#463）。
    センシティブ予定（redact_title_keywords に一致）はタイトルを None にする（名前は残す）。

    Returns:
        {"2026-02-03": [{"attendees": ["太郎"], "title": "ランチ"}], ...}
        ネット/パース失敗は取れたぶんだけ返す。
    """
    texts = fetch_ics_texts(ics_urls, timeout)
    return events_by_date_from_texts(texts, start_date, end_date, redact_title_keywords)


# --- internal parsing -----------------------------------------------------


def _parse_today(
    text: str,
    day_start: datetime,
    day_end: datetime,
    keywords: List[str],
) -> List[Dict[str, Any]]:
    lines = _unfold_ics(text)
    events: List[Dict[str, Any]] = []

    in_event = False
    props: Dict[str, str] = {}
    raw_lines: Dict[str, str] = {}
    exdates: List[str] = []
    for line in lines:
        if line == BEGIN_EVENT:
            in_event = True
            props = {}
            raw_lines = {}
            exdates = []
            continue
        if line == END_EVENT:
            in_event = False
            built = _build_today_event(
                props, raw_lines, exdates, day_start, day_end, keywords
            )
            if built:
                events.append(built)
            continue
        if not in_event:
            continue
        key, value = _split_ics_line(line)
        props[key] = value
        raw_key = line.split(":", 1)[0] if ":" in line else line
        if raw_key.startswith("DTSTART"):
            raw_lines[key] = line
        elif raw_key.startswith("EXDATE"):
            # キャンセルされた繰り返し回。rrulestr にそのまま渡して除外する
            exdates.append(line)

    return events


def _parse_range(
    text: str,
    range_start: datetime,
    range_end: datetime,
) -> List[tuple[str, List[str], str]]:
    """期間内の各発生日について `(ISO日付, 参加者リスト, 予定タイトル)` を返す.

    `_parse_today` の期間版。各 VEVENT の参加者・タイトルを 1 回だけ抽出し、繰り返し
    予定は期間内の全発生日に展開する。redaction は適用しない（呼び出し側で判断する）。
    タイトルは参加者サフィックス（`@名前...`）を除いた本文。
    """
    lines = _unfold_ics(text)
    results: List[tuple[str, List[str], str]] = []

    in_event = False
    props: Dict[str, str] = {}
    raw_lines: Dict[str, str] = {}
    exdates: List[str] = []
    for line in lines:
        if line == BEGIN_EVENT:
            in_event = True
            props = {}
            raw_lines = {}
            exdates = []
            continue
        if line == END_EVENT:
            in_event = False
            results.extend(
                _event_dates_with_attendees(
                    props, raw_lines, exdates, range_start, range_end
                )
            )
            continue
        if not in_event:
            continue
        key, value = _split_ics_line(line)
        props[key] = value
        raw_key = line.split(":", 1)[0] if ":" in line else line
        if raw_key.startswith("DTSTART"):
            raw_lines[key] = line
        elif raw_key.startswith("EXDATE"):
            exdates.append(line)

    return results


def _event_dates_with_attendees(
    props: Dict[str, str],
    raw_lines: Dict[str, str],
    exdates: List[str],
    range_start: datetime,
    range_end: datetime,
) -> List[tuple[str, List[str], str]]:
    summary = props.get("SUMMARY")
    dtstart_val = props.get("DTSTART")
    if not summary or not dtstart_val:
        return []
    if props.get("STATUS", "").upper() == "CANCELLED":
        return []

    summary = _unescape_ics_text(summary)
    attendees = extract_attendees(summary)
    if not attendees:
        return []
    title = strip_attendee_suffix(summary)

    dtstart_raw = raw_lines.get("DTSTART", f"DTSTART:{dtstart_val}")
    start_dt = _parse_ics_datetime(dtstart_raw, dtstart_val)
    if start_dt is None:
        return []

    occ_dates = _occurrence_dates(
        start_dt, props.get("RRULE"), exdates, range_start, range_end
    )
    return [(d, attendees, title) for d in occ_dates]


def _occurrence_dates(
    start_dt: datetime,
    rrule: Optional[str],
    exdates: List[str],
    range_start: datetime,
    range_end: datetime,
) -> List[str]:
    """期間内に該当する発生日（JST の ISO 日付）を新しい順でない素朴な順で返す.

    RRULE があれば期間内で全展開し、各発生を JST の日付に変換する。EXDATE は除外。
    """
    if not rrule:
        if range_start <= start_dt <= range_end:
            return [start_dt.astimezone(JST).date().isoformat()]
        return []
    rule_str = "\n".join([f"RRULE:{rrule}", *exdates])
    try:
        rule = rrulestr(rule_str, dtstart=start_dt)
    except Exception:
        if range_start <= start_dt <= range_end:
            return [start_dt.astimezone(JST).date().isoformat()]
        return []
    occurrences = rule.between(range_start, range_end, inc=True)
    return [o.astimezone(JST).date().isoformat() for o in occurrences]


def _build_today_event(
    props: Dict[str, str],
    raw_lines: Dict[str, str],
    exdates: List[str],
    day_start: datetime,
    day_end: datetime,
    keywords: List[str],
) -> Optional[Dict[str, Any]]:
    summary = props.get("SUMMARY")
    dtstart_val = props.get("DTSTART")
    if not summary or not dtstart_val:
        return None
    if props.get("STATUS", "").upper() == "CANCELLED":
        return None

    # ICS は SUMMARY 内の , ; \ をエスケープする（`@a\, @b` 等）。
    # アンエスケープしないと参加者名に "\" が混ざる
    summary = _unescape_ics_text(summary)

    dtstart_raw = raw_lines.get("DTSTART", f"DTSTART:{dtstart_val}")
    start_dt = _parse_ics_datetime(dtstart_raw, dtstart_val)
    if start_dt is None:
        return None
    all_day = bool(re.fullmatch(r"\d{8}", dtstart_val))

    occ = _occurrence_today(start_dt, props.get("RRULE"), exdates, day_start, day_end)
    if occ is None:
        return None

    attendees = extract_attendees(summary) or []
    is_sensitive = any(k in summary.lower() for k in keywords)
    title = "(予定)" if is_sensitive else strip_attendee_suffix(summary)
    if is_sensitive:
        attendees = []

    return {
        "title": title,
        "time": None if all_day else occ.astimezone(JST).strftime("%H:%M"),
        "all_day": all_day,
        "attendees": attendees,
    }


def _occurrence_today(
    start_dt: datetime,
    rrule: Optional[str],
    exdates: List[str],
    day_start: datetime,
    day_end: datetime,
) -> Optional[datetime]:
    """今日（JST）に該当する開始時刻を返す。該当しなければ None.

    RRULE があれば今日の範囲で展開し、最初の発生を返す。EXDATE（キャンセル
    された回）は rrulestr に渡して除外する。
    """
    if not rrule:
        return start_dt if day_start <= start_dt <= day_end else None
    rule_str = "\n".join([f"RRULE:{rrule}", *exdates])
    try:
        rule = rrulestr(rule_str, dtstart=start_dt)
    except Exception:
        return start_dt if day_start <= start_dt <= day_end else None
    occurrences = rule.between(day_start, day_end, inc=True)
    return occurrences[0] if occurrences else None


def _unfold_ics(text: str) -> List[str]:
    """折り返された ICS 行（継続行は空白/タブ始まり）を結合する."""
    result: List[str] = []
    for line in text.splitlines():
        stripped = line.rstrip("\r")
        if stripped.startswith((" ", "\t")) and result:
            result[-1] += stripped[1:]
        else:
            result.append(stripped.strip())
    return result


def _unescape_ics_text(value: str) -> str:
    """RFC 5545 TEXT のエスケープを戻す（`\\,`→`,` / `\\;`→`;` / `\\\\`→`\\` / `\\n`→改行）."""
    out: List[str] = []
    i = 0
    n = len(value)
    while i < n:
        ch = value[i]
        if ch == "\\" and i + 1 < n:
            nxt = value[i + 1]
            out.append("\n" if nxt in ("n", "N") else nxt)
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _split_ics_line(line: str) -> tuple[str, str]:
    if ":" not in line:
        return line, ""
    key, value = line.split(":", 1)
    key = key.split(";", 1)[0]
    return key, value


def _parse_ics_datetime(raw_line: str, value: str) -> Optional[datetime]:
    """ICS の日時をタイムゾーン対応で parse する（life-log と同一ロジック）."""
    # UTC: 20260303T040000Z
    if re.fullmatch(r"\d{8}T\d{6}Z", value):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    # 終日: 20260303 → UTC 真夜中（JST 09:00・当日 JST 枠内に収まる）
    if re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc)
    # TZID 付き: DTSTART;TZID=Asia/Tokyo:20260303T130000
    tzid_match = re.search(r"TZID=([^:;]+)", raw_line)
    if tzid_match and re.fullmatch(r"\d{8}T\d{6}", value):
        try:
            from dateutil import tz

            tzinfo = tz.gettz(tzid_match.group(1))
            return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=tzinfo)
        except Exception:  # noqa: S110 未知の TZID は下の UTC 解釈へ落とす
            pass
    # tz なしローカル時刻: 20260303T130000 → UTC とみなす
    if re.fullmatch(r"\d{8}T\d{6}", value):
        return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    return None
