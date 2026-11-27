"""CP2 shared API. Demo-only identity; authentication is NOT implemented.

Environment variables:
  CP2_DB_PATH        SQLite file (default backend/data/cp2.sqlite3)
  CP2_CORS_ORIGINS   comma-separated allowed origins (default http://localhost:5173)
  CP2_AI_TIMEOUT     seconds to wait for an AI draft before storing it as failed (default 30)
  CP2_AI             answer generator: "placeholder" (default), "claude" or "gemini".
                     claude/gemini run B's RagGenerator pipeline with that model;
                     claude needs ANTHROPIC_API_KEY (TODO: set on the demo machine), see README
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


AI_MODES = ("placeholder", "claude", "gemini")


def default_generator(repo):
    """Pick the answer generator from CP2_AI. Returns (mode, generator).

    The default stays the placeholder so CI, tests and anyone without a
    Gemini key are unaffected. An unknown value fails at startup instead of
    silently falling back to placeholder answers.
    """
    mode = os.getenv("CP2_AI", "placeholder").strip().lower() or "placeholder"
    if mode == "placeholder":
        return mode, PlaceholderGenerator()
    if mode in ("claude", "gemini"):
        from .ai.adapter import RagGenerator  # imported only when enabled
        options = {}
        if mode == "claude":
            from .ai import claude_llm
            options["call"] = claude_llm.call_api  # gemini uses the pipeline default (llm.call_api)
        # Mentor-approved answers are retrieved alongside project documents,
        # so approved answers get reused in later drafts.
        return mode, RagGenerator(knowledge_source=lambda: repo.search_knowledge(None, 500), **options)
    raise RuntimeError(f"Unknown CP2_AI={mode!r}; use one of: {', '.join(AI_MODES)}")


def create_app(db_path=None, generator=None, ai_timeout_seconds=None):
    database = Database(db_path or os.getenv("CP2_DB_PATH", DEFAULT_DB))
    database.migrate()
    timeout = float(ai_timeout_seconds or os.getenv("CP2_AI_TIMEOUT", "30"))
    repo = QuestionRepository(database)
    if generator is None:
        mode, generator = default_generator(repo)
    else:
        mode = "custom"  # injected by a caller, e.g. tests

    app = FastAPI(title="CP2 Onboarding Assistant API", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CP2_CORS_ORIGINS", "http://localhost:5173").split(","),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(build_router(repo, generator, timeout, mode))
    return app


app = create_app()
