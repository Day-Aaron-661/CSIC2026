#!/usr/bin/env python3
"""Offline readiness check for the isolated CP2 backup prototype.

Checks only local setup. Does NOT contact Gemini/Claude or prove a live call.
Does NOT log credentials or inspect the SQLite database.
"""
import argparse
import importlib.util
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
TEXT_EXTENSIONS = {".md", ".txt", ".rst", ".adoc", ".py", ".js", ".jsx", ".json", ".yaml", ".yml"}


def has_documents(root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for p in root.rglob("*")
               if p.is_file() and not p.is_symlink() and p.suffix.lower() in TEXT_EXTENSIONS
               and p.stat().st_size > 0 and not p.name.startswith(".")
               and not any(x in p.parts for x in (".git", "node_modules", ".venv")))


def has_gemini_key(path: Path) -> bool:
    try:
        return any(line.strip() and not line.lstrip().startswith("#")
                   for line in path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Check CP2 backup environment without calling an LLM.")
    parser.add_argument("--mode", choices=["placeholder", "gemini", "claude"],
                        default=(os.getenv("CP2_AI") or "placeholder").lower())
    parser.add_argument("--docs", type=Path, help="Docs directory (same as CP2_AI_DOCS_DIR used to launch backend)")
    args = parser.parse_args()

    mode = args.mode
    if args.docs:
        docs = args.docs.resolve()
    else:
        configured = os.getenv("CP2_AI_DOCS_DIR")
        docs = (BACKEND / configured).resolve() if configured else BACKEND / "app/ai/documents"
    print(f"CP2 backup preflight — mode: {mode} (OFFLINE ONLY)")
    print("Mode selected; no API request is made by this command.")

    if importlib.util.find_spec("fastapi") is None:
        print("MISSING: FastAPI. Install: python3 -m pip install -r backend/requirements.txt")
        return 2

    if mode == "placeholder":
        print("READY: placeholder prototype needs no API key (not a real AI answer).")
        return 0

    failures = []
    count = has_documents(docs)
    if count:
        print(f"OK: {count} nonempty candidate document files in {docs}")
    else:
        failures.append("No documents found. Set CP2_AI_DOCS_DIR to a folder with approved project documents.")

    if mode == "gemini":
        path = Path(os.getenv("CP2_GEMINI_KEYS_FILE") or BACKEND / "app/ai/gemini_api_keys.txt")
        if has_gemini_key(path):
            print("OK: Gemini key file contains at least one non-comment line (key not displayed).")
        else:
            failures.append("Gemini keys missing. Create the ignored backend/app/ai/gemini_api_keys.txt on the demo machine.")
    elif mode == "claude":
        if importlib.util.find_spec("anthropic") is None:
            failures.append("Anthropic SDK missing. Install backend/requirements.txt.")
        if os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"):
            print("OK: an Anthropic credential environment variable is set (value not displayed).")
        else:
            failures.append("No explicit ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN set on this machine.")

    if failures:
        for message in failures:
            print("NEEDS SETUP:", message)
        return 2
    print("LOCAL SETUP CHECKS PASSED — still run a real-key question and verify ai_status=ok + citations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
