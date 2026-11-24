"""Request and response models. Response fields are a superset of CP2 v0.1."""
from typing import Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    # Optional client-generated key (e.g. a UUID). Re-sending the same key
    # returns the original question instead of creating a duplicate.
    client_request_id: str | None = Field(
        default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class ReviewRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=10000)
    reviewer: str = Field(min_length=1, max_length=100)


class CitationOut(BaseModel):
    source: str
    snippet: str | None = None
    locator: str | None = None


class QuestionOut(BaseModel):
    id: int
    question: str
    ai_answer: str
    ai_status: Literal["placeholder", "ok", "failed"]
    ai_error: str | None = None
    status: Literal["pending", "approved"]
    reviewed_answer: str | None = None
    reviewer: str | None = None
    created_at: str
    reviewed_at: str | None = None
    citations: list[CitationOut] = []


class ReviewOut(BaseModel):
    version: int
    action: Literal["approve"]
    answer: str
    reviewer: str
    created_at: str


class HealthOut(BaseModel):
    ok: bool
    mode: str
    schema_version: int
