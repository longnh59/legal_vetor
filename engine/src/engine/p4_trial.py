"""P4 trial run: re-validate a sample of currently warn/failed docs with tier D
(LLM) enabled, to measure improvement + cost before committing to the full
~43k-doc run. Compares old verdict (from reports/quality.parquet) vs new."""

from collections import Counter

import pyarrow.dataset as ds
import pyarrow.parquet as pq

from engine.classify import Classifier
from engine.classify_llm import LlmClassifier
from engine.config import CONTENT_PARQUET, REPORTS_DIR
from engine.io import metadata_by_id
from engine.validate import validate_document


def run_trial(sample_size: int = 200) -> None:
    quality = pq.read_table(REPORTS_DIR / "quality.parquet").to_pylist()
    warn_failed = [r for r in quality if r["verdict"] in ("warn", "failed")][:sample_size]
    doc_ids = [r["doc_id"] for r in warn_failed]

    meta = metadata_by_id()
    dataset = ds.dataset(CONTENT_PARQUET, format="parquet")
    rows = dataset.to_table(filter=ds.field("id").isin(doc_ids)).to_pylist()
    content = {row["id"]: row["content_html"] for row in rows}
    classifier = Classifier()
    llm = LlmClassifier()

    before = Counter(r["verdict"] for r in warn_failed)
    after = Counter()
    improved = []

    for r in warn_failed:
        doc_id = r["doc_id"]
        html_str = content.get(doc_id) or ""
        m = meta.get(doc_id, {})
        new_r = validate_document(doc_id, html_str, classifier, so_ky_hieu=m.get("so_ky_hieu"), llm=llm)
        after[new_r.verdict] += 1
        if new_r.verdict != r["verdict"]:
            improved.append((doc_id, r["verdict"], new_r.verdict))

    print(f"Sample: {len(warn_failed)} docs")
    print(f"Before: {dict(before)}")
    print(f"After:  {dict(after)}")
    print(f"Changed: {len(improved)}")
    for doc_id, old_v, new_v in improved[:20]:
        print(f"  {doc_id}: {old_v} -> {new_v}")


if __name__ == "__main__":
    run_trial()
