"""B（backend/app/ai）的離線測試：不連網、不讀真正的 key 檔，LLM 與 HTTP 都用假的。"""
import io
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from app.ai import adapter, citations, llm, pipeline, prompts, retriever


# ---------------------------------------------------------------- fixtures
@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    def blocked(*args, **kwargs):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    keys = tmp_path / "keys.txt"
    keys.write_text("# fake\nKEY-A\nKEY-B\nKEY-C\n", encoding="utf-8")
    monkeypatch.setenv("CP2_GEMINI_KEYS_FILE", str(keys))
    monkeypatch.setattr(llm, "_current", 0)
    monkeypatch.setattr(llm, "_exhausted_until", 0.0)
    retriever._CHUNK_CACHE.clear()


def write(root: Path, rel: str, text: str):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / "docs"
    write(root, "setup.md", "# Setup\n\n## Start the backend\n\nRun `uvicorn app.main:app --reload` from backend/.\n\n"
                            "## Start the frontend\n\nRun `npm run dev` in frontend/.\n")
    write(root, "hr/leave.md", "# Leave policy\n\n## Refund of travel expenses\n\nSubmit receipts to finance within 30 days.\n")
    write(root, "zh.md", "# 部署流程\n\n部署前請先執行測試，然後由 Mentor 核准合併。\n")
    write(root, "code/useNewcomerQuestions.js", "export function useNewcomerQuestions() {\n  return pollEveryFiveSeconds();\n}\n")
    write(root, "node_modules/x/readme.md", "# Start the backend secret\n")
    write(root, "package-lock.json", "{\"start\": \"backend\"}")
    (root / "image.png").write_bytes(b"\x89PNG\x00\x01")
    (root / "bad.txt").write_bytes(b"\xff\xfe\xfa not utf8")
    return root


@pytest.fixture
def empty_dir(tmp_path):
    path = tmp_path / "empty"
    path.mkdir()
    return path


def fake_llm(answer="Run uvicorn [1]. Also see [7].", rewrite="start backend uvicorn", log=None):
    def call(prompt, system=None):
        if log is not None:
            log.append((system, prompt))
        return rewrite if system == prompts.REWRITE_SYSTEM_PROMPT else answer
    return call


def http_error(code, body=b'{"error": {"message": "quota"}}'):
    return urllib.error.HTTPError(llm.API_URL, code, "err", {}, io.BytesIO(body))


# ---------------------------------------------------------------- retriever
def test_tokenize_splits_identifiers_and_chinese_and_drops_stopwords():
    tokens = retriever.tokenize("How do I use useNewcomerQuestions 部署流程")
    assert {"usenewcomerquestions", "use", "newcomer", "questions", "部署", "署流", "流程"} <= set(tokens)
    assert "how" not in tokens and "do" not in tokens


def test_markdown_split_by_heading_ignores_hash_in_code_block():
    md = "# A\n\ntext a\n\n```bash\n# not a heading\necho hi\n```\n\n# B\n\n" + ("x" * 900)
    sections = retriever.split_markdown_sections(md)
    assert len(sections) == 2 and "# not a heading" in sections[0]
    assert all(len(c) <= 800 for c in retriever.split_markdown(md, 800))


def test_markdown_fence_must_close_with_same_marker():
    md = "# A\n\n````md\n```\n# still code\n```\n````\n\n# B\n\ntext"
    sections = retriever.split_markdown_sections(md)
    assert len(sections) == 2 and "# still code" in sections[0]
    md = "# A\n\n~~~\n```\n# still code\n~~~\n\n# B\n"
    assert len(retriever.split_markdown_sections(md)) == 2


def test_small_markdown_sections_are_merged():
    assert retriever.split_markdown("# A\n\none\n\n# B\n\ntwo\n", 800) == ["# A\n\none\n\n# B\n\ntwo"]


def test_loader_skips_dependencies_locks_binaries_and_bad_encoding(corpus):
    sources = {c.source for c in retriever.load_document_chunks(corpus)}
    assert sources == {"setup.md", "hr/leave.md", "zh.md", "code/useNewcomerQuestions.js"}


def test_loader_skips_secret_files(tmp_path):
    root = tmp_path / "docs"
    for name in ("credentials.json", "service-account-prod.json", "secrets.yaml", ".env",
                 ".env.local", "server.pem", "gemini_api_keys.txt", "my_secret.txt"):
        write(root, name, "TOKEN=abc123 start backend")
    write(root, ".env.example", "PORT=8000 start backend")
    write(root, "config.json", "{\"start\": \"backend\"}")
    sources = {c.source for c in retriever.load_document_chunks(root)}
    assert sources == {".env.example", "config.json"}


