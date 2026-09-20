import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, timedelta
from time import monotonic
from typing import Any
from urllib.parse import quote_plus
from weakref import WeakValueDictionary

import httpx
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.models import Bout, Event, EventSummary, Fighter

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"
UPSTREAM_TIMEOUT_SECONDS = 10.0
MAX_CACHE_ENTRIES = 256
REDIS_URL = os.getenv("REDIS_URL")
REDIS_PREFIX = "mma:scoreboard:"
logger = logging.getLogger(__name__)


class EspnMmaError(RuntimeError):
    """Base error for the ESPN MMA provider."""


class EspnMmaTimeoutError(EspnMmaError):
    """The provider did not respond before the configured timeout."""


class EspnMmaRequestError(EspnMmaError):
    """The provider request failed."""


class EspnMmaDataError(EspnMmaError):
    """The provider returned malformed or incomplete data."""


class EspnMmaEventNotFoundError(EspnMmaError):
    """The requested event was not returned by the provider."""


@dataclass
class CacheEntry:
    payload: dict[str, Any]
    expires_at: float


_scoreboard_cache: dict[str, CacheEntry] = {}
_cache_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
_redis = Redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=UPSTREAM_TIMEOUT_SECONDS,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            headers={
                "Accept": "application/json",
                "User-Agent": (
                    "mma-api-service/0.1 (+https://github.com/cascadiacollections/mma-api-service)"
                ),
            },
        )
    return _http_client


def _cache_key(params: dict[str, str]) -> str:
    raw_key = "&".join(f"{key}={value}" for key, value in sorted(params.items()))
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _payload_ttl(payload: dict[str, Any], *, event_lookup: bool) -> int:
    if not event_lookup:
        return 600

    events = payload.get("events", [])
    if events and all(
        event.get("status", {}).get("type", {}).get("completed") is True for event in events
    ):
        return 86_400
    if any(event.get("status", {}).get("type", {}).get("state") == "in" for event in events):
        return 15
    return 900


async def _get_cached(key: str) -> dict[str, Any] | None:
    if _redis is not None:
        try:
            value = await _redis.get(f"{REDIS_PREFIX}{key}")
            if value:
                payload = json.loads(value)
                if isinstance(payload, dict):
                    return payload
        except (RedisError, json.JSONDecodeError):
            logger.exception("Shared cache unavailable; continuing with process cache")

    cached = _scoreboard_cache.get(key)
    if cached and cached.expires_at > monotonic():
        return cached.payload
    return None


async def _store_cached(key: str, payload: dict[str, Any], ttl: int) -> None:
    now = monotonic()
    expired_keys = [
        cached_key
        for cached_key, cached_entry in _scoreboard_cache.items()
        if cached_entry.expires_at <= now
    ]
    for expired_key in expired_keys:
        _scoreboard_cache.pop(expired_key, None)

    while len(_scoreboard_cache) >= MAX_CACHE_ENTRIES:
        oldest_key = next(iter(_scoreboard_cache))
        _scoreboard_cache.pop(oldest_key, None)

    _scoreboard_cache[key] = CacheEntry(payload=payload, expires_at=now + ttl)
    if _redis is not None:
        try:
            await _redis.setex(f"{REDIS_PREFIX}{key}", ttl, json.dumps(payload))
        except RedisError:
            logger.exception("Shared cache write failed; process cache remains active")


async def close() -> None:
    global _http_client
    if _redis is not None:
        await _redis.aclose()
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


async def fetch_scoreboard(params: dict[str, str]) -> dict[str, Any]:
    key = _cache_key(params)
    cached = await _get_cached(key)
    if cached is not None:
        return cached

    lock = _cache_locks.setdefault(key, asyncio.Lock())
    async with lock:
        cached = await _get_cached(key)
        if cached is not None:
            return cached

        try:
            response = await _get_http_client().get(SCOREBOARD_URL, params=params)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise EspnMmaTimeoutError("UFC event provider timed out") from exc
        except httpx.HTTPError as exc:
            raise EspnMmaRequestError("UFC event provider request failed") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise EspnMmaDataError("UFC event provider returned invalid JSON") from exc
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("events"), list)
            or not all(isinstance(event, dict) for event in payload["events"])
        ):
            raise EspnMmaDataError("UFC event provider returned invalid data")

        await _store_cached(
            key,
            payload,
            _payload_ttl(payload, event_lookup="event" in params),
        )
        return payload


