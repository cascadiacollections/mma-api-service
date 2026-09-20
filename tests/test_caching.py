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