def test_loader_does_not_enter_skipped_directories(tmp_path, monkeypatch):
    root = tmp_path / "docs"
    write(root, "a.md", "# A\n\ntext")
    write(root, "node_modules/pkg/readme.md", "# pkg")
    visited = []
    real_walk = os.walk

    def tracking_walk(top, *args, **kwargs):
        for dirpath, dirnames, filenames in real_walk(top, *args, **kwargs):
            visited.append(Path(dirpath).name)
            yield dirpath, dirnames, filenames
    monkeypatch.setattr(retriever.os, "walk", tracking_walk)
    retriever.load_document_chunks(root)
    assert "node_modules" not in visited and "pkg" not in visited


def test_loader_reuses_chunks_until_a_file_changes(tmp_path, monkeypatch):
    root = tmp_path / "docs"
    doc = write(root, "a.md", "# A\n\nfirst version")
    reads = []
    real_read = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: reads.append(self.name) or real_read(self, *a, **k))
    retriever.load_document_chunks(root)
    retriever.load_document_chunks(root)
    assert reads == ["a.md"]
    doc.write_text("# A\n\nsecond version", encoding="utf-8")
    os.utime(doc, ns=(doc.stat().st_atime_ns, doc.stat().st_mtime_ns + 10**9))
    chunks = retriever.load_document_chunks(root)
    assert reads == ["a.md", "a.md"] and "second version" in chunks[0].text


def test_loader_skips_symlink_outside_root(tmp_path):
    root = tmp_path / "docs"
    write(root, "a.md", "# A")
    outside = write(tmp_path, "private/notes.md", "# private")
    try:
        (root / "link.md").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")
    assert {c.source for c in retriever.load_document_chunks(root)} == {"a.md"}


def test_missing_or_empty_folder_returns_nothing(tmp_path, empty_dir):
    assert retriever.load_document_chunks(tmp_path / "missing") == []
    assert retriever.retrieve("anything", directory=empty_dir) == []


def test_exact_terms_rank_first(corpus):
    assert retriever.retrieve("uvicorn", directory=corpus)[0].source == "setup.md"
    assert retriever.retrieve("useNewcomerQuestions", directory=corpus)[0].source == "code/useNewcomerQuestions.js"
    assert retriever.retrieve("部署前要做什麼", directory=corpus)[0].source == "zh.md"


def test_rewritten_query_finds_paraphrased_question(corpus):
    question = "how do I get my money back for a trip"
    found = retriever.retrieve(question, directory=corpus, expand=lambda q, c: "refund travel expenses receipts")
    assert found[0].source == "hr/leave.md"


def test_failing_query_expansion_falls_back_to_bm25(corpus):
    def broken(question, catalog):
        raise RuntimeError("rewrite down")
    plain = retriever.retrieve("uvicorn", directory=corpus)
    assert [c.source for c in retriever.retrieve("uvicorn", directory=corpus, expand=broken)] == \
           [c.source for c in plain]
    assert [c.source for c in retriever.retrieve("uvicorn", directory=corpus, expand=lambda q, c: None)] == \
           [c.source for c in plain]


def test_rrf_combines_rank_lists():
    assert [i for i, _ in retriever.reciprocal_rank_fusion([[1, 2, 3], [3, 1]])] == [1, 3, 2]


def test_catalog_lists_files_and_headings_but_not_code_comments(tmp_path):
    root = tmp_path / "docs"
    write(root, "guide.md", "# Guide\n\n## Install\n\n```bash\n# install deps\npip install x\n```\n")
    catalog = retriever.build_catalog(retriever.load_document_chunks(root))
    assert "guide.md" in catalog and "## Install" in catalog and "# install deps" not in catalog


def test_knowledge_uses_only_approved_answers_and_tolerates_missing_question():
    rows = [{"id": 1, "status": "approved", "question": "q1", "reviewed_answer": "a1"},
            {"id": 2, "status": "pending", "question": "q2", "reviewed_answer": None},
            {"id": 3, "status": "approved", "question": "q3", "reviewed_answer": "  "},
            {"id": 4, "status": "approved", "question": None, "reviewed_answer": "a4"}]
    assert [c.source for c in retriever.knowledge_chunks(rows)] == ["knowledge#1", "knowledge#4"]


def test_knowledge_drops_old_citation_markers_and_sources_list():
    answer = "Run uvicorn [1] and read `argv[1]` [2].\n\nSources:\n[1] README.md\n[2] docs/x.md"
    chunk = retriever.knowledge_chunks([{"id": 9, "status": "approved", "question": "q",
                                         "reviewed_answer": answer}])[0]
    assert chunk.text.endswith("Run uvicorn and read `argv[1]`.")
    assert "Sources" not in chunk.text and "README.md" not in chunk.text


# ---------------------------------------------------------------- citations
def found_citations(text):
    found = []
    citations.sub_citations(text, lambda n: found.append(n) or n)
    return found


