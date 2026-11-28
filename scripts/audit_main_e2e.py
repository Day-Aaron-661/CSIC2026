#!/usr/bin/env python3
"""Evidence-only integrated smoke test against an immutable checkout of MAIN.

No changes to main; no external API key. Uses real FastAPI routes, actual B
retriever/adapter, SQLite, and a deterministic *fake* Gemini model call.
Browser UI cases are tested separately by MAIN's Playwright suite.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from fastapi.testclient import TestClient


def main():
    main_root = Path(os.environ["TESTED_MAIN"]).resolve()
    sys.path.insert(0, str(main_root / "backend"))
    cases = []

    def check(name, fn):
        try:
            detail = fn()
            cases.append({"name": name, "result": "PASS", "detail": detail or ""})
            print("PASS:", name, "|", detail or "")
        except BaseException as exc:
            cases.append({"name": name, "result": "FAIL", "detail": f"{type(exc).__name__}: {exc}"})
            print("FAIL:", name, "|", type(exc).__name__, str(exc))

    with tempfile.TemporaryDirectory(prefix="main-cp2-e2e-") as temp:
        td = Path(temp)
        docs = td / "docs"
        docs.mkdir()
        (docs / "setup.md").write_text(
            "# Backend setup\n\nStart the backend server with uvicorn app.main:app.\n",
            encoding="utf-8",
        )
        os.environ["CP2_AI_DOCS_DIR"] = str(docs)
        os.environ["CP2_AI"] = "gemini"
        os.environ["CP2_GEMINI_KEYS_FILE"] = str(td / "NO_REAL_KEYS.txt")
        os.environ["CP2_DB_PATH"] = str(td / "import.sqlite3")
        from app.ai import llm, prompts
        from app.main import create_app

        calls = []

        def stubbed_model(prompt, system=None):
            calls.append((prompt, system))
            if system == prompts.REWRITE_SYSTEM_PROMPT:
                return "backend start uvicorn"
            return "Start the backend with uvicorn as documented [1]."

        llm.call_api = stubbed_model
        db = td / "e2e.sqlite3"
        client = TestClient(create_app(db))
        state = {}

        def check_health():
            data = client.get("/api/health").json()
            assert data["ok"] is True and data["mode"] == "gemini", data
            return "mode=gemini; provider call still stubbed"
        check("GET health on MAIN (mode selected)", check_health)

        def submit():
            res = client.post("/api/questions", json={
                "question": "How to start the backend with uvicorn?",
                "client_request_id": "main-audit-question-1",
            })
            assert res.status_code == 201, res.text
            row = res.json()
            assert row["status"] == "pending" and row["ai_status"] == "ok", row
            assert row["citations"] and row["citations"][0]["source"] == "setup.md", row
            assert "[1]" in row["ai_answer"]
            state["id"] = row["id"]
            return "saved pending AI draft; structured source=setup.md"
        check("newcomer POST -> B retrieval -> cited AI draft", submit)

        def visible_pending():
            res = client.get("/api/questions?status=pending")
            assert res.status_code == 200
            assert any(x["id"] == state["id"] for x in res.json())
            return "pending question visible to mentor queue"
        check("mentor queue sees pending question", visible_pending)

        def blank():
            assert client.post("/api/questions", json={"question": "   "}).status_code == 422
            return "HTTP 422"
        check("blank question rejected", blank)

        def retry():
            before = len(calls)
            res = client.post("/api/questions", json={
                "question": "How to start the backend with uvicorn?",
                "client_request_id": "main-audit-question-1",
            })
            assert res.status_code == 200 and res.json()["id"] == state["id"]
            assert len(calls) == before, "replay unexpectedly called AI"
            assert client.post("/api/questions", json={
                "question": "Other question",
                "client_request_id": "main-audit-question-1",
            }).status_code == 409
            return "same key -> HTTP 200, original id, no extra model call; wrong text -> 409"
        check("duplicate/retry idempotency", retry)

        def review():
            res = client.post(f'/api/questions/{state["id"]}/review', json={
                "answer": "Verified: start with uvicorn app.main:app from backend/",
                "reviewer": "Main integrated test",
            })
            assert res.status_code == 200, res.text
            item = res.json()
            assert item["status"] == "approved" and item["reviewed_answer"].startswith("Verified:")
            return "mentor amended + approved answer"
        check("mentor edit -> approve", review)

        def reviewed_newcomer():
            res = client.get(f'/api/questions/{state["id"]}')
            item = res.json()
            assert res.status_code == 200
            assert item["status"] == "approved"
            assert item["reviewed_answer"].startswith("Verified:")
            assert item["ai_answer"].startswith("Start the backend")
            assert item["reviewed_answer"] != item["ai_answer"]
            return "reviewed answer and original AI draft both retained"
        check("newcomer GET sees reviewed answer", reviewed_newcomer)

        def conflict():
            assert client.post(f'/api/questions/{state["id"]}/review', json={
                "answer": "Second review", "reviewer": "Other mentor"
            }).status_code == 409
            return "second mentor gets HTTP 409"
        check("second mentor conflict", conflict)

        def reuse_knowledge():
            (docs / "setup.md").unlink()
            from app.ai import retriever
            retriever._CHUNK_CACHE.clear()
            res = client.post("/api/questions", json={"question": "How can I start backend using uvicorn?"})
            assert res.status_code == 201
            item = res.json()
            assert item["ai_status"] == "ok", item
            assert any(c["source"] == f'knowledge#{state["id"]}' for c in item["citations"]), item
            return "follow-up retrieved mentor-approved knowledge (not old docs)"
        check("approved answer retrievable by later newcomer", reuse_knowledge)

        def persist_restart():
            restarted = TestClient(create_app(db))
            row = restarted.get(f'/api/questions/{state["id"]}').json()
            assert row["reviewed_answer"].startswith("Verified:") and row["status"] == "approved"
            assert restarted.get(f'/api/questions/{state["id"]}/reviews').json()
            return "SQLite row + review history retained across fresh app instance"
        check("API restart preserves review", persist_restart)

        def no_context():
            new = td / "empty"
            new.mkdir()
            os.environ["CP2_AI_DOCS_DIR"] = str(new)
            cc = TestClient(create_app(td / "empty.sqlite3"))
            ans = cc.post("/api/questions", json={"question": "Completely unknown question"}).json()
            assert ans["ai_status"] == "failed" and ans["ai_error"] == "no_context"
            assert ans["status"] == "pending"
            return "no hallucinated answer; question stays pending"
        check("no-context failure mode", no_context)

        def model_failure():
            err_docs = td / "errdocs"
            err_docs.mkdir()
            (err_docs / "backend.txt").write_text("backend uvicorn startup help\n", encoding="utf-8")
            os.environ["CP2_AI_DOCS_DIR"] = str(err_docs)
            def offline(*args, **kwargs):
                raise NotImplementedError("no test credential")
            llm.call_api = offline
            cc = TestClient(create_app(td / "err.sqlite3"))
            ans = cc.post("/api/questions", json={"question": "backend uvicorn startup?"}).json()
            assert ans["status"] == "pending" and ans["ai_status"] == "failed", ans
            assert ans["ai_error"] == "llm_not_configured", ans
            assert not ans["citations"]
            return "failed AI draft not mistaken for a generated/approved answer"
        check("missing model/key outcome handled safely", model_failure)

        def network_failure():
            try:
                urlopen("http://127.0.0.1:9/api/health", timeout=1)
            except (URLError, ConnectionError, TimeoutError, OSError):
                return "connection refused as expected; browser UI tested by Playwright"
            raise AssertionError("unexpected server listening on reserved test port")
        check("backend disconnect / HTTP unreachable", network_failure)

    result = {
        "tested_ref": "main", "tested_sha": os.getenv("TESTED_SHA", ""),
        "tested_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "deterministic fake Gemini LLM (no live API credentials)",
        "scope": "real FastAPI + real B RAG + SQLite; browser E2E in separate Playwright CI",
        "cases": cases,
    }
    dest = Path(os.environ.get("REPORT_FILE", "main-e2e-report.json"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    failed = sum(c["result"] == "FAIL" for c in cases)
    print(f"Summary: {len(cases)-failed} passed, {failed} failed; report={dest}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
