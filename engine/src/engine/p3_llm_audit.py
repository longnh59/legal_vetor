"""Spot-check the T5 (rule-based) validator: sample docs it scored 'clean' and
ask an LLM to independently judge whether the resulting Dieu/Khoan/Diem tree
looks structurally correct against the raw text - a second opinion on
whether "clean" is really clean, not just whether the rules say so."""

import pyarrow.dataset as ds
import pyarrow.parquet as pq

from engine.classify import Classifier
from engine.classify_llm import LlmClassifier
from engine.config import CONTENT_PARQUET, REPORTS_DIR
from engine.io import metadata_by_id
from engine.parse_document import parse_document

_SYSTEM_PROMPT = (
    "Bạn kiểm tra chất lượng bóc tách cấu trúc của một văn bản quy phạm pháp luật Việt Nam. "
    "Bạn sẽ nhận được văn bản gốc và cây cấu trúc (Điều/Khoản/Điểm) mà một bộ rule đã dựng ra. "
    "Kiểm tra: có Điều/Khoản/Điểm nào bị thiếu, bị gộp sai, đánh số sai, hoặc bị xếp sai cấp không. "
    "Trả lời NGẮN GỌN: dòng đầu ghi 'OK' nếu cây đúng, hoặc 'LỖI: <mô tả ngắn>' nếu có vấn đề."
)


def _tree_summary(nodes) -> str:
    lines = []
    for n in nodes:
        indent = "  " * n.depth
        lines.append(f"{indent}[{n.node_type} {n.number_raw or ''}] {n.text[:80]}")
    return "\n".join(lines)


def run_audit(sample_size: int = 15) -> None:
    quality = pq.read_table(REPORTS_DIR / "quality.parquet").to_pylist()
    clean_docs = [r for r in quality if r["verdict"] == "clean" and r["n_nodes"] > 0][:sample_size]
    doc_ids = [r["doc_id"] for r in clean_docs]

    meta = metadata_by_id()
    dataset = ds.dataset(CONTENT_PARQUET, format="parquet")
    rows = dataset.to_table(filter=ds.field("id").isin(doc_ids)).to_pylist()
    content = {row["id"]: row["content_html"] for row in rows}

    classifier = Classifier()
    llm = LlmClassifier()

    for idx, doc_id in enumerate(doc_ids, 1):
        m = meta.get(doc_id, {})
        nodes = parse_document(doc_id, content.get(doc_id) or "", classifier, so_ky_hieu=m.get("so_ky_hieu"))
        tree_text = _tree_summary(nodes)
        user_content = f"CÂY CẤU TRÚC ({len(nodes)} node):\n{tree_text[:6000]}"
        try:
            verdict = llm.chat(user_content, system_prompt=_SYSTEM_PROMPT)
        except Exception as e:
            verdict = f"LLM call failed: {e}"
        print(f"[{idx}/{len(doc_ids)}] {doc_id}: {verdict.splitlines()[0] if verdict else '(empty)'}", flush=True)


if __name__ == "__main__":
    run_audit()
