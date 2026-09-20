from app.espn import normalize_event


def test_normalizes_espn_event() -> None:
    event = normalize_event(
        {
            "id": "600000001",
            "name": "UFC Test",
            "date": "2026-09-20T00:00Z",
            "status": {"type": {"description": "Final", "completed": True}},
            "competitions": [
                {
                    "id": "401000001",
                    "status": {"type": {"description": "Final", "completed": True}},
                    "type": {"abbreviation": "Lightweight"},
                    "competitors": [
                        {
                            "id": "1",
                            "winner": True,
                            "athlete": {
                                "displayName": "Winner",
                                "flag": {"alt": "United States"},
                            },
                            "records": [{"type": "total", "summary": "10-0-0"}],
                        },
                        {
                            "id": "2",
                            "winner": False,
                            "athlete": {"displayName": "Opponent"},
                            "records": [],
                        },
                    ],
                }
            ],
        }
    )

    assert event.bout_count == 1
    assert event.bouts[0].winner_id == "1"
    assert event.bouts[0].fighters[0].record == "10-0-0"
    assert event.bouts[0].fighters[0].country == "United States"
