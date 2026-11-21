"""Boundary between the API (owner A) and the AI implementation (owner B).

B implements an object with ``generate(question) -> AnswerResult`` under
``backend/app/ai/`` and passes it to ``create_app(generator=...)``. The API
only ever stores what is returned here into ``ai_*`` fields and citations;
an AI result can never change the review ``status``.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Literal, Protocol

log = logging.getLogger(__name__)

PLACEHOLDER_ANSWER = ("[DEMO PLACEHOLDER — NOT AI GENERATED] This question has been "
                      "submitted for mentor review. AI retrieval and citations are not implemented yet.")
FAILED_ANSWER = ("[AI DRAFT UNAVAILABLE] An AI draft could not be generated for this question. "
                 "It is still waiting for mentor review.")

AiStatus = Literal["placeholder", "ok", "failed"]


@dataclass
class Citation:
    source: str
    snippet: str | None = None
    locator: str | None = None


@dataclass
class AnswerResult:
    answer: str
    status: AiStatus
    citations: list[Citation] = field(default_factory=list)
    error: str | None = None


class AnswerGenerator(Protocol):
    def generate(self, question: str) -> AnswerResult: ...


class PlaceholderGenerator:
    """Default until B's implementation is merged. Never claims to be AI output."""

    def generate(self, question):
        return AnswerResult(answer=PLACEHOLDER_ANSWER, status="placeholder")


def failed(error):
    return AnswerResult(answer=FAILED_ANSWER, status="failed", error=error)


# A worker that outlives its timeout cannot be killed in Python; it keeps
# running in this shared pool while the API answers with a failed draft.
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ai-generate")


def safe_generate(generator, question, timeout_seconds):
    """Call the generator and convert every failure into a ``failed`` result.

    The stored ``error`` is a short category, not the raw exception text, so
    internal details (paths, keys, prompts) are not exposed through the API.
    """
    try:
        result = _pool.submit(generator.generate, question).result(timeout=timeout_seconds)
    except FutureTimeout:
        log.warning("AI generation timed out after %ss", timeout_seconds)
        return failed("timeout")
    except Exception as exc:  # noqa: BLE001 - any generator bug must not lose the question
        log.exception("AI generation raised")
        return failed(f"exception:{type(exc).__name__}")

    if not isinstance(result, AnswerResult) or result.status not in ("placeholder", "ok", "failed"):
        log.error("AI generator returned an invalid result: %r", result)
        return failed("invalid_result")
    if result.status == "failed":
        # Never show a failed generation's text as if it were a draft answer.
        return failed((result.error or "generator_failed")[:200])
    if not isinstance(result.answer, str) or not result.answer.strip():
        return failed("empty_answer")
    citations = [c for c in result.citations
                 if isinstance(c, Citation) and isinstance(c.source, str) and c.source.strip()]
    return AnswerResult(answer=result.answer.strip(), status=result.status, citations=citations)
