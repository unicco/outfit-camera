"""Environment-related service clients (weather and calendar)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..settings import Settings
from ..utils.timezone_utils import TimezoneUtils

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WeatherSnapshot:
    """Normalized weather payload used across services."""

    condition: str
    temperature: Optional[float]
    feels_like: Optional[float]
    temp_min: Optional[float]
    temp_max: Optional[float]
    precipitation_mm: float
    humidity: Optional[float]
    wind_speed: Optional[float]
    sunrise: Optional[datetime]
    sunset: Optional[datetime]
    raw: Dict[str, Any]

    @property
    def umbrella_required(self) -> bool:
        """Return True when precipitation exceeds light drizzle (>= 0.2mm)."""
        return self.precipitation_mm >= 0.2


class WeatherService:
    """OpenWeather One Call API client with simple caching."""

    _API_URL = "https://api.openweathermap.org/data/3.0/onecall"

    def __init__(self, settings: Settings, cache_ttl_minutes: int = 15) -> None:
        self._api_key = settings.openweather_api_key
        self._lat = settings.morning_location_lat
        self._lon = settings.morning_location_lon
        self._cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self._cache: tuple[WeatherSnapshot, datetime] | None = None
        self._enabled = bool(
            self._api_key and self._lat is not None and self._lon is not None
        )

    async def get_current_weather(self) -> WeatherSnapshot:
        """Return cached weather if valid, otherwise fetch from API."""
        now = datetime.now(timezone.utc)
        if self._cache and now - self._cache[1] < self._cache_ttl:
            return self._cache[0]

        if not self._enabled:
            snapshot = self._empty_snapshot("unknown")
            self._cache = (snapshot, now)
            return snapshot

        params = {
            "lat": self._lat,
            "lon": self._lon,
            "appid": self._api_key,
            "units": "metric",
            "exclude": "minutely,alerts",
            "lang": "ja",
        }

        data: Dict[str, Any] | None = None

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(self._API_URL, params=params)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                logger.warning(
                    "OpenWeather API request failed with 401. Falling back to /data/2.5/weather: %s",
                    exc,
                )
                try:
                    async with httpx.AsyncClient(timeout=8.0) as client:
                        fallback_response = await client.get(
                            "https://api.openweathermap.org/data/2.5/weather",
                            params={
                                "lat": self._lat,
                                "lon": self._lon,
                                "appid": self._api_key,
                                "units": "metric",
                                "lang": "ja",
                            },
                        )
                        fallback_response.raise_for_status()
                        data = self._adapt_current_weather(
                            payload=fallback_response.json()
                        )
                except httpx.HTTPError as fallback_exc:
                    logger.warning(
                        "Fallback OpenWeather request failed: %s", fallback_exc
                    )
            else:
                logger.warning("OpenWeather API request failed: %s", exc)
        except httpx.HTTPError as exc:  # pragma: no cover - depends on network
            logger.warning("OpenWeather API request failed: %s", exc)

        if data is None:
            snapshot = self._empty_snapshot("unavailable")
            self._cache = (snapshot, now)
            return snapshot

        snapshot = self._parse_payload(data)
        self._cache = (snapshot, now)
        return snapshot

    def _parse_payload(self, payload: Dict[str, Any]) -> WeatherSnapshot:
        current = payload.get("current", {})
        hourly = payload.get("hourly", [])
        condition = self._normalize_condition(current)
        precipitation = 0.0

        if isinstance(hourly, list) and hourly:
            next_hour = hourly[0]
            precipitation = float(
                (next_hour.get("rain", {}) or {}).get("1h", 0.0)
                or (next_hour.get("snow", {}) or {}).get("1h", 0.0)
            )

        return WeatherSnapshot(
            condition=condition,
            temperature=_safe_float(current.get("temp")),
            feels_like=_safe_float(current.get("feels_like")),
            temp_min=_safe_float(
                payload.get("daily", [{}])[0].get("temp", {}).get("min")
            ),
            temp_max=_safe_float(
                payload.get("daily", [{}])[0].get("temp", {}).get("max")
            ),
            precipitation_mm=precipitation,
            humidity=_safe_float(current.get("humidity")),
            wind_speed=_safe_float(current.get("wind_speed")),
            sunrise=_safe_datetime(current.get("sunrise")),
            sunset=_safe_datetime(current.get("sunset")),
            raw=payload,
        )

    def _adapt_current_weather(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Convert /data/2.5/weather payload into One Call format."""
        weather = payload.get("weather", [])
        main = payload.get("main", {})
        wind = payload.get("wind", {})
        sys_data = payload.get("sys", {})

        return {
            "current": {
                "weather": weather,
                "temp": main.get("temp"),
                "feels_like": main.get("feels_like"),
                "humidity": main.get("humidity"),
                "wind_speed": wind.get("speed"),
                "sunrise": sys_data.get("sunrise"),
                "sunset": sys_data.get("sunset"),
            },
            "hourly": [],
            "daily": [
                {
                    "temp": {
                        "min": main.get("temp_min"),
                        "max": main.get("temp_max"),
                    }
                }
            ],
        }

    @staticmethod
    def _normalize_condition(current: Dict[str, Any]) -> str:
        weather = current.get("weather")
        if isinstance(weather, list) and weather:
            main = str(weather[0].get("main", "")).lower()
            if main in {"rain", "drizzle", "thunderstorm"}:
                return "rainy"
            if main == "snow":
                return "snowy"
            if main == "clear":
                return "sunny"
            if main in {"clouds", "mist", "fog", "haze"}:
                return "cloudy"
        return "cloudy"

    @staticmethod
    def _empty_snapshot(condition: str) -> WeatherSnapshot:
        return WeatherSnapshot(
            condition=condition,
            temperature=None,
            feels_like=None,
            temp_min=None,
            temp_max=None,
            precipitation_mm=0.0,
            humidity=None,
            wind_speed=None,
            sunrise=None,
            sunset=None,
            raw={},
        )


