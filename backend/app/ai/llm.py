"""LLM 呼叫介面（B）：Google Gemini（Interactions API）。

- 只用標準函式庫（urllib），不新增依賴。
- API key 從文字檔讀取，一行一個，# 開頭為註解；預設檔案為本資料夾的 gemini_api_keys.txt，
  可用環境變數 CP2_GEMINI_KEYS_FILE 指定其他路徑。檔案每次呼叫時重新讀取，改 key 不必重啟。
- 遇到用量超額（HTTP 429）或 key 無效（401/403）時自動換下一個 key；全部失敗才拋出例外，
  例外訊息與 log 會列出每個 key 的 HTTP 狀態和 Gemini 的錯誤說明（不含 key）。
- 所有 key 都超額時，之後 QUOTA_COOLDOWN 秒內直接失敗，不再送出請求。
- 目前使用第幾個 key 的指標只存在記憶體（重啟後從第一個開始），不寫入檔案。
"""
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
API_REVISION = "2026-05-20"
DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_KEYS_FILE = Path(__file__).resolve().parent / "gemini_api_keys.txt"
REQUEST_TIMEOUT = 12  # 秒；每題兩次呼叫，需在 A 的 CP2_AI_TIMEOUT（預設 30 秒）內完成
ROTATE_STATUSES = {429, 401, 403}  # 超額、key 無效/被停用 → 換下一個 key
QUOTA_COOLDOWN = 60  # 秒；所有 key 都回 429 後，這段時間內不再送出請求

_lock = threading.Lock()
_current = 0  # 目前使用的 key 索引
_exhausted_until = 0.0  # time.monotonic()；在此之前所有 key 視為超額


class LLMNotConfigured(NotImplementedError):
    """沒有可用的 API key。"""


class AllKeysFailed(RuntimeError):
    """所有 API key 都超額或無效。"""


def keys_file() -> Path:
    return Path(os.getenv("CP2_GEMINI_KEYS_FILE") or DEFAULT_KEYS_FILE)


def load_keys(path: Path | None = None) -> list[str]:
    try:
        lines = (path or keys_file()).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def _build_body(prompt: str, system: str | None) -> dict:
    body = {"model": os.getenv("CP2_GEMINI_MODEL") or DEFAULT_MODEL, "input": prompt, "store": False}
    if system:
        body["system_instruction"] = system
    level = os.getenv("CP2_GEMINI_THINKING_LEVEL")  # 不設定則用模型預設
    if level:
        body["generation_config"] = {"thinking_level": level}
    return body


def _extract_text(data) -> str:
    """取出模型的最終文字（略過 thought 步驟）。output_text 沒有內容時改讀 steps。"""
    if not isinstance(data, dict):
        log.warning("Gemini response is not a JSON object: %s", type(data).__name__)
        return ""
    output = data.get("output_text")
    if isinstance(output, str) and output.strip():
        return output
    texts = []
    for step in data.get("steps") or []:
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        for item in step.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                texts.append(item["text"])
    text = "".join(texts)
    if not text.strip():
        log.warning("Gemini response had no text; top-level keys: %s", sorted(data))
    return text


def _error_detail(exc: urllib.error.HTTPError) -> str:
    """讀出 Gemini 的錯誤說明並關閉連線。"""
    try:
        body = exc.read().decode("utf-8", "replace")
    except Exception:
        body = ""
    finally:
        exc.close()
    try:
        message = json.loads(body).get("error", {}).get("message")
    except Exception:
        message = None
    return (message or body).strip()[:200]


def _post(key: str, body: dict) -> dict:
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key, "Api-Revision": API_REVISION},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def call_api(prompt: str, system: str | None = None) -> str:
    """送出一次 LLM 請求並回傳模型的文字回答。

    Args:
        prompt: 使用者訊息（已組好的問題與檢索到的文件內容）。
        system: 系統指示（角色與回答規則），可省略。

    Returns:
        模型產生的文字回答。

    Raises:
        LLMNotConfigured（NotImplementedError 子類別）: 沒有設定任何 API key。
        AllKeysFailed: 每個 key 都超額或無效（訊息列出各 key 的 HTTP 狀態）。
        其他例外（urllib.error.HTTPError、URLError、逾時等）: 直接拋出，
            由 pipeline.generate_answer 統一處理，不回傳假答案。
    """
    global _current, _exhausted_until
    keys = load_keys()
    if not keys:
        raise LLMNotConfigured(f"No Gemini API key in {keys_file()}")
    if time.monotonic() < _exhausted_until:
        raise AllKeysFailed("All Gemini API keys are over quota (cooling down)")
    body = _build_body(prompt, system)

    with _lock:
        start = _current % len(keys)
    statuses = []
    for offset in range(len(keys)):
        index = (start + offset) % len(keys)
        try:
            data = _post(keys[index], body)
        except urllib.error.HTTPError as exc:
            if exc.code not in ROTATE_STATUSES:
                raise
            statuses.append(exc.code)
            log.warning("Gemini key #%d returned HTTP %d (%s); trying the next key",
                        index + 1, exc.code, _error_detail(exc))
            continue
        with _lock:
            _current = index
        return _extract_text(data)

    if all(code == 429 for code in statuses):
        _exhausted_until = time.monotonic() + QUOTA_COOLDOWN
    elif all(code == 403 for code in statuses) and len(keys) > 1:
        log.error("Every Gemini key returned 403; check the model name and API permissions, not only the keys")
    raise AllKeysFailed(f"All {len(keys)} Gemini API keys failed (HTTP {', '.join(map(str, statuses))})")
