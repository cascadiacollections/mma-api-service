import asyncio

import pytest

from app import espn
from app.espn import _payload_ttl


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
    espn._scoreboard_cache.clear()
    espn._cache_locks.clear()
    monkeypatch.setattr(espn, "_redis", None)
    monkeypatch.setattr(espn, "_get_http_client", lambda: fake_client)

    first, second = await asyncio.gather(
        espn.fetch_scoreboard({"event": "600000001"}),
        espn.fetch_scoreboard({"event": "600000001"}),
    )

    assert first == {"events": []}
    assert second == first
    assert fake_client.calls == 1
