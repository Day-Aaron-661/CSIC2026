"""Isolated backup prototype tests: never make a real external AI request."""
import pytest
from fastapi.testclient import TestClient

from app.ai import llm, prompts
from app.ai_hook import AnswerResult
from app.main import create_app


def test_default_mode_still_uses_honest_placeholder(tmp_path, monkeypatch):
    monkeypatch.delenv("CP2_AI", raising=False)
    client = TestClient(create_app(tmp_path / "placeholder.db"))
    assert client.get("/api/health").json()["mode"] == "placeholder"
    created = client.post("/api/questions", json={"question": "How do I start?"})
    assert created.status_code == 201
    data = created.json()
    assert data["ai_status"] == "placeholder"
    assert data["citations"] == []
    assert data["status"] == "pending"


def test_backup_gemini_wiring_citations_and_mentor_knowledge(tmp_path, monkeypatch):
    """Full HTTP -> B retriever -> B adapter -> DB -> mentor -> knowledge cycle."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "setup.md").write_text(
        "# Backend setup\n\nStart the backend using uvicorn app.main:app on port 8000.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CP2_AI", "gemini")
    monkeypatch.setenv("CP2_AI_DOCS_DIR", str(docs))
    calls = []

    def fake_llm(prompt, system=None):
        calls.append((prompt, system))
        if system == prompts.REWRITE_SYSTEM_PROMPT:
            return "start backend uvicorn"
        return "Use the documented backend startup command [1]."

    monkeypatch.setattr(llm, "call_api", fake_llm)

    client = TestClient(create_app(tmp_path / "rag.db"))
    assert client.get("/api/health").json()["mode"] == "gemini"
    first = client.post("/api/questions", json={
        "question": "How do I start the backend with uvicorn?",
        "client_request_id": "backup-test-1",
    })
    assert first.status_code == 201
    data = first.json()
    assert data["ai_status"] == "ok"
    assert data["status"] == "pending"
    assert data["citations"][0]["source"] == "setup.md"
    assert "[1]" in data["ai_answer"]
    assert calls

    # A lost frontend response can be safely retried with the same key.
    replay = client.post("/api/questions", json={
        "question": "How do I start the backend with uvicorn?",
        "client_request_id": "backup-test-1",
    })
    assert replay.status_code == 200
    assert replay.json()["id"] == data["id"]

    reviewed = client.post(f'/api/questions/{data["id"]}/review', json={
        "answer": "Run uvicorn app.main:app from backend/",
        "reviewer": "Backup tester",
    })
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "approved"

    # Remove the local document: only the approved knowledge should remain.
    (docs / "setup.md").unlink()
    second = client.post("/api/questions", json={
        "question": "How should I start the backend using uvicorn?",
    })
    assert second.status_code == 201
    second_data = second.json()
    assert second_data["ai_status"] == "ok"
    assert any(
        cite["source"] == f'knowledge#{data["id"]}'
        for cite in second_data["citations"]
    )


def test_no_api_key_fails_honestly_and_still_queues_for_mentor(tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "setup.md").write_text(
        "Backend startup: use uvicorn to start the backend server.", encoding="utf-8"
    )
    monkeypatch.setenv("CP2_AI", "gemini")
    monkeypatch.setenv("CP2_AI_DOCS_DIR", str(docs))
    monkeypatch.setenv("CP2_GEMINI_KEYS_FILE", str(tmp_path / "missing-keys.txt"))

    client = TestClient(create_app(tmp_path / "no-key.db"))
    response = client.post("/api/questions", json={"question": "Start backend with uvicorn"})
    assert response.status_code == 201
    item = response.json()
    assert item["ai_status"] == "failed"
    assert item["ai_error"] == "llm_not_configured"
    assert item["status"] == "pending"
    assert item["citations"] == []

    # The fixed AI failure message must not be approved without a real answer.
    assert client.post(f'/api/questions/{item["id"]}/review', json={
        "answer": item["ai_answer"], "reviewer": "Mentor"
    }).status_code == 422
    assert client.post(f'/api/questions/{item["id"]}/review', json={
        "answer": "Verified manually using the README.", "reviewer": "Mentor"
    }).status_code == 200


def test_no_documents_has_no_hallucinated_answer(tmp_path, monkeypatch):
    docs = tmp_path / "empty-docs"
    docs.mkdir()
    monkeypatch.setenv("CP2_AI", "gemini")
    monkeypatch.setenv("CP2_AI_DOCS_DIR", str(docs))

    def never_call(*args, **kwargs):
        raise AssertionError("No model call is needed without documents or knowledge")

    monkeypatch.setattr(llm, "call_api", never_call)
    client = TestClient(create_app(tmp_path / "no-context.db"))
    item = client.post("/api/questions", json={"question": "Unknown repository policy"}).json()
    assert item["ai_status"] == "failed"
    assert item["ai_error"] == "no_context"
    assert item["status"] == "pending"


def test_custom_generator_still_supported(tmp_path, monkeypatch):
    monkeypatch.setenv("CP2_AI", "invalid-mode")  # ignored when explicitly injected

    class CustomGenerator:
        def generate(self, question):
            return AnswerResult(answer="Fixture draft", status="ok")

    client = TestClient(create_app(tmp_path / "custom.db", generator=CustomGenerator()))
    assert client.get("/api/health").json()["mode"] == "custom"
    data = client.post("/api/questions", json={"question": "Test injected model"}).json()
    assert data["ai_status"] == "ok"


def test_unknown_mode_and_bad_timeout_fail_loudly(tmp_path, monkeypatch):
    monkeypatch.setenv("CP2_AI", "not-a-provider")
    with pytest.raises(ValueError, match="Unsupported CP2_AI"):
        create_app(tmp_path / "bad-provider.db")
    monkeypatch.setenv("CP2_AI", "placeholder")
    with pytest.raises(ValueError, match="must be positive"):
        create_app(tmp_path / "bad-timeout.db", ai_timeout_seconds=0)
