"""T4 tier D - LLM classification for the ambiguous residue left after tiers
A/B (PLAN_v2 section 5: "chỉ cho block mơ hồ còn lại, batch, schema cố định").

Only called for blocks where node_type is None or conflict=True - never
replaces a confident regex/css_class result. Uses an OpenAI-compatible
/chat/completions endpoint (config via engine/.env, stdlib urllib only, no
new dependency).
"""

import json
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path

from engine.classify import Classification
from engine.models import Block, NodeType

_NODE_TYPES: tuple[NodeType, ...] = (
    "phan", "chuong", "muc", "tieu_muc", "dieu", "khoan", "diem", "gach_dau_dong", "phu_luc",
)

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

_SYSTEM_PROMPT = (
    "Bạn phân loại một dòng trong văn bản quy phạm pháp luật Việt Nam vào đúng một cấp cấu trúc. "
    f"Chỉ chọn node_type trong: {', '.join(_NODE_TYPES)}, hoặc null nếu dòng này không phải một "
    "mốc cấu trúc (ví dụ: nội dung thường, tiêu đề cơ quan, chữ ký). "
    "Trả lời CHỈ bằng JSON: {\"node_type\": <string|null>, \"number_raw\": <string|null>, "
    "\"confidence\": <float 0-1>}. number_raw là số/chữ cái ngay sau nhãn (vd \"Điều 5\" -> \"5\", "
    "\"a)\" -> \"a\"), null nếu node_type null."
)


def _load_env() -> None:
    if not _ENV_PATH.exists():
        return
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


class LlmClassifier:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None):
        _load_env()
        self.base_url = (base_url or os.environ["LLM_BASE_URL"]).rstrip("/")
        self.api_key = api_key or os.environ["LLM_API_KEY"]
        self.model = model or os.environ["LLM_MODEL"]

    def chat(self, user_content: str, system_prompt: str = _SYSTEM_PROMPT, timeout: int = 60) -> str:
        """Raw chat call, returns the assistant's text content verbatim."""
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
        return payload["choices"][0]["message"]["content"].strip()

    def _call(self, user_content: str) -> dict:
        content = self.chat(user_content)
        if content.startswith("```"):
            content = content.strip("`").removeprefix("json").strip()
        return json.loads(content)

    def classify(self, block: Block, prev_text: str = "", next_text: str = "") -> Classification:
        user_content = (
            f"Dòng trước: {prev_text[:200]!r}\n"
            f"DÒNG CẦN PHÂN LOẠI: {block.text[:400]!r}\n"
            f"Dòng sau: {next_text[:200]!r}"
        )
        try:
            result = self._call(user_content)
        except (urllib.error.URLError, json.JSONDecodeError, KeyError, TimeoutError):
            return Classification(None, None, 0.0, None)

        node_type = result.get("node_type")
        if node_type not in _NODE_TYPES:
            node_type = None
        number_raw = result.get("number_raw") if node_type else None
        confidence = float(result.get("confidence") or 0.0) if node_type else 0.0
        return Classification(node_type, number_raw, confidence, "llm" if node_type else None)


def enrich_with_llm(
    blocks: list[Block],
    classifications: list[Classification],
    llm: LlmClassifier,
    max_workers: int = 10,
) -> list[Classification]:
    """Only touches blocks tier A/B left ambiguous (None type or conflict) - a
    confident regex/css_class result is never overridden by the LLM. Ambiguous
    blocks are independent of each other, so calls run concurrently
    (ThreadPoolExecutor - each call is a blocking network request, not CPU-bound)."""
    out = list(classifications)
    pending = [i for i, cls in enumerate(out) if cls.node_type is None or cls.conflict]
    if not pending:
        return out

    def _classify_at(i: int) -> Classification:
        prev_text = blocks[i - 1].text if i > 0 else ""
        next_text = blocks[i + 1].text if i + 1 < len(blocks) else ""
        return llm.classify(blocks[i], prev_text, next_text)

    # Per-call urlopen(timeout=30) does not always bound wall-clock time (a
    # server trickling bytes can dodge socket-level timeout entirely -
    # verified: one real call hung 30+ minutes). A plain `with ThreadPoolExecutor`
    # would then hang forever too, since __exit__ blocks on shutdown(wait=True).
    # future.result(timeout=...) here is what actually caps the wait; stuck
    # threads are abandoned (cancel_futures, wait=False) rather than joined.
    pool = ThreadPoolExecutor(max_workers=max_workers)
    futures = {pool.submit(_classify_at, i): i for i in pending}
    for fut, i in futures.items():
        try:
            llm_cls = fut.result(timeout=45)
        except FutureTimeoutError:
            continue
        if llm_cls.node_type is not None:
            out[i] = llm_cls
    pool.shutdown(wait=False, cancel_futures=True)
    return out


def demo() -> None:
    print("classify_llm.py: no offline demo (needs live API) - see tests/test_classify_llm_live.py")


if __name__ == "__main__":
    demo()
