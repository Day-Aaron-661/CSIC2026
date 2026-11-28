"""CP2_AI selects the answer generator; B's RagGenerator is wired in by A.

No test here reaches Claude or Gemini: the network is blocked and the LLM
call (or the Anthropic client) is faked.
"""
import urllib.request
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.ai import claude_llm, llm
from app.ai.adapter import RagGenerator
from app.ai_hook import PLACEHOLDER_ANSWER, AnswerResult
from app.db import Database
from app.main import create_app, backup_generator
from app.repository import QuestionRepository


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    def blocked(*args, **kwargs):
        raise AssertionError("tests must not call the real Gemini API")

    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setenv("CP2_GEMINI_KEYS_FILE", str(tmp_path / "no-keys.txt"))
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CP2_CLAUDE_MODEL", "CP2_CLAUDE_EFFORT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(claude_llm, "_client", None)
    docs = tmp_path / "docs"
    docs.mkdir()
    monkeypatch.setenv("CP2_AI_DOCS_DIR", str(docs))
    return docs


def make_client(tmp_path):
    return TestClient(create_app(tmp_path / "test.sqlite3"))


def fake_llm(monkeypatch, answer):
    """Replace the Gemini call; query rewriting gets an empty reply (plain BM25)."""
    prompts = []

    def call(prompt, system=None):
        prompts.append(prompt)
        return "" if "rewrite" in (system or "").lower() else answer

    monkeypatch.setattr(llm, "call_api", call)
    return prompts


# ---- selection -------------------------------------------------------------

@pytest.mark.parametrize("value", [None, "", "placeholder", " Placeholder "])
def test_placeholder_is_the_default(monkeypatch, tmp_path, value):
    if value is None:
        monkeypatch.delenv("CP2_AI", raising=False)
    else:
        monkeypatch.setenv("CP2_AI", value)
    client = make_client(tmp_path)
    assert client.get("/api/health").json()["mode"] == "placeholder"
    item = client.post("/api/questions", json={"question": "Q?"}).json()
    assert (item["ai_status"], item["ai_answer"]) == ("placeholder", PLACEHOLDER_ANSWER)


def test_gemini_mode_uses_rag_generator(monkeypatch, tmp_path):
    monkeypatch.setenv("CP2_AI", "gemini")
    assert make_client(tmp_path).get("/api/health").json()["mode"] == "gemini"
    database = Database(tmp_path / "x.sqlite3")
    database.migrate()
    mode, generator = backup_generator(QuestionRepository(database))
    assert mode == "gemini" and isinstance(generator, RagGenerator)


def test_claude_mode_uses_rag_generator_with_claude_call(monkeypatch, tmp_path):
    monkeypatch.setenv("CP2_AI", "claude")
    assert make_client(tmp_path).get("/api/health").json()["mode"] == "claude"
    database = Database(tmp_path / "x.sqlite3")
    database.migrate()
    mode, generator = backup_generator(QuestionRepository(database))
    assert mode == "claude" and isinstance(generator, RagGenerator)
    assert generator.options["call"] is claude_llm.call_api


def test_unknown_mode_fails_at_startup(monkeypatch, tmp_path):
    monkeypatch.setenv("CP2_AI", "gemni")
    with pytest.raises(ValueError, match="gemni"):
        create_app(tmp_path / "test.sqlite3")


def test_injected_generator_wins_over_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CP2_AI", "gemini")

    class Fixed:
        def generate(self, question):
            return AnswerResult(answer="injected", status="ok")

    client = TestClient(create_app(tmp_path / "test.sqlite3", generator=Fixed()))
    assert client.get("/api/health").json()["mode"] == "custom"
    assert client.post("/api/questions", json={"question": "Q?"}).json()["ai_answer"] == "injected"


# ---- gemini mode end to end (LLM faked) ------------------------------------

def test_gemini_draft_with_document_citation(monkeypatch, tmp_path, offline):
    monkeypatch.setenv("CP2_AI", "gemini")
    (offline / "SETUP.md").write_text("# Setup\nStart the dev server with make dev.\n", encoding="utf-8")
    fake_llm(monkeypatch, "Run `make dev` [1].")
    client = make_client(tmp_path)

    item = client.post("/api/questions", json={"question": "How do I start the dev server?"}).json()
    assert item["ai_status"] == "ok"
    assert item["status"] == "pending"  # the AI never approves
    assert item["ai_answer"].startswith("Run `make dev` [1].")
    assert [c["source"] for c in item["citations"]] == ["SETUP.md"]


