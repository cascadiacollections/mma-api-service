import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi import Path as ApiPath
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.espn import close_cache, default_event_window, get_event, list_events
from app.grading import grade_picks
from app.models import Event, EventSummary, GradeReport, PickSubmission

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
REVISION = os.getenv("K_REVISION") or os.getenv("BUILD_SHA") or "development"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_cache()


app = FastAPI(
    title="MMA Pick'em API",
    version="0.1.0",
    description="UFC event cards, winner picks, and pick grading.",
    contact={
        "name": "Kevin T. Coughlin",
        "url": "https://github.com/cascadiacollections/mma-api-service",
    },
    license_info={"name": "MIT", "identifier": "MIT"},
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; base-uri 'none'; connect-src 'self'; "
        "form-action 'none'; frame-ancestors 'none'; img-src 'self' data:; "
        "script-src 'self'; style-src 'self'",
    )
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.scheme == "https":
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    if request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "public, max-age=3600")
    return response


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "revision": REVISION}


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
async def event(
    response: Response,
    event_id: str = ApiPath(pattern=r"^\d{6,20}$"),
) -> Event:
    ufc_event = await get_event(event_id)
    if ufc_event.completed:
        response.headers["Cache-Control"] = "public, max-age=3600, s-maxage=86400"
    elif ufc_event.status.lower() in {"in progress", "live"}:
        response.headers["Cache-Control"] = "public, max-age=5, s-maxage=15"
    else:
        response.headers["Cache-Control"] = "public, max-age=300, s-maxage=900"
    return ufc_event


@app.post("/api/events/{event_id}/grade", response_model=GradeReport)
async def grade(
    submission: PickSubmission,
    event_id: str = ApiPath(pattern=r"^\d{6,20}$"),
) -> GradeReport:
    return grade_picks(await get_event(event_id), submission)