class WeatherArchiveService:
    """Open-Meteo Historical Archive client.

    過去の設定地点の日次気温を取得する（無料・API キー不要）。撮影写真に気温を
    backfill するために使う。OpenWeather と違い課金されず、日付範囲を 1
    リクエストでまとめて取れる。ERA5 ベースのため直近数日はまだ欠損しうる
    （その日付は None を返す）。
    """

    _API_URL = "https://archive-api.open-meteo.com/v1/archive"

    def __init__(self, settings: Settings) -> None:
        self._lat = settings.morning_location_lat
        self._lon = settings.morning_location_lon
        self._enabled = self._lat is not None and self._lon is not None

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def get_daily_temperatures(
        self, start_date: date, end_date: date
    ) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
        """date 文字列(YYYY-MM-DD) -> (最高気温, 最低気温) のマップを返す。

        設定が無い / 取得失敗時は空 dict を返す（呼び出し側で graceful degrade）。
        """
        if not self._enabled:
            logger.warning(
                "WeatherArchiveService disabled: morning_location lat/lon not set"
            )
            return {}

        params = {
            "latitude": self._lat,
            "longitude": self._lon,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "daily": "temperature_2m_max,temperature_2m_min",
            "timezone": "Asia/Tokyo",
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(self._API_URL, params=params)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:  # pragma: no cover - depends on network
            logger.warning("Open-Meteo archive request failed: %s", exc)
            return {}

        daily = data.get("daily", {}) or {}
        times = daily.get("time", []) or []
        tmax = daily.get("temperature_2m_max", []) or []
        tmin = daily.get("temperature_2m_min", []) or []

        result: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
        for idx, day in enumerate(times):
            hi = _safe_float(tmax[idx]) if idx < len(tmax) else None
            lo = _safe_float(tmin[idx]) if idx < len(tmin) else None
            result[day] = (hi, lo)
        return result


class CalendarServiceError(RuntimeError):
    """Base exception for calendar service failures."""


class CalendarServiceDisabled(CalendarServiceError):
    """Raised when calendar integration is not configured."""


@dataclass(slots=True)
class CalendarEvent:
    """Calendar event representation shared by scheduling features."""

    title: str
    start: datetime
    end: Optional[datetime]
    location: Optional[str]
    calendar_id: str
    all_day: bool = False
    status: str = "confirmed"
    attendees: List[Dict[str, Any]] = field(default_factory=list)
    description: Optional[str] = None
    hangout_link: Optional[str] = None
    conference_solution: Optional[str] = None
    conference_urls: List[str] = field(default_factory=list)
    user_response: Optional[str] = None
    html_link: Optional[str] = None


class CalendarService:
    """Google Calendar service account client with graceful degradation."""

    def __init__(self, settings: Settings):
        self._credentials_file_source = settings.google_credentials_file
        self._token_file_source = settings.google_token_file
        self._primary_id = settings.google_calendar_primary_id
        self._extra_ids = settings.google_calendar_extra_ids or []
        self._delegated_user = settings.google_calendar_delegated_user
        candidate_emails = set()
        for value in (self._primary_id, self._delegated_user):
            if isinstance(value, str) and "@" in value:
                candidate_emails.add(value.lower())
        self._user_emails = candidate_emails
        self._enabled = bool(
            self._primary_id
            and (
                (
                    self._credentials_file_source
                    and self._credentials_file_source.strip()
                )
                or (self._token_file_source and self._token_file_source.strip())
            )
        )
        self._scopes = ["https://www.googleapis.com/auth/calendar.readonly"]

    async def get_upcoming_events(
        self,
        start: datetime,
        end: datetime,
        limit: int = 10,
    ) -> List[CalendarEvent]:
        if not self._enabled:
            raise CalendarServiceDisabled(
                "Google Calendar integration is not configured"
            )

        return await asyncio.to_thread(self._fetch_events_sync, start, end, limit)

    # --- internal helpers -------------------------------------------------

    def _fetch_events_sync(
        self, start: datetime, end: datetime, limit: int
    ) -> List[CalendarEvent]:
        try:
            from googleapiclient.discovery import build  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            logger.warning(
                "google-api-python-client is not installed; calendar disabled"
            )
            self._enabled = False
            raise CalendarServiceError(
                "Google Calendar client library is not installed"
            ) from exc

        credentials = self._load_credentials()
        if credentials is None:
            raise CalendarServiceError("Failed to load Google Calendar credentials")

        try:
            service = build(
                "calendar",
                "v3",
                credentials=credentials,
                cache_discovery=False,
            )
        except Exception as exc:  # pragma: no cover - network/credentials errors
            logger.warning("Failed to build Google Calendar service: %s", exc)
            raise CalendarServiceError(
                "Failed to initialize Google Calendar client"
            ) from exc

        calendar_ids = [self._primary_id, *self._extra_ids]
        events: List[CalendarEvent] = []
        successful_fetch = False

        for calendar_id in calendar_ids:
            try:
                result = (
                    service.events()
                    .list(
                        calendarId=calendar_id,
                        timeMin=start.isoformat(),
                        timeMax=end.isoformat(),
                        singleEvents=True,
                        orderBy="startTime",
                        maxResults=limit,
                    )
                    .execute()
                )
                successful_fetch = True
            except Exception as exc:  # pragma: no cover - network errors
                logger.warning(
                    "Failed to fetch events for calendar %s: %s", calendar_id, exc
                )
                continue

            for item in result.get("items", []):
                event = self._transform_event(item, calendar_id)
                if event:
                    events.append(event)

        if not successful_fetch:
            raise CalendarServiceError("Failed to fetch events from Google Calendar")

        events.sort(key=lambda e: e.start)
        return events[:limit]

    def _load_credentials(self, credentials_cls: Any | None = None):
        oauth_credentials = self._load_oauth_credentials()
        if oauth_credentials is not None:
            return oauth_credentials

        if not self._credentials_file_source:
            return None

        info, _ = self._read_json_source(self._credentials_file_source)
        if info is None:
            return None

        if credentials_cls is None:
            try:
                from google.oauth2 import service_account  # type: ignore

                credentials_cls = service_account.Credentials
            except ImportError as exc:  # pragma: no cover - optional dependency
                logger.warning(
                    "google-auth library is required for service account credentials: %s",
                    exc,
                )
                return None

        kwargs: Dict[str, Any] = {"scopes": self._scopes}
        if self._delegated_user:
            kwargs["subject"] = self._delegated_user

        try:
            return credentials_cls.from_service_account_info(info, **kwargs)
        except Exception as exc:  # pragma: no cover - key errors etc.
            logger.warning("Failed to load Google Calendar credentials: %s", exc)
            self._enabled = False
            return None

    def _load_oauth_credentials(self):
        if not self._token_file_source:
            return None

        info, from_file = self._read_json_source(self._token_file_source)
        if info is None:
            return None

        required_fields = {"client_id", "client_secret", "token_uri"}
        if not required_fields.issubset(info.keys()):
            logger.warning(
                "OAuth token data missing required fields: %s",
                required_fields - info.keys(),
            )
            return None

        try:
            from google.oauth2.credentials import Credentials as OAuthCredentials  # type: ignore
            from google.auth.transport.requests import Request  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            logger.warning(
                "google-auth library is required for OAuth credentials: %s", exc
            )
            return None

        try:
            credentials = OAuthCredentials.from_authorized_user_info(
                info, scopes=self._scopes
            )
        except Exception as exc:
            logger.warning("Failed to load OAuth credentials: %s", exc)
            return None

        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                if from_file:
                    updated = info.copy()
                    updated["token"] = credentials.token
                    if credentials.refresh_token:
                        updated["refresh_token"] = credentials.refresh_token
                    if credentials.expiry:
                        updated["expiry"] = credentials.expiry.isoformat()
                    self._write_json_source(self._token_file_source, updated)
            except Exception as exc:  # pragma: no cover - network/refresh errors
                logger.warning("Failed to refresh OAuth token: %s", exc)

        return credentials

    def _read_json_source(self, source: str) -> Tuple[Optional[Dict[str, Any]], bool]:
        if not source.strip():
            return None, False

        if source.strip().startswith("{"):
            try:
                return json.loads(source), False
            except json.JSONDecodeError:
                logger.warning("Invalid JSON content for Google credentials")
                return None, False

        try:
            with open(source, "r", encoding="utf-8") as handle:
                return json.load(handle), True
        except FileNotFoundError:
            logger.warning("Google credentials file not found: %s", source)
        except json.JSONDecodeError:
            logger.warning("Invalid Google credentials JSON in file: %s", source)
        except OSError as exc:
            logger.warning("Failed to read Google credentials file %s: %s", source, exc)
        return None, False

    def _write_json_source(self, source: str, data: Dict[str, Any]) -> None:
        if source.strip().startswith("{"):
            return

        directory = os.path.dirname(source)
        try:
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(source, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
        except OSError as exc:  # pragma: no cover - filesystem errors
            logger.warning("Failed to write updated OAuth token to %s: %s", source, exc)

    def _transform_event(
        self, payload: Dict[str, Any], calendar_id: str
    ) -> Optional[CalendarEvent]:
        summary = payload.get("summary") or "予定"
        start_raw = payload.get("start", {})
        end_raw = payload.get("end", {})

        start_dt, all_day = CalendarService._parse_event_time(start_raw)
        end_dt, _ = CalendarService._parse_event_time(end_raw)

        if start_dt is None:
            return None

        attendees_raw = payload.get("attendees") or []
        attendees: List[Dict[str, Any]] = []
        user_response: Optional[str] = None
        if isinstance(attendees_raw, list):
            for attendee in attendees_raw:
                if not isinstance(attendee, dict):
                    continue
                record = {
                    "email": attendee.get("email"),
                    "displayName": attendee.get("displayName"),
                    "responseStatus": attendee.get("responseStatus"),
                    "self": attendee.get("self"),
                }
                attendees.append(record)
                email = (attendee.get("email") or "").lower()
                if attendee.get("self"):
                    user_response = attendee.get("responseStatus")
                elif email and email in self._user_emails:
                    user_response = attendee.get("responseStatus")

        hangout_link = payload.get("hangoutLink")
        conference_solution = None
        conference_urls: List[str] = []
        conference_data = payload.get("conferenceData")
        if isinstance(conference_data, dict):
            solution = conference_data.get("conferenceSolution")
            if isinstance(solution, dict):
                conference_solution = solution.get("name") or solution.get("iconUri")
            for entry in conference_data.get("entryPoints", []) or []:
                if isinstance(entry, dict):
                    uri = entry.get("uri")
                    if uri:
                        conference_urls.append(uri)

        status = payload.get("status", "confirmed")
        html_link = payload.get("htmlLink")
        description = payload.get("description")

        return CalendarEvent(
            title=summary,
            start=start_dt,
            end=end_dt,
            location=payload.get("location"),
            calendar_id=calendar_id,
            all_day=all_day,
            status=status,
            attendees=attendees,
            description=description,
            hangout_link=hangout_link,
            conference_solution=conference_solution,
            conference_urls=conference_urls,
            user_response=user_response,
            html_link=html_link,
        )

    @staticmethod
    def _parse_event_time(payload: Dict[str, Any]) -> tuple[Optional[datetime], bool]:
        if "dateTime" in payload:
            value = payload["dateTime"]
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None, False
            return TimezoneUtils.to_jst(dt), False

        if "date" in payload:
            value = payload["date"]
            try:
                date_obj = datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                return None, True
            dt = TimezoneUtils.to_jst(date_obj.replace(hour=0, minute=0, second=0))
            return dt, True

        return None, False


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_datetime(epoch_seconds: Any) -> Optional[datetime]:
    try:
        if epoch_seconds is None:
            return None
        return datetime.fromtimestamp(float(epoch_seconds), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
