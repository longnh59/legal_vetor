"""Materialize block streams for the 30 golden_set_ids into tests/golden/.

NOTE: these are auto-generated T1+T2 output, NOT hand-verified trees. PLAN_v2
P1 calls for "30 file JSON cay chuan, tach tay" (hand-split) - that requires a
person with legal-domain knowledge to check each doc's Dieu/Khoan/Diem
structure, which no tool here can fabricate. This gives a regression baseline
(re-run and diff after any clean/flatten change) and a starting point for
manual review; treat it as unverified until someone checks it.
"""

import json

from engine.clean import clean_html
from engine.config import GOLDEN_DIR, PROFILING_DIR
from engine.flatten import flatten
from engine.io import iter_content_rows


def build() -> None:
    golden_ids = json.loads((PROFILING_DIR / "golden_set_ids.json").read_text(encoding="utf-8"))
    wanted = set(golden_ids)
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    found = {}
    for row in iter_content_rows():
        if row["id"] in wanted:
            found[row["id"]] = row["content_html"]
            if len(found) == len(wanted):
                break

    for doc_id in golden_ids:
        html_str = found.get(doc_id, "")
        tree = clean_html(html_str)
        blocks = [] if tree is None else flatten(tree)
        out = GOLDEN_DIR / f"{doc_id}.blocks.json"
        out.write_text(
            json.dumps([b.model_dump() for b in blocks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(f"Wrote {len(golden_ids)} block-stream baselines to {GOLDEN_DIR}")


if __name__ == "__main__":
    build()
