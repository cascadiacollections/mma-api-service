from fastapi import HTTPException

from app.models import Event, GradedPick, GradeReport, GradeSummary, PickSubmission


def grade_picks(event: Event, submission: PickSubmission) -> GradeReport:
    bouts_by_id = {bout.id: bout for bout in event.bouts}
    unknown_bouts = sorted(set(submission.picks) - set(bouts_by_id))
    if unknown_bouts:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown bout IDs: {', '.join(unknown_bouts)}",
        )

    results: list[GradedPick] = []
    for bout_id, picked_fighter_id in submission.picks.items():
        bout = bouts_by_id[bout_id]
        fighter_ids = {fighter.id for fighter in bout.fighters}
        if picked_fighter_id not in fighter_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Fighter {picked_fighter_id} is not in bout {bout_id}",
            )

        if not bout.completed:
            result = "pending"
        elif bout.winner_id is None:
            result = "void"
        elif picked_fighter_id == bout.winner_id:
            result = "win"
        else:
            result = "loss"

        results.append(
            GradedPick(
                bout_id=bout_id,
                picked_fighter_id=picked_fighter_id,
                winner_id=bout.winner_id,
                result=result,
            )
        )

    counts = {
        result: sum(graded.result == result for graded in results)
        for result in ("win", "loss", "pending", "void")
    }
    decided = counts["win"] + counts["loss"]
    percentage = round((counts["win"] / decided) * 100, 1) if decided else None

    return GradeReport(
        event=event,
        results=results,
        summary=GradeSummary(
            wins=counts["win"],
            losses=counts["loss"],
            pending=counts["pending"],
            void=counts["void"],
            decided=decided,
            percentage=percentage,
        ),
    )
