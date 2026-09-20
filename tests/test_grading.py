import pytest
from fastapi import HTTPException

from app.grading import grade_picks
from app.models import Bout, Event, Fighter, PickSubmission


@pytest.fixture
def event() -> Event:
    fighters = [
        Fighter(id="red", name="Red Fighter"),
        Fighter(id="blue", name="Blue Fighter"),
    ]
    return Event(
        id="event-1",
        name="UFC Test",
        date="2026-09-20T00:00:00Z",
        status="Final",
        completed=True,
        bout_count=4,
        bouts=[
            Bout(
                id="win",
                order=1,
                status="Final",
                completed=True,
                fighters=fighters,
                winner_id="red",
            ),
            Bout(
                id="loss",
                order=2,
                status="Final",
                completed=True,
                fighters=fighters,
                winner_id="red",
            ),
            Bout(
                id="pending",
                order=3,
                status="Scheduled",
                completed=False,
                fighters=fighters,
            ),
            Bout(
                id="void",
                order=4,
                status="Final",
                completed=True,
                fighters=fighters,
            ),
        ],
    )


def test_grades_wins_losses_pending_and_void(event: Event) -> None:
    report = grade_picks(
        event,
        PickSubmission(
            picks={
                "win": "red",
                "loss": "blue",
                "pending": "red",
                "void": "red",
            }
        ),
    )

    assert [result.result for result in report.results] == ["win", "loss", "pending", "void"]
    assert report.summary.wins == 1
    assert report.summary.losses == 1
    assert report.summary.pending == 1
    assert report.summary.void == 1
    assert report.summary.percentage == 50.0


def test_empty_submission_has_no_percentage(event: Event) -> None:
    report = grade_picks(event, PickSubmission())

    assert report.results == []
    assert report.summary.decided == 0
    assert report.summary.percentage is None


def test_rejects_fighter_outside_bout(event: Event) -> None:
    with pytest.raises(HTTPException, match="not in bout"):
        grade_picks(event, PickSubmission(picks={"win": "other"}))


def test_rejects_unknown_bout(event: Event) -> None:
    with pytest.raises(HTTPException, match="Unknown bout IDs"):
        grade_picks(event, PickSubmission(picks={"missing": "red"}))
