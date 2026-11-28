"""The backup's preflight never calls a provider and never prints keys."""
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/backup_preflight.py"


def run_check(tmp_path, mode, *, with_key=False):
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "setup.md").write_text("# Run backend\\nUse uvicorn.\\n", encoding="utf-8")
    key_path = tmp_path / "keys.txt"
    if with_key:
        key_path.write_text("FAKE-KEY-DO-NOT-PRINT\\n", encoding="utf-8")
    env = dict(os.environ, CP2_AI=mode, CP2_GEMINI_KEYS_FILE=str(key_path))
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    if mode == "claude" and with_key:
        env["ANTHROPIC_API_KEY"] = "FAKE-KEY-DO-NOT-PRINT"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--mode", mode, "--docs", str(docs)],
        text=True, capture_output=True, check=False, env=env,
    )
    assert "FAKE-KEY-DO-NOT-PRINT" not in result.stdout + result.stderr
    return result


def test_placeholder_check_passes_without_model(tmp_path):
    result = run_check(tmp_path, "placeholder")
    assert result.returncode == 0
    assert "not a real AI answer" in result.stdout


def test_gemini_check_catches_missing_key_and_passes_after_local_setup(tmp_path):
    missing = run_check(tmp_path, "gemini")
    assert missing.returncode == 2 and "NEEDS SETUP" in missing.stdout
    configured = run_check(tmp_path, "gemini", with_key=True)
    assert configured.returncode == 0
    assert "still run a real-key question" in configured.stdout


def test_claude_check_catches_missing_credentials(tmp_path):
    missing = run_check(tmp_path, "claude")
    assert missing.returncode == 2
    configured = run_check(tmp_path, "claude", with_key=True)
    assert configured.returncode == 0