def test_code_indices_are_not_treated_as_citations():
    text = "Run `python main.py` and read sys.argv[1] [2], items[3], m[0][2] and f()[1]."
    assert found_citations(text) == [2]


def test_adjacent_citations_are_all_found():
    assert found_citations("Start here [1][3]. Then [2].") == [1, 3, 2]


def test_citations_inside_code_blocks_are_ignored():
    assert found_citations("See [1].\n\n```python\nx = [1]\nprint(a [2])\n```") == [1]


def test_grouped_citations_are_expanded():
    assert citations.expand_groups("a [1, 3] b [1-3] c [2，4]") == "a [1][3] b [1][2][3] c [2][4]"
    assert citations.expand_groups("`[1, 3]` stays") == "`[1, 3]` stays"


# ---------------------------------------------------------------- prompts
def test_parse_rewrite_takes_first_line():
    assert prompts.parse_rewrite("\n  refund travel \nsecond") == "refund travel"
    assert prompts.parse_rewrite("") is None and prompts.parse_rewrite(None) is None
    assert len(prompts.parse_rewrite("x" * 2000)) == prompts.MAX_REWRITE_CHARS


def test_context_never_exceeds_limit_including_headers():
    chunks = [retriever.Chunk("a.md", "x" * 2990), retriever.Chunk("b.md", "y" * 2990)]
    kept = prompts.fit_chunks(chunks, 6000)
    assert len(prompts.format_context(kept)) <= 6000 and [c.source for c in kept] == ["a.md"]


def test_overlong_first_passage_is_truncated():
    kept = prompts.fit_chunks([retriever.Chunk("knowledge#1", "z" * 9000)], 6000)
    assert len(kept) == 1 and len(prompts.format_context(kept)) <= 6000


# ---------------------------------------------------------------- pipeline
def test_pipeline_answers_with_valid_citations_only(corpus):
    calls = []
    result = pipeline.generate_answer("How do I start the backend?", docs_dir=corpus, call=fake_llm(log=calls))
    assert result.status == "answered" and result.answer == "Run uvicorn [1]. Also see."
    assert [c.number for c in result.citations] == [1]
    assert calls[0][0] == prompts.REWRITE_SYSTEM_PROMPT and calls[1][0] == prompts.SYSTEM_PROMPT


def test_pipeline_keeps_code_indices_in_the_answer(corpus):
    answer = "Read `sys.argv[1]` and arr[5] [1]."
    result = pipeline.generate_answer("uvicorn", docs_dir=corpus, call=fake_llm(answer=answer))
    assert result.answer == answer and [c.number for c in result.citations] == [1]


def test_pipeline_understands_grouped_citations(corpus):
    result = pipeline.generate_answer("uvicorn refund", docs_dir=corpus, rewrite_query=False,
                                      call=fake_llm(answer="Both steps [1, 2]."))
    assert result.answer == "Both steps [1][2]." and [c.number for c in result.citations] == [1, 2]


def test_pipeline_reports_no_context(empty_dir):
    result = pipeline.generate_answer("q", docs_dir=empty_dir, call=fake_llm())
    assert (result.status, result.error) == ("no_context", "no_context")


def test_pipeline_reports_llm_errors(corpus):
    def boom(prompt, system=None):
        raise ValueError("x")

    def not_configured(prompt, system=None):
        raise NotImplementedError
    assert pipeline.generate_answer("uvicorn", docs_dir=corpus, call=boom).error == "llm_error:ValueError"
    assert pipeline.generate_answer("uvicorn", docs_dir=corpus, call=lambda p, system=None: "  ").error == "empty_response"
    assert pipeline.generate_answer("uvicorn", docs_dir=corpus, call=not_configured).error == "llm_not_configured"


# ---------------------------------------------------------------- llm.py（假的 HTTP）
def test_no_keys_means_not_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("CP2_GEMINI_KEYS_FILE", str(tmp_path / "missing.txt"))
    with pytest.raises(llm.LLMNotConfigured):
        llm.call_api("hi")


def test_request_body_and_text_from_steps(monkeypatch):
    seen = {}

    def fake_post(key, body):
        seen.update(key=key, body=body)
        return {"steps": [{"type": "thought", "signature": "s"},
                          {"type": "model_output", "content": [{"type": "text", "text": "Hello "},
                                                               {"type": "text", "text": "world"}]}]}
    monkeypatch.setattr(llm, "_post", fake_post)
    assert llm.call_api("p", system="sys") == "Hello world"
    assert seen == {"key": "KEY-A", "body": {"model": llm.DEFAULT_MODEL, "input": "p", "store": False,
                                             "system_instruction": "sys"}}


def test_empty_output_text_falls_back_to_steps():
    data = {"output_text": "", "steps": [{"type": "model_output", "content": [{"type": "text", "text": "ok"}]}]}
    assert llm._extract_text(data) == "ok"


