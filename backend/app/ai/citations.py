"""引用標記 [n] 的共用規則（pipeline、adapter、retriever 共用同一套）。

- 只認「前面不是名稱或右括號」的 [n]：argv[1]、items[3]、m[0][2]、f()[1] 都不是引用。
- 反引號與程式碼區塊（``` / ~~~）裡的內容一律不處理。
- [1, 3]、[1-3] 先展開成 [1][3]、[1][2][3] 再處理。
"""
import re

UNVERIFIED_NOTE = "(Unverified: this draft cites no project documents.)"

_NOT_AFTER_NAME = r"(?<![\w\]\)])"
# 一整串連續的 [n]（例如 [1][3]）一起判斷：開頭不能接在名稱或括號後面
_CHAIN = re.compile(r"( ?)" + _NOT_AFTER_NAME + r"((?:\[\d+\])+)")
_NUMBER = re.compile(r"\[(\d+)\]")
_GROUP = re.compile(_NOT_AFTER_NAME + r"\[(\d+(?:\s*[,，\-–]\s*\d+)+)\]")
_CODE = re.compile(r"(```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)|`[^`\n]*`)")
_SOURCES_BLOCK = re.compile(r"\n\s*Sources:[ \t]*\n(?:[ \t]*\[\d+\][^\n]*(?:\n|$))+\s*$")
MAX_RANGE = 20


def _outside_code(text: str, fn) -> str:
    """只對程式碼以外的部分套用 fn。"""
    parts = _CODE.split(text)  # 奇數索引是程式碼
    return "".join(part if i % 2 else fn(part) for i, part in enumerate(parts))


def _expand_group(match) -> str:
    numbers = []
    for piece in re.split(r"\s*[,，]\s*", match.group(1)):
        bounds = re.split(r"\s*[\-–]\s*", piece)
        if len(bounds) == 1:
            numbers.append(int(bounds[0]))
        elif len(bounds) == 2 and 0 <= int(bounds[1]) - int(bounds[0]) < MAX_RANGE:
            numbers.extend(range(int(bounds[0]), int(bounds[1]) + 1))
        else:
            return match.group(0)
    return "".join(f"[{n}]" for n in numbers)


def expand_groups(text: str) -> str:
    """[1, 3] -> [1][3]；[1-3] -> [1][2][3]。"""
    return _outside_code(text, lambda s: _GROUP.sub(_expand_group, s))


def sub_citations(text: str, repl) -> str:
    """對程式碼以外的每個引用 [n] 呼叫 repl(n)：回傳新的編號（int）表示保留／改號，回傳 None 表示刪除。
    一串引用全部被刪除時，前面的空白也一起刪除。"""
    def replace_chain(match):
        kept = []
        for number in _NUMBER.findall(match.group(2)):
            new = repl(int(number))
            if new is not None:
                kept.append(f"[{new}]")
        return match.group(1) + "".join(kept) if kept else ""

    return _outside_code(text, lambda s: _CHAIN.sub(replace_chain, s))


def format_sources(sources: list[str]) -> str:
    return "Sources:\n" + "\n".join(f"[{n}] {source}" for n, source in enumerate(sources, start=1))


def clean_for_reuse(answer: str) -> str:
    """已核准答案放進檢索前：拿掉結尾的 Sources 清單、Unverified 說明和 [n] 標記。"""
    text = _SOURCES_BLOCK.sub("", answer or "").replace(UNVERIFIED_NOTE, "")
    return sub_citations(expand_groups(text), lambda n: None).strip()
