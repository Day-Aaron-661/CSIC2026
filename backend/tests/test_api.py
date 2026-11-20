import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(tmp_path / "test.sqlite3"))


def ask(client, q="How do I start?"):
    return client.post("/api/questions", json={"question": q})


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


def test_question_created_pending(client):
    result = ask(client)
    assert result.status_code == 201
    data = result.json()
    assert data["status"] == "pending"
    assert "PLACEHOLDER" in data["ai_answer"]
    assert data["reviewed_answer"] is None


def test_blank_question_rejected(client):
    assert ask(client, "  ").status_code == 422


def test_list_and_filter(client):
    ask(client)
    assert len(client.get("/api/questions?status=pending").json()) == 1
    assert client.get("/api/questions?status=approved").json() == []


def test_get_missing_returns_404(client):
    assert client.get("/api/questions/999").status_code == 404


def test_review_updates_visible_answer(client):
    item_id = ask(client).json()["id"]
    response = client.post(f"/api/questions/{item_id}/review",
                           json={"answer": "Read README.", "reviewer": "Mentor"})
    assert response.status_code == 200
    result = client.get(f"/api/questions/{item_id}").json()
    assert result["status"] == "approved"
    assert result["reviewed_answer"] == "Read README."
    assert result["reviewer"] == "Mentor"


def test_double_review_returns_conflict(client):
    item_id = ask(client).json()["id"]
    url = f"/api/questions/{item_id}/review"
    body = {"answer": "A", "reviewer": "M"}
    assert client.post(url, json=body).status_code == 200
    assert client.post(url, json=body).status_code == 409


def test_approved_knowledge_only(client):
    first = ask(client, "First").json()["id"]
    ask(client, "Second")
    client.post(f"/api/questions/{first}/review", json={"answer": "Verified", "reviewer": "M"})
    knowledge = client.get("/api/knowledge").json()
    assert len(knowledge) == 1
    assert knowledge[0]["question"] == "First"
