import sqlite3
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.ai_hook import FAILED_ANSWER, AnswerResult, Citation
from app.db import SCHEMA_VERSION, Database
from app.main import create_app


def make_client(tmp_path, **kwargs):
    return TestClient(create_app(tmp_path / "test.sqlite3", **kwargs))


class FixedGenerator:
    def __init__(self, result):
        self.result = result

    def generate(self, question):
        return self.result


class RaisingGenerator:
    def generate(self, question):
        raise RuntimeError("secret internal detail")


class SlowGenerator:
    def generate(self, question):
        time.sleep(2)
        return AnswerResult(answer="late", status="ok")


# ---- schema migration ------------------------------------------------------

LEGACY_SCHEMA = """CREATE TABLE questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT NOT NULL,
    ai_answer TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
    reviewed_answer TEXT, reviewer TEXT, created_at TEXT NOT NULL, reviewed_at TEXT)"""


def test_legacy_database_is_upgraded_without_losing_rows(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    db = sqlite3.connect(path)
    db.execute(LEGACY_SCHEMA)
    db.execute("INSERT INTO questions (question, ai_answer, created_at) VALUES ('Old pending', 'ph', 't1')")
    db.execute("""INSERT INTO questions (question, ai_answer, status, reviewed_answer, reviewer, created_at, reviewed_at)
                  VALUES ('Old approved', 'ph', 'approved', 'Verified', 'M', 't2', 't3')""")
    db.commit()
    db.close()

    client = TestClient(create_app(path))
    items = client.get("/api/questions").json()
    assert [i["question"] for i in items] == ["Old approved", "Old pending"]
    assert all(i["ai_status"] == "placeholder" and i["citations"] == [] for i in items)
    assert items[0]["reviewed_answer"] == "Verified"
    # New rows continue the old id sequence.
    assert client.post("/api/questions", json={"question": "New"}).json()["id"] == 3

    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_migration_is_idempotent_and_enforces_status(tmp_path):
    database = Database(tmp_path / "x.sqlite3")
    database.migrate()
    database.migrate()  # second run is a no-op
    with pytest.raises(sqlite3.IntegrityError):
        with database.connect() as db:
            db.execute("INSERT INTO questions (question, ai_answer, status, created_at) "
                       "VALUES ('q', 'a', 'bogus', 't')")


def test_newer_schema_is_refused(tmp_path):
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    with pytest.raises(RuntimeError):
        create_app(path)


def test_health_reports_schema_version(tmp_path):
    assert make_client(tmp_path).get("/api/health").json()["schema_version"] == SCHEMA_VERSION


# ---- AI hook ---------------------------------------------------------------

def test_ai_result_and_citations_are_stored(tmp_path):
    result = AnswerResult(answer=" Run make dev. ", status="ok", citations=[
        Citation(source="README.md", snippet="make dev", locator="L10"),
        Citation(source="  "),  # blank source is dropped
    ])
    client = make_client(tmp_path, generator=FixedGenerator(result))
    item = client.post("/api/questions", json={"question": "How to run?"}).json()
    assert item["ai_status"] == "ok"
    assert item["ai_answer"] == "Run make dev."
    assert item["status"] == "pending"  # AI output never approves
    assert item["citations"] == [{"source": "README.md", "snippet": "make dev", "locator": "L10"}]
    assert client.get(f"/api/questions/{item['id']}").json()["citations"] == item["citations"]


@pytest.mark.parametrize("generator, error", [
    (RaisingGenerator(), "exception:RuntimeError"),
    (FixedGenerator("not a result"), "invalid_result"),
    (FixedGenerator(AnswerResult(answer="   ", status="ok")), "empty_answer"),
    (FixedGenerator(AnswerResult(answer="made up", status="failed", error="no_sources")), "no_sources"),
])
def test_ai_failures_keep_question_pending(tmp_path, generator, error):
    client = make_client(tmp_path, generator=generator)
    response = client.post("/api/questions", json={"question": "Q?"})
    assert response.status_code == 201
    item = response.json()
    assert item["ai_status"] == "failed"
    assert item["ai_error"] == error
    assert item["ai_answer"] == FAILED_ANSWER
    assert item["status"] == "pending"
    assert "secret" not in response.text


def test_ai_timeout_is_stored_as_failed(tmp_path):
    client = make_client(tmp_path, generator=SlowGenerator(), ai_timeout_seconds=0.2)
    item = client.post("/api/questions", json={"question": "Slow?"}).json()
    assert (item["ai_status"], item["ai_error"]) == ("failed", "timeout")


# ---- idempotent submission -------------------------------------------------

def test_repeated_client_request_id_returns_original(tmp_path):
    client = make_client(tmp_path)
    body = {"question": "Same?", "client_request_id": "abc-123"}
    first = client.post("/api/questions", json=body)
    second = client.post("/api/questions", json=body)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["id"] == second.json()["id"]
    assert len(client.get("/api/questions").json()) == 1


def test_client_request_id_reused_for_other_question_conflicts(tmp_path):
    client = make_client(tmp_path)
    client.post("/api/questions", json={"question": "A", "client_request_id": "k1"})
    assert client.post("/api/questions", json={"question": "B", "client_request_id": "k1"}).status_code == 409


def test_concurrent_duplicate_submissions_create_one_row(tmp_path):
    class Gate:
        """Hold both requests in the AI step so both pass the first lookup."""
        def __init__(self):
            self.barrier = threading.Barrier(2, timeout=5)

        def generate(self, question):
            self.barrier.wait()
            return AnswerResult(answer="draft", status="ok")

    client = make_client(tmp_path, generator=Gate())
    body = {"question": "Race?", "client_request_id": "race-1"}
    responses = []
    threads = [threading.Thread(target=lambda: responses.append(client.post("/api/questions", json=body)))
               for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(r.status_code for r in responses) == [200, 201]
    assert len({r.json()["id"] for r in responses}) == 1
    assert len(client.get("/api/questions").json()) == 1


@pytest.mark.parametrize("key", ["", "has space", "x" * 101])
def test_invalid_client_request_id_rejected(tmp_path, key):
    client = make_client(tmp_path)
    assert client.post("/api/questions", json={"question": "Q", "client_request_id": key}).status_code == 422


# ---- list limit and knowledge search ---------------------------------------

def test_list_limit(tmp_path):
    client = make_client(tmp_path)
    for i in range(3):
        client.post("/api/questions", json={"question": f"Q{i}"})
    assert [i["question"] for i in client.get("/api/questions?limit=2").json()] == ["Q2", "Q1"]
    assert client.get("/api/questions?limit=0").status_code == 422
    assert client.get("/api/questions?limit=501").status_code == 422


def test_knowledge_search(tmp_path):
    client = make_client(tmp_path)
    ids = [client.post("/api/questions", json={"question": q}).json()["id"]
           for q in ("How to run docker?", "Where is 100% coverage?", "Docker pending")]
    client.post(f"/api/questions/{ids[0]}/review", json={"answer": "Use compose.", "reviewer": "M"})
    client.post(f"/api/questions/{ids[1]}/review", json={"answer": "See CI.", "reviewer": "M"})

    def search(q):
        return [i["id"] for i in client.get("/api/knowledge", params={"q": q}).json()]

    assert search("DOCKER") == [ids[0]]          # case-insensitive, approved only
    assert search("compose") == [ids[0]]         # matches reviewed answer
    assert search("100%") == [ids[1]]            # % is literal, not a wildcard
    assert search("%") == [ids[1]]
    assert search("nothing") == []
    assert client.get("/api/knowledge?q=").status_code == 422


def test_pending_queue_has_no_default_cap(tmp_path):
    """The mentor queue must still see the oldest waiting questions past 100."""
    client = make_client(tmp_path)
    for i in range(105):
        client.post("/api/questions", json={"question": f"Q{i}"})
    pending = client.get("/api/questions?status=pending").json()
    assert len(pending) == 105
    assert pending[-1]["question"] == "Q0"
    # Other lists keep the default cap, and an explicit limit still applies to pending.
    assert len(client.get("/api/questions").json()) == 100
    assert len(client.get("/api/questions?status=pending&limit=10").json()) == 10
