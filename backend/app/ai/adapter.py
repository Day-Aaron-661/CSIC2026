"""A（API）與 B（AI 流程）之間的轉接層。

對應 A 在 backend/app/ai_hook.py 定義的介面：
    generator.generate(question) -> ai_hook.AnswerResult(answer, status, citations, error)
由 create_app(generator=RagGenerator(...)) 傳入。
- status "ok"：依文件產生的草稿；citations 為實際引用的來源，答案中的 [n] 對應 citations 第 n 筆。
- status "failed"：沒有草稿（找不到文件、LLM 未設定或失敗）；error 為短代碼，A 會改顯示固定說明文字。
ai_hook 只存在於 A 的新版後端，因此在 generate() 內才 import。
"""
import logging
from typing import Callable

from .citations import UNVERIFIED_NOTE, format_sources, sub_citations
from .pipeline import STATUS_ANSWERED, generate_answer

log = logging.getLogger(__name__)

# 回傳 Mentor 已核准問答資料列（/api/knowledge 格式）的函式
KnowledgeSource = Callable[[], list[dict]]


def renumber_citations(answer: str, numbers: list[int]) -> str:
    """把答案中的 [n]（context 段落編號）改成引用清單中的順序 1..k。程式碼裡的 [n] 不動。"""
    mapping = {old: new for new, old in enumerate(numbers, start=1)}
    return sub_citations(answer, mapping.get)


class RagGenerator:
    """B 的 AnswerGenerator 實作。generate() 不會拋出例外。"""

    def __init__(self, knowledge_source: KnowledgeSource | None = None, **options):
        """
        Args:
            knowledge_source: 取得已核准問答的函式（例如讀 A 的 repository），會一併納入檢索；可省略。
            options: 傳給 pipeline.generate_answer，例如 docs_dir、top_k、rewrite_query。
        """
        self.knowledge_source = knowledge_source
        self.options = options

    def _knowledge(self) -> list[dict] | None:
        if self.knowledge_source is None:
            return None
        try:
            return list(self.knowledge_source())
        except Exception:
            log.warning("Could not load approved answers; retrieving from documents only", exc_info=True)
            return None

    def generate(self, question: str):
        from ..ai_hook import AnswerResult, Citation, failed

        question = (question or "").strip()
        if not question:
            return failed("empty_question")
        try:
            result = generate_answer(question, self._knowledge(), **self.options)
        except Exception as exc:  # 檢索等非預期錯誤
            log.exception("AI pipeline failed")
            return failed(f"pipeline_error:{type(exc).__name__}")

        if result.status != STATUS_ANSWERED:
            return failed(result.error or result.status)

        citations = [Citation(source=c.source, snippet=c.snippet) for c in result.citations]
        answer = renumber_citations(result.answer, [c.number for c in result.citations])
        if citations:
            # 來源清單也附在答案末尾；已核准答案放回檢索前會由 citations.clean_for_reuse 拿掉
            answer += "\n\n" + format_sources([c.source for c in citations])
        else:
            answer = f"{answer}\n\n{UNVERIFIED_NOTE}"
        return AnswerResult(answer=answer, status="ok", citations=citations)
