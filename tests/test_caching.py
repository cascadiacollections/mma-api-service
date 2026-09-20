import asyncio

import pytest

from app.providers import espn_mma
from app.providers.espn_mma import _payload_ttl


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
