#!/usr/bin/env python3
"""Check a running CP2 backup server without printing answers or credentials.

Read-only by default. --submit explicitly sends one new question to the
selected backend and evaluates the returned AI status + citation count.
Run on the same machine as the API, not on a public untrusted endpoint.
"""
import argparse
import json
import secrets
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def get_json(url, payload=None, *, opener=urlopen):
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=None if payload is None else json.dumps(payload).encode("utf-8"),
                      headers=headers, method="POST" if payload is not None else "GET")
    with opener(request, timeout=65) as response:
        return response.status, json.load(response)


def main(argv=None, *, opener=urlopen):
    parser = argparse.ArgumentParser(description="Read-only by default; --submit sends a real demo question.")
    parser.add_argument("--url", default="http://127.0.0.1:8000",
                        help="Loopback API URL; do not send demo questions to a public endpoint")
    parser.add_argument("--submit", metavar="QUESTION", help="Explicitly create a demo question (writes to DB)")
    parser.add_argument("--require-citations", action="store_true",
                        help="Treat zero document citations as a failed smoke check")
    args = parser.parse_args(argv)
    parsed = urlsplit(args.url)
    if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        parser.error("for safety this tool connects only to an HTTP loopback API")
    base = args.url.rstrip("/")

    try:
        _, health = get_json(base + "/api/health", opener=opener)
        if not isinstance(health, dict) or health.get("ok") is not True:
            print("FAIL: API health did not report ok=true")
            return 2
        mode = health.get("mode")
        print(f"API healthy. Selected mode: {mode!s} (selection does not prove provider access)")
        if args.submit is None:
            print("Read-only check complete. Use --submit 'your question' to test real generation.")
            return 0
        question = args.submit.strip()
        if not question or len(question) > 2000:
            parser.error("question must be 1–2000 characters")
        payload = {"question": question, "client_request_id": "backup-smoke-" + secrets.token_hex(12)}
        status, result = get_json(base + "/api/questions", payload, opener=opener)
        if not isinstance(result, dict):
            print("FAIL: invalid response shape")
            return 2
        ai = result.get("ai_status")
        citations = result.get("citations")
        valid_count = len([c for c in citations if isinstance(c, dict) and isinstance(c.get("source"), str)
                           and c["source"].strip()]) if isinstance(citations, list) else 0
        # Deliberately never print the raw question, answer, documents, key, or headers.
        print(f"POST HTTP {status}: question saved, ai_status={ai}, citations={valid_count}")
        if ai != "ok":
            error = result.get("ai_error")
            if isinstance(error, str) and len(error) <= 120 and error.replace("_", "").replace(":", "").isalnum():
                print(f"FAIL: AI draft unavailable; error category={error}")
            else:
                print("FAIL: AI draft unavailable (error category omitted)")
            return 3
        if args.require_citations and valid_count == 0:
            print("FAIL: no structured citations in AI draft")
            return 4
        print("AI draft generated. Manually verify the answer and each cited source in the Newcomer UI.")
        return 0
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        # No raw URL, headers or model exception text in logs (may contain secrets).
        print(f"FAIL: API connectivity or response issue ({type(exc).__name__}). Check backend logs locally.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
