from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def print_df(con: duckdb.DuckDBPyConnection, title: str, sql: str) -> None:
    print(f"\n## {title}")
    df = con.execute(sql).fetchdf()
    if df.empty:
        print("(empty)")
    else:
        print(df.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a sampled legal DuckDB database.")
    parser.add_argument("--db", default="legal_sample_200.duckdb", help="Path to DuckDB database")
    parser.add_argument("--doc-id", default=None, help="Optional document id to inspect in detail")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    con = duckdb.connect(str(db_path))
    print(f"DB: {db_path}")

    print_df(
        con,
        "Tables",
        "SHOW TABLES",
    )

    print_df(
        con,
        "Core Counts",
        """
        SELECT 'documents' AS table_name, count(1) AS n FROM documents
        UNION ALL SELECT 'document_versions', count(1) FROM document_versions
        UNION ALL SELECT 'raw_docs', count(1) FROM raw_docs
        UNION ALL SELECT 'document_lines', count(1) FROM document_lines
        UNION ALL SELECT 'document_blocks', count(1) FROM document_blocks
        UNION ALL SELECT 'document_parts', count(1) FROM document_parts
        UNION ALL SELECT 'preamble_items', count(1) FROM preamble_items
        UNION ALL SELECT 'provisions', count(1) FROM provisions
        UNION ALL SELECT 'provision_versions', count(1) FROM provision_versions
        UNION ALL SELECT 'chunks', count(1) FROM chunks
        UNION ALL SELECT 'document_edges', count(1) FROM document_edges
        UNION ALL SELECT 'semantic_signals', count(1) FROM semantic_signals
        UNION ALL SELECT 'appendix_blocks', count(1) FROM appendix_blocks
        UNION ALL SELECT 'footnotes', count(1) FROM footnotes
        UNION ALL SELECT 'parse_coverage', count(1) FROM parse_coverage
        UNION ALL SELECT 'parse_quality_reports', count(1) FROM parse_quality_reports
        ORDER BY table_name
        """,
    )

    print_df(
        con,
        "Parse Quality",
        """
        SELECT
          parse_status,
          count(1) AS n,
          min(coverage_ratio) AS min_coverage,
          avg(coverage_ratio) AS avg_coverage,
          max(n_orphan_body_lines) AS max_orphan_lines
        FROM parse_quality_reports
        GROUP BY parse_status
        ORDER BY parse_status
        """,
    )

    print_df(
        con,
        "Largest Documents By Lines",
        """
        SELECT
          doc_id,
          n_lines,
          n_body_lines,
          n_parsed_body_lines,
          n_orphan_body_lines,
          coverage_ratio,
          parse_status
        FROM parse_quality_reports
        ORDER BY n_lines DESC
        LIMIT 10
        """,
    )

    print_df(
        con,
        "Document Edge Types",
        """
        SELECT relation_type, count(1) AS n
        FROM document_edges
        GROUP BY relation_type
        ORDER BY n DESC, relation_type
        """,
    )

    print_df(
        con,
        "Semantic Signal Types",
        """
        SELECT signal_type, count(1) AS n
        FROM semantic_signals
        GROUP BY signal_type
        ORDER BY n DESC, signal_type
        """,
    )

    print_df(
        con,
        "Sample Documents",
        """
        SELECT
          d.doc_id,
          d.so_ky_hieu,
          d.loai_van_ban,
          d.co_quan,
          d.ngay_ban_hanh,
          left(d.trich_yeu, 120) AS trich_yeu,
          q.coverage_ratio
        FROM documents d
        LEFT JOIN document_versions v
          ON v.doc_id = d.doc_id AND v.is_current
        LEFT JOIN parse_quality_reports q
          ON q.doc_id = d.doc_id AND q.version_no = v.version_no
        ORDER BY d.doc_id
        LIMIT 15
        """,
    )

    print_df(
        con,
        "Duplicate Legal Paths Preserved",
        """
        SELECT doc_id, legal_path, count(1) AS n, string_agg(path, ', ' ORDER BY path) AS stored_paths
        FROM provisions
        GROUP BY doc_id, legal_path
        HAVING count(1) > 1
        ORDER BY n DESC, doc_id, legal_path
        LIMIT 10
        """,
    )

    print_df(
        con,
        "Orphan Body Lines",
        """
        SELECT doc_id, line_no, section, status, reason, left(raw_text, 140) AS raw_text
        FROM parse_coverage
        WHERE status = 'orphan'
        ORDER BY doc_id, line_no
        LIMIT 20
        """,
    )

    doc_id = args.doc_id or con.execute("SELECT doc_id FROM documents ORDER BY doc_id LIMIT 1").fetchone()[0]
    print(f"\n## Detail For doc_id={doc_id}")

    print_df(
        con,
        "Parts",
        f"""
        SELECT part_id, part_type, title, starts_at_ord, ends_at_ord
        FROM document_parts
        WHERE doc_id = '{doc_id}'
        ORDER BY starts_at_ord, part_id
        """,
    )

    print_df(
        con,
        "First Provisions",
        f"""
        SELECT provision_id, path, legal_path, number, heading, legal_role, line_start, line_end
        FROM provisions
        WHERE doc_id = '{doc_id}'
        ORDER BY ord
        LIMIT 30
        """,
    )

    print_df(
        con,
        "First Raw Lines",
        f"""
        SELECT line_no, section, left(raw_text, 160) AS raw_text
        FROM document_lines
        WHERE doc_id = '{doc_id}' AND version_no = 1
        ORDER BY line_no
        LIMIT 40
        """,
    )


if __name__ == "__main__":
    main()
