"""CP2 shared API. Demo-only identity; authentication is NOT implemented."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DEFAULT_DB = str(Path(__file__).resolve().parents[1] / "data" / "cp2.sqlite3")


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class ReviewRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=10000)
    reviewer: str = Field(min_length=1, max_length=100)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def create_app(db_path=None):
    path = str(db_path or os.getenv("CP2_DB_PATH", DEFAULT_DB))
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect():
        db = sqlite3.connect(path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            ai_answer TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            reviewed_answer TEXT,
            reviewer TEXT,
            created_at TEXT NOT NULL,
            reviewed_at TEXT
        )""")

    app = FastAPI(title="CP2 Onboarding Assistant API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CP2_CORS_ORIGINS", "http://localhost:5173").split(","),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    def get_one(question_id):
        with connect() as db:
            item = db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        if item is None:
            raise HTTPException(404, "Question not found")
        return dict(item)

    @app.get("/api/health")
    def health():
        return {"ok": True, "mode": "scaffold"}

    @app.post("/api/questions", status_code=201)
    def ask(payload: AskRequest):
        question = payload.question.strip()
        if not question:
            raise HTTPException(422, "Question cannot be blank")
        # AI owner replaces this placeholder in a separate reviewed PR.
        ai_answer = ("[DEMO PLACEHOLDER — NOT AI GENERATED] This question has been "
                     "submitted for mentor review. AI retrieval and citations are not implemented yet.")
        with connect() as db:
            cur = db.execute(
                "INSERT INTO questions (question, ai_answer, created_at) VALUES (?, ?, ?)",
                (question, ai_answer, now_iso()),
            )
            question_id = cur.lastrowid
        return get_one(question_id)

    @app.get("/api/questions")
    def list_questions(status: str | None = Query(default=None, pattern="^(pending|approved)$")):
        with connect() as db:
            if status:
                rows = db.execute("SELECT * FROM questions WHERE status=? ORDER BY id DESC", (status,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM questions ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]

    @app.get("/api/questions/{question_id}")
    def get_question(question_id: int):
        return get_one(question_id)

    @app.post("/api/questions/{question_id}/review")
    def review(question_id: int, payload: ReviewRequest):
        answer = payload.answer.strip()
        reviewer = payload.reviewer.strip()
        if not answer or not reviewer:
            raise HTTPException(422, "Answer and reviewer cannot be blank")
        with connect() as db:
            cur = db.execute(
                """UPDATE questions SET status='approved', reviewed_answer=?,
                   reviewer=?, reviewed_at=? WHERE id=? AND status='pending'""",
                (answer, reviewer, now_iso(), question_id),
            )
            if cur.rowcount == 0:
                existing = db.execute("SELECT id FROM questions WHERE id=?", (question_id,)).fetchone()
                raise HTTPException(404 if existing is None else 409,
                                    "Question not found" if existing is None else "Already reviewed")
        return get_one(question_id)

    @app.get("/api/knowledge")
    def knowledge():
        with connect() as db:
            rows = db.execute("SELECT * FROM questions WHERE status='approved' ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]

    return app


app = create_app()
