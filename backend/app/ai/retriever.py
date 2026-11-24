"""文件檢索（B）。

從專案文件資料夾讀取文件與程式碼等純文字檔，切成段落後以 BM25 排序。
不依賴額外套件；中文以字元 bigram 切詞，英文/程式名稱以單字切詞，
程式識別字另外拆成 camelCase / snake_case 的組成單字。
檢索方式（B+）：原問題的 BM25 與 LLM 改寫後查詢的 BM25 各取候選，以 RRF 合併；
改寫不可用時等同純 BM25。
文件資料夾為空或不存在時回傳空清單，不會報錯。
"""
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# 專案文件放置位置；可用環境變數 CP2_AI_DOCS_DIR 覆寫。
DEFAULT_DOCS_DIR = Path(__file__).resolve().parent / "documents"
DOC_SUFFIXES = {
    # 文件
    ".md", ".markdown", ".txt", ".rst", ".adoc",
    # 網頁
    ".html", ".htm", ".css", ".scss", ".sass", ".less", ".vue", ".svelte",
    # 程式碼
    ".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
    ".java", ".kt", ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".go", ".rs",
    ".rb", ".php", ".swift", ".m", ".r", ".lua", ".sql",
    ".sh", ".bash", ".ps1", ".bat",
    # 設定檔
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".xml", ".env.example",
}
DOC_FILENAMES = {"Dockerfile", "Makefile", "CMakeLists.txt", "Procfile"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
             ".pytest_cache", ".mypy_cache", ".next", "coverage"}
SKIP_FILENAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
                  "gemini_api_keys.txt", ".env"}  # 金鑰檔絕不能被讀進語料
MAX_FILE_BYTES = 1_000_000
MAX_CHUNK_CHARS = 800

_IDENT = re.compile(r"[A-Za-z0-9_]+")
_IDENT_PART = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
_CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]+")
# English function words are ignored for retrieval ("the", "how", ... would otherwise score unrelated passages)
_STOPWORDS = frozenset((
    "a an the and or but if of to in on at by for with from as is are was were be been being "
    "do does did doing have has had i you he she it we they me my your our their this that these "
    "those what which who whom when where why how can could should would will shall may might must "
    "not no so than too very there here about into over under again then once all any both each few "
    "more most other some such only own same just also up down out off"
).split())


@dataclass(frozen=True)
class Chunk:
    source: str   # 文件相對路徑，或 "knowledge#<id>"
    text: str
    score: float = 0.0


def docs_dir() -> Path:
    return Path(os.getenv("CP2_AI_DOCS_DIR") or DEFAULT_DOCS_DIR)


def tokenize(text: str) -> list[str]:
    tokens = []
    for ident in _IDENT.findall(text):
        if ident.lower() not in _STOPWORDS:
            tokens.append(ident.lower())
        parts = _IDENT_PART.findall(ident)  # useNewcomerQuestions -> use, newcomer, questions
        if len(parts) > 1:
            tokens.extend(p.lower() for p in parts if p.lower() not in _STOPWORDS)
    for run in _CJK.findall(text):
        tokens.extend(run if len(run) == 1 else (run[i:i + 2] for i in range(len(run) - 1)))
    return tokens


def split_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """依空行切段，再合併成不超過 max_chars 的區塊；超長段落硬切。"""
    chunks, current = [], ""
    for para in (p.strip() for p in re.split(r"\n\s*\n", text)):
        if not para:
            continue
        while len(para) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(para[:max_chars])
            para = para[max_chars:]
        if current and len(current) + len(para) + 2 > max_chars:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks


MARKDOWN_SUFFIXES = (".md", ".markdown")
_MD_HEADING = re.compile(r"#{1,6}\s+\S")
_MD_FENCE = re.compile(r"(```|~~~)")


def split_markdown_sections(text: str) -> list[str]:
    """依 Markdown 標題（# ~ ######）切成小節；第一個標題之前的內容自成一節。
    程式碼區塊（``` / ~~~）內以 # 開頭的行不視為標題。"""
    sections, current, in_fence = [], [], False
    for line in text.splitlines():
        stripped = line.lstrip()
        if _MD_FENCE.match(stripped):
            in_fence = not in_fence
        if not in_fence and _MD_HEADING.match(stripped) and any(l.strip() for l in current):
            sections.append("\n".join(current).strip())
            current = []
        current.append(line)
    if any(l.strip() for l in current):
        sections.append("\n".join(current).strip())
    return [s for s in sections if s]


