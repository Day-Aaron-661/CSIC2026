"""Offline regression tests for the safe backup launch and health/smoke CLI."""
import importlib.util
import io
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace


SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location("cp2_" + name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def demo_docs(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "safe.md").write_text("# Backend\n\nStart the server with uvicorn.\n", encoding="utf-8")
    return docs


def test_demo_gemini_prompt_uses_private_temporary_file(tmp_path, capsys):
    launch = load("backup_demo")
    docs = demo_docs(tmp_path)
    seen = []

    def runner(cmd, *, cwd, env, check):
        assert not check
        assert str(cwd).endswith("backend")
        assert "FAKE-GEMINI-KEY" not in " ".join(cmd)
        key_file = Path(env["CP2_GEMINI_KEYS_FILE"])
        assert key_file.read_text(encoding="utf-8") == "FAKE-GEMINI-KEY\n"
        assert stat.S_IMODE(key_file.stat().st_mode) == 0o600
        assert env["CP2_AI"] == "gemini"
        assert Path(env["CP2_DB_PATH"]).parent == key_file.parent
        seen.append(key_file)
        return SimpleNamespace(returncode=0)

    rc = launch.main(["--provider", "gemini", "--docs", str(docs)],
                     prompt=lambda _: "FAKE-GEMINI-KEY", runner=runner)
    assert rc == 0 and len(seen) == 1
    assert not seen[0].exists()
    output = capsys.readouterr()
    assert "FAKE-GEMINI-KEY" not in output.out + output.err


def test_demo_claude_key_only_in_child_env(tmp_path, capsys):
    launch = load("backup_demo")
    docs = demo_docs(tmp_path)

    def runner(cmd, *, cwd, env, check):
        assert env["ANTHROPIC_API_KEY"] == "FAKE-ANTHROPIC-KEY"
        assert env["CP2_AI"] == "claude"
        assert "FAKE-ANTHROPIC-KEY" not in " ".join(cmd)
        assert "CP2_GEMINI_KEYS_FILE" not in env
        return SimpleNamespace(returncode=0)

    rc = launch.main(["--provider", "claude", "--docs", str(docs)],
                     prompt=lambda _: "FAKE-ANTHROPIC-KEY", runner=runner)
    assert rc == 0
    output = capsys.readouterr()
    assert "FAKE-ANTHROPIC-KEY" not in output.out + output.err


def test_demo_empty_key_refuses_start_without_printing_secret(tmp_path, capsys):
    launch = load("backup_demo")
    docs = demo_docs(tmp_path)
    called = []

    def runner(*args, **kwargs):
        called.append(1)

    rc = launch.main(["--provider", "gemini", "--docs", str(docs)],
                     prompt=lambda _: "", runner=runner)
    assert rc == 2 and not called
    assert "No Gemini key entered" in capsys.readouterr().err


class JSONReply(io.BytesIO):
    def __init__(self, value, status=200):
        super().__init__(json.dumps(value).encode("utf-8"))
        self.status = status


def test_smoke_defaults_to_read_only(capsys):
    smoke = load("backup_smoke")
    requests = []

    def opener(request, *, timeout):
        requests.append(request)
        assert request.get_method() == "GET"
        return JSONReply({"ok": True, "mode": "gemini"})

    assert smoke.main([], opener=opener) == 0
    assert len(requests) == 1
    assert "selection does not prove" in capsys.readouterr().out


def test_smoke_explicit_submit_checks_status_and_citations_without_printing_answer(capsys):
    smoke = load("backup_smoke")
    requests = []

    def opener(request, *, timeout):
        requests.append(request)
        if request.get_method() == "GET":
            return JSONReply({"ok": True, "mode": "gemini"})
        body = json.loads(request.data)
        assert body["question"] == "How to start the demo?"
        assert body["client_request_id"].startswith("backup-smoke-")
        return JSONReply({"ai_status": "ok", "ai_answer": "SENSITIVE ANSWER",
                          "citations": [{"source": "private-doc.md", "snippet": "SECRET SOURCE"}]}, 201)

    rc = smoke.main(["--submit", "How to start the demo?", "--require-citations"], opener=opener)
    assert rc == 0 and len(requests) == 2
    out = capsys.readouterr().out
    assert "citations=1" in out
    assert "SENSITIVE ANSWER" not in out
    assert "SECRET SOURCE" not in out
    assert "private-doc.md" not in out


def test_smoke_rejects_missing_citations_and_failed_drafts(capsys):
    smoke = load("backup_smoke")
    for result, expected in [
        ({"ai_status": "ok", "citations": []}, 4),
        ({"ai_status": "failed", "ai_error": "llm_not_configured", "citations": []}, 3),
    ]:
        def opener(request, *, timeout):
            if request.get_method() == "GET":
                return JSONReply({"ok": True, "mode": "gemini"})
            return JSONReply(result, 201)
        assert smoke.main(["--submit", "Start uvicorn?", "--require-citations"], opener=opener) == expected
    assert "llm_not_configured" in capsys.readouterr().out
