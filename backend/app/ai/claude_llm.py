"""Claude (Anthropic API) LLM call with the same signature as ``llm.call_api``.

Used when the backend runs with ``CP2_AI=claude``: main.py passes ``call_api``
to B's ``RagGenerator(call=...)``, so retrieval, prompts and citation checks
are unchanged; only the model behind them differs.

Credentials come from the Anthropic SDK's usual sources (``ANTHROPIC_API_KEY``,
``ANTHROPIC_AUTH_TOKEN`` or an ``ant auth login`` profile). No key is stored in
the repository.
TODO(team): obtain an API key for the demo machine and set ANTHROPIC_API_KEY
before starting the backend (see README "Real AI drafts").

Settings (environment variables):
  CP2_CLAUDE_MODEL   model ID (default claude-opus-5-5)
  CP2_CLAUDE_EFFORT  low | medium | high | xhigh | max (default low: short drafts,
                     and each draft needs two calls inside CP2_AI_TIMEOUT)
"""
import logging
import os
import threading

import anthropic

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "low"
# Seconds per call. A draft makes two calls (query rewrite + answer), which must
# finish inside A's CP2_AI_TIMEOUT (default 30). No SDK retries for the same reason.
REQUEST_TIMEOUT = 12
MAX_TOKENS = 16000

_lock = threading.Lock()
_client = None


class LLMNotConfigured(NotImplementedError):
    """No Anthropic credentials. Subclass of NotImplementedError, so the
    pipeline reports it as ``llm_not_configured`` like the Gemini adapter."""


class ClaudeRefused(RuntimeError):
    """The model declined the request (stop_reason == "refusal")."""


def _get_client():
    global _client
    with _lock:
        if _client is None:
            _client = anthropic.Anthropic(timeout=REQUEST_TIMEOUT, max_retries=0)
        return _client


def _has_credentials(client) -> bool:
    return any(getattr(client, name, None) is not None for name in ("api_key", "auth_token", "credentials"))


def call_api(prompt: str, system: str | None = None) -> str:
    """Send one prompt to Claude and return the text of the reply.

    Raises:
        LLMNotConfigured: no Anthropic credentials are set.
        ClaudeRefused: the request was declined (after the server-side fallback).
        anthropic.APIError subclasses (auth, rate limit, timeout, network): passed
            through; pipeline.generate_answer turns them into a failed draft.
    """
    client = _get_client()
    if not _has_credentials(client):
        raise LLMNotConfigured("No Anthropic credentials; set ANTHROPIC_API_KEY")

    params = {
        "model": os.getenv("CP2_CLAUDE_MODEL") or DEFAULT_MODEL,
        "max_tokens": MAX_TOKENS,
        "output_config": {"effort": os.getenv("CP2_CLAUDE_EFFORT") or DEFAULT_EFFORT},
        "messages": [{"role": "user", "content": prompt}],
        # If a safety classifier declines, the API retries on a fallback model
        # inside the same call instead of returning no draft.
        "betas": ["server-side-fallback-2026-07-01"],
        "fallbacks": "default",
    }
    if system:
        params["system"] = system

    response = client.beta.messages.create(**params)
    if response.stop_reason == "refusal":
        category = getattr(response.stop_details, "category", None) if response.stop_details else None
        log.warning("Claude declined the request (category=%s, request_id=%s)",
                    category, getattr(response, "_request_id", None))
        raise ClaudeRefused(f"refusal:{category}")
    if response.stop_reason == "max_tokens":
        log.warning("Claude reply hit max_tokens; the draft may be cut off")
    return "".join(block.text for block in response.content if block.type == "text")
