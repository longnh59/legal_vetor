# -*- coding: utf-8 -*-
import os
import tempfile

from sample_corpus import DOCS
from vbpl_extract import make_chunks, parse_document
import vbpl_store


def main():
    path = os.path.join(tempfile.gettempdir(), "vbpl_coverage_check.duckdb")
    if os.path.exists(path):
        os.remove(path)
    con = vbpl_store.open_db(path)
    try:
        for name, text in DOCS.items():
            parsed = parse_document(text, doc_id=name)
            vbpl_store.upsert(con, parsed, make_chunks(parsed))

        print(con.execute("""
            SELECT doc_id, n_body_lines, n_parsed_body_lines, n_footnote_lines,
                   n_orphan_body_lines, coverage_ratio, parse_status
            FROM parse_quality_reports
            ORDER BY doc_id
        """).fetchdf().to_string(index=False))
        print("orphan_count", con.execute("""
            SELECT count(1) FROM parse_coverage WHERE status='orphan'
        """).fetchone()[0])
    finally:
        con.close()
        if os.path.exists(path):
            os.remove(path)


if __name__ == "__main__":
    main()