def test_response_without_text_is_logged(caplog):
    with caplog.at_level(logging.WARNING, logger=llm.__name__):
        assert llm._extract_text({"candidates": []}) == ""
    assert "candidates" in caplog.text


def test_quota_error_switches_key_and_stays_on_it(monkeypatch):
    used = []

    def fake_post(key, body):
        used.append(key)
        if key == "KEY-A":
            raise http_error(429)
        return {"output_text": f"from {key}"}
    monkeypatch.setattr(llm, "_post", fake_post)
    assert llm.call_api("p") == "from KEY-B"
    assert llm.call_api("p") == "from KEY-B"
    assert used == ["KEY-A", "KEY-B", "KEY-B"]


def test_rotated_http_errors_are_closed(monkeypatch):
    errors = []

    def fake_post(key, body):
        if key != "KEY-C":
            errors.append(http_error(429 if key == "KEY-A" else 401))
            raise errors[-1]
        return {"output_text": "ok"}
    monkeypatch.setattr(llm, "_post", fake_post)
    assert llm.call_api("p") == "ok"
    assert len(errors) == 2 and all(e.fp.closed for e in errors)


def test_server_error_is_not_rotated(monkeypatch):
    used = []

    def fake_post(key, body):
        used.append(key)
        raise http_error(503)
    monkeypatch.setattr(llm, "_post", fake_post)
    with pytest.raises(urllib.error.HTTPError):
        llm.call_api("p")
    assert used == ["KEY-A"]


def test_all_keys_failing_reports_each_status_and_reason(monkeypatch, caplog):
    monkeypatch.setattr(llm, "_post", lambda key, body: (_ for _ in ()).throw(
        http_error(403, b'{"error": {"message": "model not allowed"}}')))
    with caplog.at_level(logging.WARNING, logger=llm.__name__), pytest.raises(llm.AllKeysFailed) as info:
        llm.call_api("p")
    assert "403, 403, 403" in str(info.value)
    assert "model not allowed" in caplog.text and "model name" in caplog.text
    assert "KEY-" not in caplog.text


def test_quota_exhaustion_skips_requests_during_cooldown(monkeypatch):
    calls = []

    def fake_post(key, body):
        calls.append(key)
        raise http_error(429)
    monkeypatch.setattr(llm, "_post", fake_post)
    with pytest.raises(llm.AllKeysFailed):
        llm.call_api("rewrite")
    with pytest.raises(llm.AllKeysFailed):
        llm.call_api("answer")
    assert len(calls) == 3


def test_post_sends_key_in_header(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"output_text": "x"}).encode()

    def fake_urlopen(request, timeout):
        captured.update(url=request.full_url, headers=dict(request.header_items()), timeout=timeout)
        return Response()
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert llm.call_api("p") == "x"
    assert captured["url"] == llm.API_URL and captured["timeout"] == llm.REQUEST_TIMEOUT
    assert captured["headers"]["X-goog-api-key"] == "KEY-A"


# ---------------------------------------------------------------- adapter（需要 A 的 ai_hook）
def test_renumber_citations_skips_code():
    assert adapter.renumber_citations("a [3] b [1][3] `x[3]` c [9]", [1, 3]) == "a [2] b [1][2] `x[3]` c"


@pytest.fixture
def ai_hook():
    return pytest.importorskip("app.ai_hook")


def test_generator_returns_ok_with_sources(ai_hook, corpus):
    generator = adapter.RagGenerator(docs_dir=corpus, call=fake_llm(answer="Use uvicorn [2] and receipts [1].",
                                                                    rewrite="uvicorn refund travel receipts"))
    result = generator.generate("How do I start the backend, and get money back for a trip?")
    assert isinstance(result, ai_hook.AnswerResult) and result.status == "ok" and len(result.citations) == 2
    assert result.answer.endswith(f"Sources:\n[1] {result.citations[0].source}\n[2] {result.citations[1].source}")


def test_generator_failures(ai_hook, corpus, empty_dir):
    assert adapter.RagGenerator(docs_dir=empty_dir, call=fake_llm()).generate("q").error == "no_context"
    assert adapter.RagGenerator(docs_dir=corpus, call=fake_llm()).generate("   ").error == "empty_question"


def test_generator_marks_uncited_answers(ai_hook, corpus):
    result = adapter.RagGenerator(docs_dir=corpus, call=fake_llm(answer="No idea.")).generate("uvicorn")
    assert result.status == "ok" and result.citations == [] and citations.UNVERIFIED_NOTE in result.answer


def test_generator_ignores_broken_knowledge_source(ai_hook, corpus):
    def broken():
        raise RuntimeError("db down")
    assert adapter.RagGenerator(knowledge_source=broken, docs_dir=corpus,
                                call=fake_llm()).generate("uvicorn").status == "ok"