def _is_ufc_event(raw_event: dict[str, Any]) -> bool:
    return "ufc" in str(raw_event.get("name", "")).lower()


def normalize_event_summary(raw_event: dict[str, Any]) -> EventSummary:
    status = raw_event.get("status", {}).get("type", {})
    return EventSummary(
        id=str(raw_event["id"]),
        name=str(raw_event["name"]),
        date=str(raw_event["date"]),
        status=str(status.get("description", "Unknown")),
        completed=bool(status.get("completed", False)),
        bout_count=len(raw_event.get("competitions", [])),
    )


def _normalize_fighter(raw_competitor: dict[str, Any]) -> Fighter:
    athlete = raw_competitor.get("athlete", {})
    fighter_id = str(raw_competitor["id"])
    fighter_name = str(athlete.get("displayName") or athlete.get("fullName") or "Unknown fighter")
    records = raw_competitor.get("records", [])
    overall_record = next(
        (record.get("summary") for record in records if record.get("type") == "total"),
        None,
    )
    flag = athlete.get("flag") or {}
    return Fighter(
        id=fighter_id,
        name=fighter_name,
        record=overall_record,
        country=flag.get("alt"),
        flag_url=flag.get("href"),
        image_url=f"https://a.espncdn.com/i/headshots/mma/players/full/{fighter_id}.png",
        espn_profile_url=f"https://www.espn.com/mma/fighter/_/id/{fighter_id}",
        tapology_search_url=f"https://www.tapology.com/search?term={quote_plus(fighter_name)}",
    )


def normalize_event(raw_event: dict[str, Any]) -> Event:
    summary = normalize_event_summary(raw_event)
    bouts: list[Bout] = []

    for order, competition in enumerate(raw_event.get("competitions", []), start=1):
        raw_competitors = competition.get("competitors", [])
        if len(raw_competitors) != 2:
            raise ValueError(f"Bout {competition.get('id', 'unknown')} does not have two fighters")
        fighters = [_normalize_fighter(competitor) for competitor in raw_competitors]
        bout_status = competition.get("status", {}).get("type", {})
        winner = next(
            (
                str(competitor["id"])
                for competitor in raw_competitors
                if competitor.get("winner") is True
            ),
            None,
        )
        bouts.append(
            Bout(
                id=str(competition["id"]),
                order=order,
                weight_class=(competition.get("type") or {}).get("abbreviation"),
                status=str(bout_status.get("description", "Unknown")),
                completed=bool(bout_status.get("completed", False)),
                fighters=fighters,
                winner_id=winner,
            )
        )

    return Event(**summary.model_dump(), bouts=bouts)


def default_event_window() -> tuple[date, date]:
    today = date.today()
    return today - timedelta(days=14), today + timedelta(days=180)


def _event_from_payload(payload: dict[str, Any], event_id: str) -> dict[str, Any] | None:
    return next(
        (
            event
            for event in payload["events"]
            if str(event.get("id")) == event_id and _is_ufc_event(event)
        ),
        None,
    )


async def list_events(start: date, end: date) -> list[EventSummary]:
    payload = await fetch_scoreboard(
        {
            "dates": f"{start:%Y%m%d}-{end:%Y%m%d}",
            "limit": "100",
        }
    )
    try:
        events = [
            normalize_event_summary(raw_event)
            for raw_event in payload["events"]
            if _is_ufc_event(raw_event)
        ]
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise EspnMmaDataError("UFC event provider data is incomplete") from exc
    return sorted(events, key=lambda event: event.date)


async def get_event(event_id: str) -> Event:
    payload = await fetch_scoreboard({"event": event_id})
    raw_event = _event_from_payload(payload, event_id)

    if raw_event is None:
        start, end = default_event_window()
        fallback_payload = await fetch_scoreboard(
            {
                "dates": f"{start:%Y%m%d}-{end:%Y%m%d}",
                "limit": "100",
            }
        )
        raw_event = _event_from_payload(fallback_payload, event_id)

    if raw_event is None:
        raise EspnMmaEventNotFoundError("UFC event not found")
    try:
        return normalize_event(raw_event)
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise EspnMmaDataError("UFC event provider data is incomplete") from exc
