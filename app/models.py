from typing import Literal

from pydantic import BaseModel, Field


class Fighter(BaseModel):
    id: str
    name: str
    record: str | None = None
    country: str | None = None


class Bout(BaseModel):
    id: str
    order: int
    weight_class: str | None = None
    status: str
    completed: bool
    fighters: list[Fighter]
    winner_id: str | None = None


class EventSummary(BaseModel):
    id: str
    name: str
    date: str
    status: str
    completed: bool
    bout_count: int


class Event(EventSummary):
    bouts: list[Bout]


class PickSubmission(BaseModel):
    picks: dict[str, str] = Field(default_factory=dict, max_length=30)


class GradedPick(BaseModel):
    bout_id: str
    picked_fighter_id: str
    winner_id: str | None
    result: Literal["win", "loss", "pending", "void"]


class GradeSummary(BaseModel):
    wins: int
    losses: int
    pending: int
    void: int
    decided: int
    percentage: float | None


class GradeReport(BaseModel):
    event: EventSummary
    results: list[GradedPick]
    summary: GradeSummary
