"""HTTP routes. Contract: docs/API_CONTRACT.md."""
from fastapi import APIRouter, HTTPException, Query, Response

from .ai_hook import safe_generate
from .db import SCHEMA_VERSION
from .repository import Conflict, IntegrityError, NotFound
from .schemas import AskRequest, HealthOut, QuestionOut, ReviewRequest

STATUS_PATTERN = "^(pending|approved)$"


def build_router(repo, generator, ai_timeout_seconds):
    router = APIRouter(prefix="/api")

    def get_or_404(question_id):
        try:
            return repo.get(question_id)
        except NotFound:
            raise HTTPException(404, "Question not found") from None

    def replay(client_request_id, question, response):
        """Return the stored question for a repeated key, or None if unseen."""
        found = repo.find_by_request_id(client_request_id)
        if found is None:
            return None
        stored_question, item = found
        if stored_question != question:
            raise HTTPException(409, "client_request_id was already used for a different question")
        response.status_code = 200  # not newly created
        return item

    @router.get("/health", response_model=HealthOut)
    def health():
        return {"ok": True, "mode": "scaffold", "schema_version": SCHEMA_VERSION}

    @router.post("/questions", status_code=201, response_model=QuestionOut)
    def ask(payload: AskRequest, response: Response):
        question = payload.question.strip()
        if not question:
            raise HTTPException(422, "Question cannot be blank")
        key = payload.client_request_id
        if key and (item := replay(key, question, response)):
            return item
        # The AI call happens outside any database transaction so a slow
        # model never holds a SQLite lock.
        result = safe_generate(generator, question, ai_timeout_seconds)
        try:
            return repo.create(question, result, key)
        except IntegrityError:
            # Another request with the same key won the race.
            if key and (item := replay(key, question, response)):
                return item
            raise

    @router.get("/questions", response_model=list[QuestionOut])
    def list_questions(status: str | None = Query(default=None, pattern=STATUS_PATTERN),
                       limit: int = Query(default=100, ge=1, le=500)):
        return repo.list(status, limit)

    @router.get("/questions/{question_id}", response_model=QuestionOut)
    def get_question(question_id: int):
        return get_or_404(question_id)

    @router.post("/questions/{question_id}/review", response_model=QuestionOut)
    def review(question_id: int, payload: ReviewRequest):
        answer = payload.answer.strip()
        reviewer = payload.reviewer.strip()
        if not answer or not reviewer:
            raise HTTPException(422, "Answer and reviewer cannot be blank")
        try:
            return repo.approve(question_id, answer, reviewer)
        except NotFound:
            raise HTTPException(404, "Question not found") from None
        except Conflict:
            raise HTTPException(409, "Already reviewed") from None

    @router.get("/knowledge", response_model=list[QuestionOut])
    def knowledge(q: str | None = Query(default=None, min_length=1, max_length=200),
                  limit: int = Query(default=100, ge=1, le=500)):
        return repo.search_knowledge(q.strip() if q else None, limit)

    return router