def test_gemini_reuses_approved_answers(monkeypatch, tmp_path):
    """Approved answers reach the prompt through knowledge_source (no documents here)."""
    monkeypatch.setenv("CP2_AI", "gemini")
    prompts = fake_llm(monkeypatch, "Use the approved steps [1].")
    client = make_client(tmp_path)

    first = client.post("/api/questions", json={"question": "Where is the staging password?"}).json()
    assert (first["ai_status"], first["ai_error"]) == ("failed", "no_context")  # nothing to cite yet
    client.post(f"/api/questions/{first['id']}/review",
                json={"answer": "Ask the team lead; it is not in the repo.", "reviewer": "M"})

    second = client.post("/api/questions", json={"question": "staging password location?"}).json()
    assert second["ai_status"] == "ok"
    assert [c["source"] for c in second["citations"]] == [f"knowledge#{first['id']}"]
    assert "Ask the team lead" in prompts[-1]


def test_gemini_without_keys_still_saves_the_question(monkeypatch, tmp_path, offline):
    monkeypatch.setenv("CP2_AI", "gemini")
    (offline / "SETUP.md").write_text("Start the dev server with make dev.\n", encoding="utf-8")
    client = make_client(tmp_path)  # CP2_GEMINI_KEYS_FILE points at a missing file

    response = client.post("/api/questions", json={"question": "How do I start the dev server?"})
    assert response.status_code == 201
    item = response.json()
    assert (item["ai_status"], item["ai_error"], item["status"]) == ("failed", "llm_not_configured", "pending")


# ---- claude mode (Anthropic client faked) ----------------------------------

class FakeAnthropic:
    """Stands in for anthropic.Anthropic; records each messages.create call."""

    def __init__(self, reply="", stop_reason="end_turn", api_key="test-key"):
        self.api_key, self.auth_token, self.credentials = api_key, None, None
        self.calls = []

        def create(**params):
            self.calls.append(params)
            text = "" if "rewrite" in (params.get("system") or "").lower() else reply
            return SimpleNamespace(stop_reason=stop_reason, stop_details=None,
                                   content=[SimpleNamespace(type="thinking", thinking=""),
                                            SimpleNamespace(type="text", text=text)])

        self.beta = SimpleNamespace(messages=SimpleNamespace(create=create))


def test_claude_draft_with_document_citation(monkeypatch, tmp_path, offline):
    monkeypatch.setenv("CP2_AI", "claude")
    (offline / "SETUP.md").write_text("# Setup\nStart the dev server with make dev.\n", encoding="utf-8")
    fake = FakeAnthropic(reply="Run `make dev` [1].")
    monkeypatch.setattr(claude_llm, "_client", fake)
    client = make_client(tmp_path)

    item = client.post("/api/questions", json={"question": "How do I start the dev server?"}).json()
    assert (item["ai_status"], item["status"]) == ("ok", "pending")
    assert item["ai_answer"].startswith("Run `make dev` [1].")
    assert [c["source"] for c in item["citations"]] == ["SETUP.md"]
    answer_call = fake.calls[-1]
    assert answer_call["model"] == "claude-opus-5-5"
    assert answer_call["output_config"] == {"effort": "low"}
    assert answer_call["fallbacks"] == "default"
    assert "thinking" not in answer_call  # always on for this model; effort controls depth
    assert answer_call["system"] and "SETUP.md" in answer_call["messages"][0]["content"]


def test_claude_without_credentials_still_saves_the_question(monkeypatch, tmp_path, offline):
    monkeypatch.setenv("CP2_AI", "claude")
    (offline / "SETUP.md").write_text("Start the dev server with make dev.\n", encoding="utf-8")
    fake = FakeAnthropic(api_key=None)
    monkeypatch.setattr(claude_llm, "_client", fake)
    client = make_client(tmp_path)

    item = client.post("/api/questions", json={"question": "How do I start the dev server?"}).json()
    assert (item["ai_status"], item["ai_error"], item["status"]) == ("failed", "llm_not_configured", "pending")
    assert fake.calls == []  # never sent a request


def test_claude_refusal_becomes_a_failed_draft(monkeypatch, tmp_path, offline):
    monkeypatch.setenv("CP2_AI", "claude")
    (offline / "SETUP.md").write_text("Start the dev server with make dev.\n", encoding="utf-8")
    monkeypatch.setattr(claude_llm, "_client", FakeAnthropic(reply="", stop_reason="refusal"))
    client = make_client(tmp_path)

    item = client.post("/api/questions", json={"question": "How do I start the dev server?"}).json()
    assert (item["ai_status"], item["ai_error"]) == ("failed", "llm_error:ClaudeRefused")
