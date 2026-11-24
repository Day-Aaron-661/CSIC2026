"""B 的主流程：（LLM 改寫問題）→ 檢索 → 組 prompt → 呼叫 LLM → 驗證引用。

任何失敗都回傳明確標示的狀態，不產生假答案、不捏造引用。
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import llm
from .citations import expand_groups, sub_citations
from .prompts import (REWRITE_SYSTEM_PROMPT, SYSTEM_PROMPT, build_prompt,
                      build_rewrite_prompt, fit_chunks, parse_rewrite)
from .retriever import Chunk, retrieve

log = logging.getLogger(__name__)

STATUS_ANSWERED = "answered"      # LLM 依文件產生了草稿
STATUS_NO_CONTEXT = "no_context"  # 找不到相關文件，未呼叫 LLM
STATUS_ERROR = "error"            # LLM 未實作、連線失敗或回傳空內容


@dataclass
class Citation:
    number: int     # 答案中使用的 [n]
    source: str
    snippet: str


@dataclass
class AnswerResult:
    status: str
    answer: str | None = None          # 僅 STATUS_ANSWERED 時有值
    citations: list[Citation] = field(default_factory=list)
    retrieved: list[Chunk] = field(default_factory=list)
    error: str | None = None


def validate_citations(answer: str, chunks: list[Chunk]) -> tuple[str, list[Citation]]:
    """保留有效的 [n] 並建立引用清單；移除指向不存在段落的 [n]。
    [1, 3]、[1-3] 先展開；程式碼裡的 argv[1] 等不算引用（規則見 citations.py）。"""
    valid = set(range(1, len(chunks) + 1))
    used = []

    def replace(number):
        if number not in valid:
            return None
        if number not in used:
            used.append(number)
        return number

    cleaned = sub_citations(expand_groups(answer), replace).strip()
    citations = [Citation(n, chunks[n - 1].source, chunks[n - 1].text[:200]) for n in sorted(used)]
    return cleaned, citations


def make_query_expander(call: Callable[..., str]):
    """回傳 expand(question, catalog)：請 LLM 把問題改寫成檢索用關鍵字。

    任何失敗（含 call_api 尚未實作）都回傳 None，檢索會退回只用原問題的 BM25。
    """
    def expand(question: str, catalog: str) -> str | None:
        try:
            return parse_rewrite(call(build_rewrite_prompt(question, catalog), system=REWRITE_SYSTEM_PROMPT))
        except NotImplementedError:
            return None
        except Exception:
            log.warning("Query rewrite failed; falling back to the original question", exc_info=True)
            return None
    return expand


def generate_answer(question: str, knowledge: list[dict] | None = None, *,
                    call: Callable[..., str] | None = None,
                    docs_dir: Path | None = None, top_k: int = 4,
                    rewrite_query: bool = True) -> AnswerResult:
    """
    Args:
        question: 新人的問題（已去除前後空白）。
        knowledge: Mentor 已核准的問答資料列（可省略），會一併納入檢索。
        call: LLM 呼叫函式，預設為 llm.call_api；測試時可注入假函式。
        docs_dir: 文件資料夾，預設見 retriever.docs_dir()。
        rewrite_query: 是否以 LLM 改寫問題做第二路檢索（B+）；False 時為純 BM25。
    """
    call = call or llm.call_api
    expand = make_query_expander(call) if rewrite_query else None
    chunks = fit_chunks(retrieve(question, knowledge, docs_dir, top_k, expand=expand))
    if not chunks:
        return AnswerResult(STATUS_NO_CONTEXT, error="no_context")

    try:
        raw = call(build_prompt(question, chunks), system=SYSTEM_PROMPT)
    except NotImplementedError:
        return AnswerResult(STATUS_ERROR, retrieved=chunks, error="llm_not_configured")
    except Exception as exc:  # 實際 API 的各種錯誤都視為失敗，不重試、不編答案
        log.exception("LLM call failed")
        return AnswerResult(STATUS_ERROR, retrieved=chunks, error=f"llm_error:{type(exc).__name__}")

    if not isinstance(raw, str) or not raw.strip():
        return AnswerResult(STATUS_ERROR, retrieved=chunks, error="empty_response")

    answer, citations = validate_citations(raw, chunks)
    return AnswerResult(STATUS_ANSWERED, answer, citations, chunks)
