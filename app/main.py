from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.espn import close_cache, default_event_window, get_event, list_events
from app.grading import grade_picks
from app.models import Event, EventSummary, GradeReport, PickSubmission

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_cache()


app = FastAPI(
    title="MMA Pick'em API",
    version="0.1.0",
    description="UFC event cards, winner picks, and pick grading.",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/ready")
async def ready() -> dict[str, str]:
    return {"status": "ready"}


@app.get("/api/events", response_model=list[EventSummary])
async def events(
    response: Response,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> list[EventSummary]:
    default_start, default_end = default_event_window()
    start = start or default_start
    end = end or default_end
    if end < start:
        raise HTTPException(status_code=422, detail="end must not be before start")
    if (end - start).days > 366:
        raise HTTPException(status_code=422, detail="date range cannot exceed 366 days")
    response.headers["Cache-Control"] = (
        "public, max-age=300, s-maxage=600, stale-while-revalidate=60"
    )
    return await list_events(start, end)


@app.get("/api/events/{event_id}", response_model=Event)
async def event(event_id: str, response: Response) -> Event:
    ufc_event = await get_event(event_id)
    if ufc_event.completed:
        response.headers["Cache-Control"] = "public, max-age=86400, s-maxage=604800, immutable"
    elif ufc_event.status.lower() in {"in progress", "live"}:
        response.headers["Cache-Control"] = "public, max-age=5, s-maxage=15"
    else:
        response.headers["Cache-Control"] = "public, max-age=300, s-maxage=900"
    return ufc_event


@app.post("/api/events/{event_id}/grade", response_model=GradeReport)
async def grade(event_id: str, submission: PickSubmission) -> GradeReport:
    return grade_picks(await get_event(event_id), submission)
