import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, suppress
from time import monotonic
from typing import Any

import httpx
import pytest
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.providers import espn_mma
from app.providers.espn_mma import (
    EspnMmaDataError,
    EspnMmaRequestError,
    EspnMmaTimeoutError,
    _payload_ttl,
)


def event_payload(*, completed: bool, state: str) -> dict:
    return {
        "events": [
            {
                "status": {
                    "type": {
                        "completed": completed,
                        "state": state,
                    }
                }
            }
        ]
    }


def test_event_list_cache_ttl() -> None:
    assert _payload_ttl({"events": []}, event_lookup=False) == 600


def test_completed_event_cache_ttl() -> None:
    assert _payload_ttl(event_payload(completed=True, state="post"), event_lookup=True) == 86_400


def test_live_event_cache_ttl() -> None:
    assert _payload_ttl(event_payload(completed=False, state="in"), event_lookup=True) == 15


def test_scheduled_event_cache_ttl() -> None:
    assert _payload_ttl(event_payload(completed=False, state="pre"), event_lookup=True) == 900


@pytest.fixture(autouse=True)
def _isolated_scoreboard_cache(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    espn_mma._scoreboard_cache.clear()
    espn_mma._cache_locks.clear()
    monkeypatch.setattr(espn_mma, "_redis", None)
    yield
    espn_mma._scoreboard_cache.clear()
    espn_mma._cache_locks.clear()


class Upstream:
    def __init__(
        self,
        *,
        status: int = 200,
        payload: dict[str, Any] | None = None,
        error: Exception | None = None,
        content: bytes | None = None,
    ) -> None:
        self.status = status
        self.payload = {"events": []} if payload is None else payload
        self.error = error
        self.content = content
        self.calls = 0

    async def get(self, *_args: Any, **_kwargs: Any) -> httpx.Response:
        self.calls += 1
        if self.error is not None:
            raise self.error
        request = httpx.Request("GET", espn_mma.SCOREBOARD_URL)
        if self.content is not None:
            return httpx.Response(self.status, content=self.content, request=request)
        return httpx.Response(self.status, json=self.payload, request=request)


class FakeRedis:
    def __init__(
        self,
        values: dict[str, tuple[str, int]] | None = None,
        *,
        error: Exception | None = None,
        write_error: Exception | None = None,
    ) -> None:
        self.values = values or {}
        self.error = error
        self.write_error = write_error
        self.reads = 0
        self.writes = 0

    def pipeline(self, transaction: bool = True, shard_hint: str | None = None) -> "FakePipeline":
        return FakePipeline(self)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.writes += 1
        if self.write_error is not None:
            raise self.write_error
        self.values[key] = (value, ttl)

    async def aclose(self) -> None:
        return None


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis
        self.ops: list[tuple[str, str]] = []

    async def __aenter__(self) -> "FakePipeline":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def get(self, key: str) -> "FakePipeline":
        self.ops.append(("get", key))
        return self

    def ttl(self, key: str) -> "FakePipeline":
        self.ops.append(("ttl", key))
        return self

    async def execute(self) -> list[Any]:
        self.redis.reads += 1
        if self.redis.error is not None:
            raise self.redis.error
        results: list[Any] = []
        for op, key in self.ops:
            value, ttl = self.redis.values.get(key, (None, -2))
            results.append(value if op == "get" else ttl)
        return results


def install_upstream(monkeypatch: pytest.MonkeyPatch, upstream: Upstream) -> None:
    monkeypatch.setattr(espn_mma, "_get_http_client", lambda: upstream)


def redis_key_for(params: dict[str, str]) -> tuple[str, str]:
    cache_key = espn_mma._cache_key(params)
    return cache_key, f"{espn_mma.REDIS_PREFIX}{cache_key}"


def seed_process_cache(cache_key: str, payload: dict[str, Any], *, ttl: float) -> None:
    espn_mma._scoreboard_cache[cache_key] = espn_mma.CacheEntry(
        payload=payload,
        expires_at=monotonic() + ttl,
    )


@asynccontextmanager
async def blackhole_redis() -> AsyncIterator[Any]:
    release = asyncio.Event()

    async def handler(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await release.wait()
        finally:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    sockets = server.sockets or []
    port = sockets[0].getsockname()[1]
    client = espn_mma._build_redis_client(f"redis://127.0.0.1:{port}/0")
    try:
        yield client
    finally:
        release.set()
        server.close()
        await server.wait_closed()
        with suppress(Exception):
            await asyncio.wait_for(client.aclose(), timeout=2)


async def test_concurrent_cache_misses_share_one_upstream_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"events": []}

    class FakeClient:
        calls = 0

        async def get(self, *_args, **_kwargs) -> FakeResponse:
            self.calls += 1
            await asyncio.sleep(0.01)
            return FakeResponse()

    fake_client = FakeClient()
    espn_mma._scoreboard_cache.clear()
    espn_mma._cache_locks.clear()
    monkeypatch.setattr(espn_mma, "_redis", None)
    monkeypatch.setattr(espn_mma, "_get_http_client", lambda: fake_client)

    first, second = await asyncio.gather(
        espn_mma.fetch_scoreboard({"event": "600000001"}),
        espn_mma.fetch_scoreboard({"event": "600000001"}),
    )

    assert first == {"events": []}
    assert second == first
    assert fake_client.calls == 1


async def test_event_lookup_falls_back_when_espn_ignores_event_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrong_event = {
        "id": "600000002",
        "name": "UFC Other",
        "date": "2026-09-21T00:00Z",
        "status": {"type": {"description": "Scheduled", "completed": False}},
        "competitions": [],
    }
    requested_event = {
        "id": "600000001",
        "name": "UFC Test",
        "date": "2026-09-20T00:00Z",
        "status": {"type": {"description": "Scheduled", "completed": False}},
        "competitions": [],
    }
    payloads = iter(({"events": [wrong_event]}, {"events": [requested_event]}))

    async def fake_fetch(_: dict[str, str]) -> dict:
        return next(payloads)

    monkeypatch.setattr(espn_mma, "fetch_scoreboard", fake_fetch)

    event = await espn_mma.get_event("600000001")

    assert event.id == "600000001"


async def test_close_still_closes_the_http_client_when_redis_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = False

    class FailingRedis:
        async def aclose(self) -> None:
            raise TimeoutError("timed out")

    class HttpClient:
        async def aclose(self) -> None:
            nonlocal closed
            closed = True

    monkeypatch.setattr(espn_mma, "_redis", FailingRedis())
    monkeypatch.setattr(espn_mma, "_http_client", HttpClient())

    await espn_mma.close()

    assert closed
    assert espn_mma._http_client is None


async def test_redis_client_uses_short_timeouts_and_does_not_retry() -> None:
    client = espn_mma._build_redis_client("redis://127.0.0.1:6379/0")
    kwargs = client.connection_pool.connection_kwargs
    try:
        assert kwargs["socket_timeout"] == espn_mma.REDIS_SOCKET_TIMEOUT_SECONDS
        assert kwargs["socket_connect_timeout"] == espn_mma.REDIS_SOCKET_TIMEOUT_SECONDS
        assert kwargs["decode_responses"] is True
        assert kwargs["retry"].get_retries() == 0
    finally:
        await client.aclose()


async def test_hanging_redis_falls_back_to_espn_and_process_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    params = {"event": "600000001"}
    upstream = Upstream(payload={"events": [{"id": "600000001"}]})
    install_upstream(monkeypatch, upstream)

    async with blackhole_redis() as client:
        monkeypatch.setattr(espn_mma, "_redis", client)
        started = monotonic()
        payload = await asyncio.wait_for(espn_mma.fetch_scoreboard(params), timeout=5)
        elapsed = monotonic() - started

        assert payload == {"events": [{"id": "600000001"}]}
        assert upstream.calls == 1
        # The floor shows the client waited out the socket timeout instead of
        # skipping Redis or blocking with no deadline. The ceiling leaves room
        # for the follow-up write to time out too, and fails a retry storm.
        assert 0.25 <= elapsed < 4, elapsed

        started = monotonic()
        again = await espn_mma.fetch_scoreboard(params)
        assert again == payload
        assert upstream.calls == 1
        assert monotonic() - started < 0.2


@pytest.mark.parametrize(
    "error",
    [
        RedisError("connection refused"),
        RedisTimeoutError("Timeout reading from socket"),
        TimeoutError("timed out"),
    ],
)
async def test_failing_redis_falls_back_to_espn(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    params = {"event": "600000001"}
    upstream = Upstream(payload={"events": [{"id": "from-espn"}]})
    install_upstream(monkeypatch, upstream)
    monkeypatch.setattr(espn_mma, "_redis", FakeRedis(error=error))

    payload = await espn_mma.fetch_scoreboard(params)

    assert payload == {"events": [{"id": "from-espn"}]}
    assert upstream.calls == 1


async def test_redis_write_timeout_still_returns_the_scoreboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    params = {"event": "600000001"}
    payload = {"events": [{"id": "from-espn"}]}
    upstream = Upstream(payload=payload)
    install_upstream(monkeypatch, upstream)
    redis = FakeRedis(write_error=TimeoutError("timed out"))
    monkeypatch.setattr(espn_mma, "_redis", redis)

    assert await espn_mma.fetch_scoreboard(params) == payload

    cache_key, _redis_key = redis_key_for(params)
    assert espn_mma._fresh_cached(cache_key) == payload
    assert redis.writes == 1
    assert upstream.calls == 1


async def test_fresh_process_cache_skips_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    params = {"event": "600000001"}
    cache_key, shared_key = redis_key_for(params)
    local = {"events": [{"id": "local"}]}
    seed_process_cache(cache_key, local, ttl=30)
    redis = FakeRedis({shared_key: (json.dumps({"events": [{"id": "shared"}]}), 30)})
    upstream = Upstream(payload={"events": [{"id": "espn"}]})
    install_upstream(monkeypatch, upstream)
    monkeypatch.setattr(espn_mma, "_redis", redis)

    assert await espn_mma.fetch_scoreboard(params) == local
    assert redis.reads == 0
    assert upstream.calls == 0


async def test_redis_hit_is_promoted_for_the_remaining_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    params = {"event": "600000001"}
    cache_key, shared_key = redis_key_for(params)
    shared = {"events": [{"id": "shared"}]}
    redis = FakeRedis({shared_key: (json.dumps(shared), 7)})
    upstream = Upstream(payload={"events": [{"id": "espn"}]})
    install_upstream(monkeypatch, upstream)
    monkeypatch.setattr(espn_mma, "_redis", redis)

    assert await espn_mma.fetch_scoreboard(params) == shared

    entry = espn_mma._scoreboard_cache[cache_key]
    remaining = entry.expires_at - monotonic()
    assert 0 < remaining <= 7
    assert redis.reads == 1
    assert redis.writes == 0
    assert upstream.calls == 0

    redis.error = RedisError("redis down")
    assert await espn_mma.fetch_scoreboard(params) == shared
    assert redis.reads == 1
    assert upstream.calls == 0


async def test_redis_hit_with_no_remaining_ttl_is_not_promoted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    params = {"event": "600000001"}
    _cache_key, shared_key = redis_key_for(params)
    shared = {"events": [{"id": "shared"}]}
    redis = FakeRedis({shared_key: (json.dumps(shared), 0)})
    upstream = Upstream(payload={"events": [{"id": "espn"}]})
    install_upstream(monkeypatch, upstream)
    monkeypatch.setattr(espn_mma, "_redis", redis)

    assert await espn_mma.fetch_scoreboard(params) == shared
    assert espn_mma._scoreboard_cache == {}

    redis.error = RedisError("redis down")
    assert await espn_mma.fetch_scoreboard(params) == {"events": [{"id": "espn"}]}
    assert upstream.calls == 1


async def test_corrupt_redis_value_falls_back_to_espn(monkeypatch: pytest.MonkeyPatch) -> None:
    params = {"event": "600000001"}
    _cache_key, shared_key = redis_key_for(params)
    redis = FakeRedis({shared_key: ("not-json", 30)})
    upstream = Upstream(payload={"events": [{"id": "espn"}]})
    install_upstream(monkeypatch, upstream)
    monkeypatch.setattr(espn_mma, "_redis", redis)

    assert await espn_mma.fetch_scoreboard(params) == {"events": [{"id": "espn"}]}
    assert upstream.calls == 1


async def _fetch_with_stale(
    monkeypatch: pytest.MonkeyPatch,
    upstream: Upstream,
    *,
    ttl: float,
) -> dict[str, Any]:
    params = {"event": "600000001"}
    cache_key, _shared_key = redis_key_for(params)
    seed_process_cache(cache_key, {"events": [{"id": "stale"}]}, ttl=ttl)
    install_upstream(monkeypatch, upstream)
    return await espn_mma.fetch_scoreboard(params)


async def test_stale_scoreboard_is_served_when_espn_times_out_within_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    params = {"event": "600000001"}
    cache_key, _shared_key = redis_key_for(params)
    seed_process_cache(cache_key, {"events": [{"id": "stale"}]}, ttl=-10)
    expires_at = espn_mma._scoreboard_cache[cache_key].expires_at
    upstream = Upstream(error=httpx.TimeoutException("timed out"))
    install_upstream(monkeypatch, upstream)

    assert await espn_mma.fetch_scoreboard(params) == {"events": [{"id": "stale"}]}
    assert upstream.calls == 1
    assert espn_mma._scoreboard_cache[cache_key].expires_at == expires_at


async def test_stale_scoreboard_is_served_on_server_error_within_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upstream = Upstream(status=503)
    assert await _fetch_with_stale(monkeypatch, upstream, ttl=-10) == {"events": [{"id": "stale"}]}
    assert upstream.calls == 1


async def test_stale_scoreboard_is_served_when_espn_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upstream = Upstream(error=httpx.ConnectError("connection refused"))
    assert await _fetch_with_stale(monkeypatch, upstream, ttl=-1) == {"events": [{"id": "stale"}]}


async def test_stale_scoreboard_is_not_served_past_the_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upstream = Upstream(error=httpx.TimeoutException("timed out"))
    with pytest.raises(EspnMmaTimeoutError, match="UFC event provider timed out"):
        await _fetch_with_stale(
            monkeypatch,
            upstream,
            ttl=-(espn_mma.STALE_ON_ERROR_SECONDS + 1),
        )
    assert upstream.calls == 1


async def test_provider_timeout_without_a_cached_scoreboard_still_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upstream = Upstream(error=httpx.TimeoutException("timed out"))
    install_upstream(monkeypatch, upstream)

    with pytest.raises(EspnMmaTimeoutError, match="UFC event provider timed out"):
        await espn_mma.fetch_scoreboard({"event": "600000001"})


async def test_client_error_does_not_serve_a_stale_scoreboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upstream = Upstream(status=400)
    with pytest.raises(EspnMmaRequestError, match="UFC event provider request failed"):
        await _fetch_with_stale(monkeypatch, upstream, ttl=-10)
    assert upstream.calls == 1


async def test_malformed_payload_does_not_serve_a_stale_scoreboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upstream = Upstream(content=b"not-json")
    with pytest.raises(EspnMmaDataError, match="invalid JSON"):
        await _fetch_with_stale(monkeypatch, upstream, ttl=-10)


async def test_stale_entry_survives_caching_a_different_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale_params = {"event": "600000001"}
    other_params = {"event": "600000002"}
    stale_key, _shared = redis_key_for(stale_params)
    seed_process_cache(stale_key, {"events": [{"id": "stale"}]}, ttl=-10)
    upstream = Upstream(payload={"events": [{"id": "other"}]})
    install_upstream(monkeypatch, upstream)

    assert await espn_mma.fetch_scoreboard(other_params) == {"events": [{"id": "other"}]}
    upstream.error = httpx.TimeoutException("timed out")
    assert await espn_mma.fetch_scoreboard(stale_params) == {"events": [{"id": "stale"}]}
