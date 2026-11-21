import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

from app.ai_hook import AnswerResult, Citation
from app.db import _LEGACY_QUESTIONS, _migrate_to_v1
from app.main import create_app
from app.repository import TRANSITIONS


def ask(client, q="How do I start?"):
    return client.post("/api/questions", json={"question": q}).json()["id"]


def approve(client, item_id, answer="Read README.", reviewer="Mentor"):
    return client.post(f"/api/questions/{item_id}/review",
                       json={"answer": answer, "reviewer": reviewer})


@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "test.sqlite3"


@pytest.fixture()
def client(db_path):
    return TestClient(create_app(db_path))


# ---- state transitions -----------------------------------------------------

def test_transition_table_only_allows_pending_to_approved():
    assert TRANSITIONS == {"approve": ("pending", "approved")}


def test_approval_records_history(client):
    item_id = ask(client)
    assert approve(client, item_id, " Use make dev. ", " Ann ").status_code == 200
    history = client.get(f"/api/questions/{item_id}/reviews").json()
    assert len(history) == 1
    entry = history[0]
    assert (entry["version"], entry["action"], entry["answer"], entry["reviewer"]) == \
        (1, "approve", "Use make dev.", "Ann")
    question = client.get(f"/api/questions/{item_id}").json()
    assert entry["created_at"] == question["reviewed_at"]


def test_pending_question_has_empty_history(client):
    assert client.get(f"/api/questions/{ask(client)}/reviews").json() == []


def test_history_for_missing_question_is_404(client):
    assert client.get("/api/questions/999/reviews").status_code == 404


def test_rejected_second_review_leaves_history_unchanged(client):
    item_id = ask(client)
    approve(client, item_id, "First")
    assert approve(client, item_id, "Second").status_code == 409
    history = client.get(f"/api/questions/{item_id}/reviews").json()
    assert [h["answer"] for h in history] == ["First"]
    assert client.get(f"/api/questions/{item_id}").json()["reviewed_answer"] == "First"


def test_review_missing_question_is_404(client):
    assert approve(client, 999).status_code == 404


@pytest.mark.parametrize("body", [
    {"answer": "   ", "reviewer": "M"},
    {"answer": "A", "reviewer": "   "},
    {"answer": "", "reviewer": "M"},
    {"answer": "A"},
])
def test_blank_or_missing_review_fields_rejected(client, body):
    item_id = ask(client)
    assert client.post(f"/api/questions/{item_id}/review", json=body).status_code == 422
    assert client.get(f"/api/questions/{item_id}").json()["status"] == "pending"
    assert client.get(f"/api/questions/{item_id}/reviews").json() == []


def test_ai_result_never_approves(db_path):
    """Even an 'ok' AI draft with citations stays pending until a mentor reviews."""
    result = AnswerResult(answer="Draft", status="ok", citations=[Citation(source="README.md")])

    class Gen:
        def generate(self, question):
            return result

    client = TestClient(create_app(db_path, generator=Gen()))
    item_id = ask(client)
    assert client.get(f"/api/questions/{item_id}").json()["status"] == "pending"
    assert client.get("/api/knowledge").json() == []


# ---- atomicity -------------------------------------------------------------

def test_failed_history_write_rolls_back_approval(db_path):
    client = TestClient(create_app(db_path), raise_server_exceptions=False)
    item_id = ask(client)
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TRIGGER fail_reviews BEFORE INSERT ON reviews "
                   "BEGIN SELECT RAISE(ABORT, 'simulated failure'); END")
    assert approve(client, item_id).status_code == 500
    question = client.get(f"/api/questions/{item_id}").json()
    assert (question["status"], question["reviewed_answer"], question["reviewer"]) == \
        ("pending", None, None)
    assert client.get("/api/knowledge").json() == []


# ---- concurrency -----------------------------------------------------------

def test_concurrent_reviews_from_two_servers(db_path):
    """Two app instances (like two server processes) review the same questions at once."""
    first, second = TestClient(create_app(db_path)), TestClient(create_app(db_path))
    ids = [ask(first, f"Q{i}") for i in range(5)]
    for item_id in ids:
        barrier = threading.Barrier(2, timeout=5)
        results = {}

        def run(name, c):
            barrier.wait()
            results[name] = approve(c, item_id, f"answer from {name}", name)

        threads = [threading.Thread(target=run, args=("A", first)),
                   threading.Thread(target=run, args=("B", second))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sorted(r.status_code for r in results.values()) == [200, 409]
        winner = next(name for name, r in results.items() if r.status_code == 200)
        history = first.get(f"/api/questions/{item_id}/reviews").json()
        assert [(h["version"], h["reviewer"]) for h in history] == [(1, winner)]
        assert second.get(f"/api/questions/{item_id}").json()["reviewer"] == winner


# ---- persistence across restarts -------------------------------------------

def test_data_survives_restart(db_path):
    before = TestClient(create_app(db_path))
    pending_id = ask(before, "Still pending")
    approved_id = ask(before, "Approved one")
    approve(before, approved_id, "Verified", "Ann")
    del before

    after = TestClient(create_app(db_path))
    items = {i["id"]: i for i in after.get("/api/questions").json()}
    assert items[pending_id]["status"] == "pending"
    assert items[approved_id]["reviewed_answer"] == "Verified"
    assert after.get(f"/api/questions/{approved_id}/reviews").json()[0]["reviewer"] == "Ann"
    assert [k["id"] for k in after.get("/api/knowledge").json()] == [approved_id]
    # The restarted server can keep working on old rows.
    assert approve(after, pending_id).status_code == 200
    assert approve(after, approved_id).status_code == 409


# ---- migration v1 -> v2 ----------------------------------------------------

def test_v1_database_gets_review_history_backfilled(db_path):
    db = sqlite3.connect(db_path)
    db.execute(_LEGACY_QUESTIONS)
    _migrate_to_v1(db)
    db.execute("PRAGMA user_version = 1")
    db.execute("""INSERT INTO questions (question, ai_answer, created_at) VALUES ('Open', 'ph', 't0')""")
    db.execute("""INSERT INTO questions (question, ai_answer, status, reviewed_answer, reviewer,
                  created_at, reviewed_at) VALUES ('Done', 'ph', 'approved', 'Yes', 'Ann', 't1', 't2')""")
    db.execute("INSERT INTO citations (question_id, source) VALUES (2, 'README.md')")
    db.commit()
    db.close()

    client = TestClient(create_app(db_path))
    assert client.get("/api/questions/1/reviews").json() == []
    assert client.get("/api/questions/2/reviews").json() == [
        {"version": 1, "action": "approve", "answer": "Yes", "reviewer": "Ann", "created_at": "t2"}]
    assert client.get("/api/questions/2").json()["citations"][0]["source"] == "README.md"
    assert client.get("/api/health").json()["schema_version"] == 2
    # Version numbering continues correctly for newly reviewed rows.
    approve(client, 1, "Now done", "Bo")
    assert client.get("/api/questions/1/reviews").json()[0]["version"] == 1


def test_knowledge_includes_citations(db_path):
    class Gen:
        def generate(self, question):
            return AnswerResult(answer="Draft", status="ok",
                                citations=[Citation(source="docs/SETUP.md", locator="§2")])

    client = TestClient(create_app(db_path, generator=Gen()))
    item_id = ask(client)
    approve(client, item_id)
    [entry] = client.get("/api/knowledge").json()
    assert entry["citations"] == [{"source": "docs/SETUP.md", "snippet": None, "locator": "§2"}]
