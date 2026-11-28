"""CP2 API — isolated backup integration for the B Gemini adapter.

This branch is an opt-in fallback if the team's AI integration misses the demo.
It is NOT merged into main. Authentication is NOT implemented.

Environment variables:
  CP2_DB_PATH        SQLite database file
  CP2_CORS_ORIGINS   comma-separated allowed frontend origins
  CP2_AI_TIMEOUT     seconds to wait for a draft (default 30)
  CP2_AI             "placeholder" (default) or "gemini"
  CP2_AI_DOCS_DIR    directory containing safe project documents to retrieve
  CP2_GEMINI_KEYS_FILE  local gitignored credentials file
  CP2_GEMINI_MODEL   model identifier supported by your Gemini API account
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
AI_MODES = ("placeholder", "gemini")


def backup_generator(repo):
    """Select the model without changing A/B's existing generator interface.

    Import the B pipeline only when explicitly requested. CI and users without
    a provider key can keep running the existing placeholder prototype.
    """
    mode = (os.getenv("CP2_AI") or "placeholder").strip().lower() or "placeholder"
    if mode == "placeholder":
        return mode, PlaceholderGenerator()
    if mode == "gemini":
        from .ai.adapter import RagGenerator

        # Knowledge is read on each call, so a newly approved answer immediately
        # becomes eligible for retrieval on a later question.
        generator = RagGenerator(
            knowledge_source=lambda: repo.search_knowledge(None, 500)
        )
        return mode, generator
    raise ValueError(f"Unsupported CP2_AI={mode!r}; choose: {', '.join(AI_MODES)}")


def create_app(db_path=None, generator=None, ai_timeout_seconds=None):
    database = Database(db_path or os.getenv("CP2_DB_PATH", DEFAULT_DB))
    database.migrate()
    timeout = float(
        os.getenv("CP2_AI_TIMEOUT", "30")
        if ai_timeout_seconds is None else ai_timeout_seconds
    )
    if timeout <= 0:
        raise ValueError("CP2_AI_TIMEOUT must be positive")

    repo = QuestionRepository(database)
    if generator is None:
        mode, generator = backup_generator(repo)
    else:
        # Dependency-injected tests can still supply their own generator.
        mode = "custom"

    app = FastAPI(title="CP2 Onboarding Assistant API (backup)", version="0.2.0")
    app.state.ai_mode = mode
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip() for origin in
            os.getenv("CP2_CORS_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(build_router(repo, generator, timeout, mode))
    return app


app = create_app()
