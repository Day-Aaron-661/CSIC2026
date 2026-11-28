#!/usr/bin/env python3
"""Start the isolated CP2 backup API without sharing or committing API keys.

A credential is entered locally without terminal echo. The Gemini key lives
only in a 0600 temporary file while the process is running. Claude's key
lives only in the child-process environment. Nothing is sent to ChatGPT or
GitHub by this helper. The provider itself receives the key when called.
"""
import argparse
import getpass
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def make_child_env(provider, docs, database, temporary_dir, *, prompt=getpass.getpass):
    env = os.environ.copy()
    env["CP2_AI"] = provider
    env["CP2_AI_DOCS_DIR"] = str(Path(docs).resolve())
    env["CP2_DB_PATH"] = str(Path(database).resolve())
    env["CP2_CORS_ORIGINS"] = "http://localhost:5173,http://127.0.0.1:5173"

    if provider == "gemini":
        key = prompt("Gemini API key (hidden; leave blank to cancel): ").strip()
        if not key:
            raise ValueError("No Gemini key entered; nothing started.")
        if "\n" in key or "\r" in key:
            raise ValueError("Gemini API key must be on one line.")
        path = Path(temporary_dir) / "gemini-api-key.txt"
        # Secret file is private, new and deleted with the temporary directory.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(key + "\n")
        env["CP2_GEMINI_KEYS_FILE"] = str(path)
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
    elif provider == "claude":
        key = prompt("Anthropic API key (hidden; leave blank to cancel): ").strip()
        if not key:
            raise ValueError("No Claude key entered; nothing started.")
        if "\n" in key or "\r" in key:
            raise ValueError("Anthropic API key must be on one line.")
        env["ANTHROPIC_API_KEY"] = key
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
        env.pop("CP2_GEMINI_KEYS_FILE", None)
    else:
        env.pop("CP2_GEMINI_KEYS_FILE", None)
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
    return env


def main(argv=None, *, prompt=getpass.getpass, runner=subprocess.run):
    parser = argparse.ArgumentParser(description="Safely launch the isolated CP2 backup API.")
    parser.add_argument("--provider", choices=["placeholder", "gemini", "claude"], default="placeholder")
    parser.add_argument("--docs", type=Path, default=ROOT / "docs",
                        help="Local folder of demo-safe documents (default: repo docs/)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", type=Path,
                        help="Optional persistent demo SQLite DB; otherwise an isolated temporary DB")
    args = parser.parse_args(argv)

    if not (1 <= args.port <= 65535):
        parser.error("port must be 1–65535")
    docs = args.docs.resolve()
    if args.provider != "placeholder" and (not docs.is_dir() or not any(docs.rglob("*.md"))):
        parser.error("real AI mode requires a nonempty documents folder; pass --docs PATH")
    if args.db is not None:
        if not args.db.parent.is_dir():
            parser.error("database parent folder must exist")
        print("Using the explicitly selected persistent demo database.")
    else:
        print("Using a throwaway SQLite database; it will be deleted when the demo exits.")

    try:
        with tempfile.TemporaryDirectory(prefix="cp2-backup-demo-") as tmp:
            db = args.db if args.db is not None else Path(tmp) / "demo.sqlite3"
            env = make_child_env(args.provider, docs, db, tmp, prompt=prompt)
            cmd = [sys.executable, "-m", "uvicorn", "app.main:app",
                   "--host", "127.0.0.1", "--port", str(args.port)]
            print(f"CP2 backup API at http://127.0.0.1:{args.port}/docs (mode: {args.provider})")
            print("In another terminal: cd frontend && npm ci && npm run dev")
            print("Stop with Ctrl+C. Credentials will never be printed or committed.")
            return runner(cmd, cwd=BACKEND, env=env, check=False).returncode
    except (KeyboardInterrupt, EOFError):
        print("Stopped or no interactive terminal available; no key was saved.")
        return 130
    except ValueError as exc:
        # Messages here intentionally contain no secrets.
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
