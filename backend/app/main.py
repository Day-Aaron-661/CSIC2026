"""CP2 shared API. Demo-only identity; authentication is NOT implemented.

Environment variables:
  CP2_DB_PATH        SQLite file (default backend/data/cp2.sqlite3)
  CP2_CORS_ORIGINS   comma-separated allowed origins (default http://localhost:5173)
  CP2_AI_TIMEOUT     seconds to wait for an AI draft before storing it as failed (default 30)
"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .ai_hook import PlaceholderGenerator
from .db import Database
from .repository import QuestionRepository
from .routes import build_router

DEFAULT_DB = str(Path(__file__).resolve().parents[1] / "data" / "cp2.sqlite3")


def create_app(db_path=None, generator=None, ai_timeout_seconds=None):
    database = Database(db_path or os.getenv("CP2_DB_PATH", DEFAULT_DB))
    database.migrate()
    timeout = float(ai_timeout_seconds or os.getenv("CP2_AI_TIMEOUT", "30"))

    app = FastAPI(title="CP2 Onboarding Assistant API", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CP2_CORS_ORIGINS", "http://localhost:5173").split(","),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(build_router(QuestionRepository(database),
                                    generator or PlaceholderGenerator(), timeout))
    return app


app = create_app()
