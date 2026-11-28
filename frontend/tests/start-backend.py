"""Run the real API against a disposable database for browser tests."""
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
    with TemporaryDirectory(prefix="csic2026-e2e-") as temporary_directory:
        # Set these before app.main is imported and creates its application.
        os.environ["CP2_DB_PATH"] = str(Path(temporary_directory) / "questions.sqlite3")
        os.environ["CP2_CORS_ORIGINS"] = "http://localhost:5173"
        os.environ["CP2_AI"] = "placeholder"  # e2e never calls a real model
        uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="warning")