def split_markdown(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Markdown 依標題切塊（參考 Week 9 Lab 的 chunk_by_heading，改以字元計算以支援中文）：
    相鄰小節依序合併，直到再加入下一節會超過 max_chars；單一小節超過 max_chars 時改用 split_text 切開。"""
    pieces = []
    for section in split_markdown_sections(text):
        pieces.extend([section] if len(section) <= max_chars else split_text(section, max_chars))
    chunks, current = [], ""
    for piece in pieces:
        if current and len(current) + len(piece) + 2 > max_chars:
            chunks.append(current)
            current = piece
        else:
            current = f"{current}\n\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks


def split_document(source: str, text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Markdown 依標題切塊，其他檔案（程式碼、設定檔等）依空行切段。"""
    if source.lower().endswith(MARKDOWN_SUFFIXES):
        return split_markdown(text, max_chars)
    return split_text(text, max_chars)


def is_text_document(path: Path, root: Path) -> bool:
    if not path.is_file() or path.name in SKIP_FILENAMES:
        return False
    if any(part in SKIP_DIRS for part in path.relative_to(root).parts[:-1]):
        return False
    name = path.name.lower()
    if path.name not in DOC_FILENAMES and not any(name.endswith(s) for s in DOC_SUFFIXES):
        return False
    try:
        return path.stat().st_size <= MAX_FILE_BYTES
    except OSError:
        return False


def load_document_chunks(directory: Path | None = None) -> list[Chunk]:
    root = Path(directory) if directory else docs_dir()
    if not root.is_dir():
        return []
    chunks = []
    for path in sorted(root.rglob("*")):
        if not is_text_document(path, root):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        source = path.relative_to(root).as_posix()
        chunks.extend(Chunk(source, piece) for piece in split_document(source, text))
    return chunks


def knowledge_chunks(knowledge: list[dict] | None) -> list[Chunk]:
    """把 Mentor 已核准的問答（/api/knowledge 的資料列）轉成可檢索的區塊。"""
    chunks = []
    for row in knowledge or []:
        answer = (row.get("reviewed_answer") or "").strip()
        if row.get("status") != "approved" or not answer:
            continue
        text = f"Q: {row.get('question', '').strip()}\nA (mentor verified): {answer}"
        chunks.append(Chunk(f"knowledge#{row.get('id')}", text))
    return chunks


class BM25Index:
    """BM25 關鍵字索引（k1=1.5, b=0.75）。建一次，可用不同查詢重複搜尋。"""

    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks, self.k1, self.b = chunks, k1, b
        self.tf = [Counter(tokenize(c.text)) for c in chunks]
        self.length = [sum(t.values()) for t in self.tf]
        self.avg = (sum(self.length) / len(self.length)) if self.length else 1.0
        df = Counter(term for counts in self.tf for term in counts)
        n = len(chunks)
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def search(self, query: str, limit: int) -> list[tuple[int, float]]:
        """回傳 [(區塊索引, 分數)]，只含分數 > 0 者，由高到低。"""
        terms = set(tokenize(query))
        scored = []
        for i, counts in enumerate(self.tf):
            score = 0.0
            for term in terms:
                tf = counts.get(term, 0)
                if tf:
                    norm = 1 - self.b + self.b * self.length[i] / (self.avg or 1.0)
                    score += self.idf[term] * tf * (self.k1 + 1) / (tf + self.k1 * norm)
            if score > 0:
                scored.append((i, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]


def reciprocal_rank_fusion(rank_lists: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    """RRF：每個清單中排名第 r 的項目得 1/(k+r) 分，加總後由高到低排序。"""
    scores = Counter()
    for ids in rank_lists:
        for r, idx in enumerate(ids, start=1):
            scores[idx] += 1.0 / (k + r)
    return scores.most_common()


def build_catalog(chunks: list[Chunk], max_chars: int = 3000) -> str:
    """語料目錄：檔名與 Markdown 標題，讓改寫問題的 LLM 知道專案實際使用的用詞。"""
    lines, seen = [], set()
    for chunk in chunks:
        if chunk.source not in seen:
            seen.add(chunk.source)
            lines.append(chunk.source)
        if chunk.source.lower().endswith(MARKDOWN_SUFFIXES):
            lines.extend(f"  {line.strip()}" for line in chunk.text.splitlines()
                         if re.match(r"#{1,6} \S", line.strip()))
    catalog, used = [], 0
    for line in lines:
        if used + len(line) + 1 > max_chars:
            break
        catalog.append(line)
        used += len(line) + 1
    return "\n".join(catalog)


# expand(question, catalog) -> 改寫後的查詢字串；失敗時回傳 None
QueryExpander = Callable[[str, str], "str | None"]


def retrieve(question: str, knowledge: list[dict] | None = None,
             directory: Path | None = None, top_k: int = 4,
             expand: QueryExpander | None = None, candidates: int = 10) -> list[Chunk]:
    """B+ 檢索：原問題 BM25 ＋ LLM 改寫後的查詢 BM25，以 RRF 合併。

    expand 為 None 或回傳空值時，只使用原問題的 BM25（等同純 BM25）。
    回傳 Chunk 的 score 為合併後的 RRF 分數。
    """
    chunks = load_document_chunks(directory) + knowledge_chunks(knowledge)
    if not chunks:
        return []
    index = BM25Index(chunks)
    rank_lists = [[i for i, _ in index.search(question, candidates)]]

    if expand is not None:
        expanded = expand(question, build_catalog(chunks))
        if expanded and expanded.strip():
            rank_lists.append([i for i, _ in index.search(expanded, candidates)])

    rank_lists = [ids for ids in rank_lists if ids]
    if not rank_lists:
        return []
    fused = reciprocal_rank_fusion(rank_lists)
    return [Chunk(chunks[i].source, chunks[i].text, round(score, 6)) for i, score in fused[:top_k]]
