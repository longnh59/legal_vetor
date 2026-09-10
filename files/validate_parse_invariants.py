# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import duckdb

import vbpl_store


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


Check = tuple[str, str, str, Any]


def scalar(con: duckdb.DuckDBPyConnection, sql: str) -> Any:
    return con.execute(sql).fetchone()[0]


def sample(con: duckdb.DuckDBPyConnection, sql: str, limit: int = 10) -> str:
    frame = con.execute(f"{sql}\nLIMIT {limit}").fetchdf()
    if frame.empty:
        return ""
    return "\n" + frame.to_string(index=False)


def add_check(checks: list[Check], name: str, status: str, detail: str, sample_text: Any = "") -> None:
    checks.append((name, status, detail, sample_text))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate structural parse invariants for the legal-document sample."
    )
    parser.add_argument("--db", default="legal_sample_200.duckdb", help="DuckDB file to validate")
    parser.add_argument("--expected-docs", type=int, default=200)
    parser.add_argument("--sample-limit", type=int, default=8)
    parser.add_argument("--strict-warnings", action="store_true", help="Treat WARN checks as failures")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    con = vbpl_store.open_db(str(db_path))
    checks: list[Check] = []

    doc_count = scalar(con, "SELECT count(1) FROM documents")
    add_check(
        checks,
        "expected_doc_count",
        "PASS" if doc_count == args.expected_docs else "FAIL",
        f"documents={doc_count}, expected={args.expected_docs}",
    )

    quality = con.execute(
        """
        SELECT
          count(1) AS reports,
          count(*) FILTER (WHERE parse_status = 'ok') AS ok_reports,
          min(coverage_ratio) AS min_coverage,
          max(n_orphan_body_lines) AS max_orphan_body_lines
        FROM parse_quality_reports
        """
    ).fetchone()
    reports, ok_reports, min_coverage, max_orphans = quality
    add_check(
        checks,
        "coverage_all_ok",
        "PASS" if reports == doc_count and ok_reports == doc_count and min_coverage == 1 and max_orphans == 0 else "FAIL",
        f"reports={reports}, ok={ok_reports}, min_coverage={min_coverage}, max_orphans={max_orphans}",
    )

    coverage_mismatch = scalar(
        con,
        """
        SELECT count(1)
        FROM (
          SELECT doc_id, version_no, count(1) AS n
          FROM document_lines
          GROUP BY doc_id, version_no
        ) l
        FULL OUTER JOIN (
          SELECT doc_id, version_no, count(1) AS n
          FROM parse_coverage
          GROUP BY doc_id, version_no
        ) c USING (doc_id, version_no)
        WHERE COALESCE(l.n, -1) <> COALESCE(c.n, -1)
        """,
    )
    add_check(
        checks,
        "coverage_has_every_source_line",
        "PASS" if coverage_mismatch == 0 else "FAIL",
        f"line_count_mismatches={coverage_mismatch}",
    )

    duplicate_paths = scalar(
        con,
        """
        SELECT count(1)
        FROM (
          SELECT doc_id, path
          FROM provisions
          GROUP BY doc_id, path
          HAVING count(1) > 1
        ) x
        """,
    )
    add_check(
        checks,
        "unique_storage_paths",
        "PASS" if duplicate_paths == 0 else "FAIL",
        f"duplicate_storage_path_groups={duplicate_paths}",
        sample(
            con,
            """
            SELECT doc_id, path, count(1) AS n
            FROM provisions
            GROUP BY doc_id, path
            HAVING count(1) > 1
            ORDER BY n DESC, doc_id, path
            """,
            args.sample_limit,
        ),
    )

    duplicate_own_legal_paths = scalar(
        con,
        """
        SELECT count(1)
        FROM (
          SELECT doc_id, legal_path
          FROM provisions
          WHERE source_context = 'own'
          GROUP BY doc_id, legal_path
          HAVING count(1) > 1
        ) x
        """,
    )
    add_check(
        checks,
        "unique_own_legal_paths",
        "PASS" if duplicate_own_legal_paths == 0 else "FAIL",
        f"duplicate_own_legal_path_groups={duplicate_own_legal_paths}",
        sample(
            con,
            """
            SELECT doc_id, legal_path, count(1) AS n
            FROM provisions
            WHERE source_context = 'own'
            GROUP BY doc_id, legal_path
            HAVING count(1) > 1
            ORDER BY n DESC, doc_id, legal_path
            """,
            args.sample_limit,
        ),
    )

    missing_parents = scalar(
        con,
        """
        SELECT count(1)
        FROM provisions p
        LEFT JOIN provisions parent
          ON parent.provision_id = p.parent_id
        WHERE p.parent_id IS NOT NULL
          AND parent.provision_id IS NULL
        """,
    )
    add_check(
        checks,
        "all_parent_refs_exist",
        "PASS" if missing_parents == 0 else "FAIL",
        f"missing_parent_refs={missing_parents}",
    )

    bad_parent_prefix = scalar(
        con,
        """
        SELECT count(1)
        FROM provisions p
        JOIN provisions parent
          ON parent.provision_id = p.parent_id
        WHERE p.path NOT LIKE parent.path || '.%'
          AND p.source_context = parent.source_context
          AND COALESCE(p.quote_id, -1) = COALESCE(parent.quote_id, -1)
        """,
    )
    add_check(
        checks,
        "child_path_extends_parent_path",
        "PASS" if bad_parent_prefix == 0 else "FAIL",
        f"bad_parent_prefix={bad_parent_prefix}",
        sample(
            con,
            """
            SELECT p.doc_id, p.path, parent.path AS parent_path
            FROM provisions p
            JOIN provisions parent
              ON parent.provision_id = p.parent_id
            WHERE p.path NOT LIKE parent.path || '.%'
              AND p.source_context = parent.source_context
              AND COALESCE(p.quote_id, -1) = COALESCE(parent.quote_id, -1)
            ORDER BY p.doc_id, p.ord
            """,
            args.sample_limit,
        ),
    )

    cross_context_parents = scalar(
        con,
        """
        SELECT count(1)
        FROM provisions p
        JOIN provisions parent
          ON parent.provision_id = p.parent_id
        WHERE p.source_context <> parent.source_context
           OR COALESCE(p.quote_id, -1) <> COALESCE(parent.quote_id, -1)
        """,
    )
    add_check(
        checks,
        "cross_context_parent_links_recorded",
        "PASS",
        f"cross_context_parent_links={cross_context_parents}",
    )

    missing_outline_refs = scalar(
        con,
        """
        SELECT count(1)
        FROM document_outline_items o
        LEFT JOIN provisions p
          ON p.provision_id = o.provision_id
        WHERE o.provision_id IS NOT NULL
          AND p.provision_id IS NULL
        """,
    )
    add_check(
        checks,
        "outline_refs_exist",
        "PASS" if missing_outline_refs == 0 else "FAIL",
        f"missing_outline_refs={missing_outline_refs}",
    )

    duplicate_preamble_classifications = scalar(
        con,
        """
        SELECT count(1)
        FROM (
          SELECT doc_id, ord, raw_text
          FROM preamble_items
          GROUP BY doc_id, ord, raw_text
          HAVING count(DISTINCT item_type) > 1
        ) x
        """,
    )
    add_check(
        checks,
        "preamble_items_have_single_classification",
        "PASS" if duplicate_preamble_classifications == 0 else "FAIL",
        f"duplicate_preamble_classifications={duplicate_preamble_classifications}",
        sample(
            con,
            """
            SELECT doc_id, ord, raw_text, string_agg(item_type, ',' ORDER BY item_type) AS item_types
            FROM preamble_items
            GROUP BY doc_id, ord, raw_text
            HAVING count(DISTINCT item_type) > 1
            ORDER BY doc_id, ord
            """,
            args.sample_limit,
        ),
    )

    nonempty_provisions = scalar(
        con,
        "SELECT count(1) FROM provisions WHERE NULLIF(trim(COALESCE(text_full, text, heading, '')), '') IS NOT NULL",
    )
    context_units = scalar(con, "SELECT count(1) FROM document_ai_context_units")
    add_check(
        checks,
        "context_units_match_nonempty_provisions",
        "PASS" if context_units == nonempty_provisions else "FAIL",
        f"context_units={context_units}, nonempty_provisions={nonempty_provisions}",
    )

    missing_context_source_lines = scalar(
        con,
        """
        SELECT count(1)
        FROM document_ai_context_units
        WHERE source_line_start IS NULL
           OR source_line_end IS NULL
        """,
    )
    add_check(
        checks,
        "context_units_have_source_line_refs",
        "PASS" if missing_context_source_lines == 0 else "FAIL",
        f"missing_context_source_line_refs={missing_context_source_lines}",
        sample(
            con,
            """
            SELECT context_id, doc_id, path, line_start, line_end, source_line_start, source_line_end
            FROM document_ai_context_units
            WHERE source_line_start IS NULL
               OR source_line_end IS NULL
            ORDER BY doc_id, ord
            """,
            args.sample_limit,
        ),
    )

    invalid_context_source_lines = scalar(
        con,
        """
        SELECT count(1)
        FROM document_ai_context_units u
        LEFT JOIN document_lines ls
          ON ls.doc_id = u.doc_id
         AND ls.version_no = u.version_no
         AND ls.line_no = u.source_line_start
        LEFT JOIN document_lines le
          ON le.doc_id = u.doc_id
         AND le.version_no = u.version_no
         AND le.line_no = u.source_line_end
        WHERE ls.line_no IS NULL
           OR le.line_no IS NULL
           OR ls.section <> 'body'
           OR le.section <> 'body'
        """,
    )
    add_check(
        checks,
        "context_source_line_refs_join_document_lines",
        "PASS" if invalid_context_source_lines == 0 else "FAIL",
        f"invalid_context_source_line_refs={invalid_context_source_lines}",
    )

    nonempty_outline_items = scalar(
        con,
        """
        SELECT count(1)
        FROM document_outline_items
        WHERE NULLIF(trim(COALESCE(text_full, text, '')), '') IS NOT NULL
        """,
    )
    outline_context_units = scalar(con, "SELECT count(1) FROM document_ai_context_outline_units")
    add_check(
        checks,
        "outline_context_units_match_nonempty_outline_items",
        "PASS" if outline_context_units == nonempty_outline_items else "FAIL",
        f"outline_context_units={outline_context_units}, nonempty_outline_items={nonempty_outline_items}",
    )

    missing_outline_source_lines = scalar(
        con,
        """
        SELECT count(1)
        FROM document_ai_context_outline_units
        WHERE source_line_start IS NULL
           OR source_line_end IS NULL
        """,
    )
    add_check(
        checks,
        "outline_context_units_have_source_line_refs",
        "PASS" if missing_outline_source_lines == 0 else "FAIL",
        f"missing_outline_source_line_refs={missing_outline_source_lines}",
        sample(
            con,
            """
            SELECT context_id, doc_id, section, item_ord, line_start, line_end, source_line_start, source_line_end
            FROM document_ai_context_outline_units
            WHERE source_line_start IS NULL
               OR source_line_end IS NULL
            ORDER BY doc_id, section_ord, item_ord
            """,
            args.sample_limit,
        ),
    )

    invalid_outline_source_lines = scalar(
        con,
        """
        SELECT count(1)
        FROM document_ai_context_outline_units u
        LEFT JOIN document_lines ls
          ON ls.doc_id = u.doc_id
         AND ls.version_no = u.version_no
         AND ls.line_no = u.source_line_start
        LEFT JOIN document_lines le
          ON le.doc_id = u.doc_id
         AND le.version_no = u.version_no
         AND le.line_no = u.source_line_end
        WHERE ls.line_no IS NULL
           OR le.line_no IS NULL
        """,
    )
    add_check(
        checks,
        "outline_source_line_refs_join_document_lines",
        "PASS" if invalid_outline_source_lines == 0 else "FAIL",
        f"invalid_outline_source_line_refs={invalid_outline_source_lines}",
    )

    source_line_count = scalar(con, "SELECT count(1) FROM document_ai_source_lines")
    document_line_count = scalar(con, "SELECT count(1) FROM document_lines")
    add_check(
        checks,
        "source_line_view_matches_document_lines",
        "PASS" if source_line_count == document_line_count else "FAIL",
        f"source_line_view_rows={source_line_count}, document_lines={document_line_count}",
    )

    unmapped_nonblank_source_lines = scalar(
        con,
        """
        SELECT count(1)
        FROM document_ai_source_lines
        WHERE NOT is_blank
          AND (context_count = 0 OR primary_context_id IS NULL)
        """,
    )
    add_check(
        checks,
        "nonblank_source_lines_have_context",
        "PASS" if unmapped_nonblank_source_lines == 0 else "FAIL",
        f"unmapped_nonblank_source_lines={unmapped_nonblank_source_lines}",
        sample(
            con,
            """
            SELECT doc_id, version_no, line_no, section, parse_status, parse_reason, raw_text
            FROM document_ai_source_lines
            WHERE NOT is_blank
              AND (context_count = 0 OR primary_context_id IS NULL)
            ORDER BY doc_id, version_no, line_no
            """,
            args.sample_limit,
        ),
    )

    expected_table_context_units = scalar(
        con,
        """
        SELECT
          (SELECT count(1) FROM appendix_tables)
          + (SELECT count(1) FROM provisions WHERE regexp_matches(COALESCE(text, ''), '\\|[^\\n]*\\|'))
        """,
    )
    table_context_units = scalar(con, "SELECT count(1) FROM document_ai_table_context_units")
    add_check(
        checks,
        "table_context_units_cover_appendix_and_embedded_tables",
        "PASS" if table_context_units == expected_table_context_units else "FAIL",
        f"table_context_units={table_context_units}, expected={expected_table_context_units}",
    )

    embedded_tables_missing_source_refs = scalar(
        con,
        """
        SELECT count(1)
        FROM document_ai_table_context_units
        WHERE source_kind = 'provision_embedded_table'
          AND (source_line_start IS NULL OR source_line_end IS NULL)
        """,
    )
    add_check(
        checks,
        "embedded_table_context_units_have_source_refs",
        "PASS" if embedded_tables_missing_source_refs == 0 else "FAIL",
        f"embedded_tables_missing_source_refs={embedded_tables_missing_source_refs}",
        sample(
            con,
            """
            SELECT table_context_id, doc_id, provision_id, source_line_start, source_line_end, title
            FROM document_ai_table_context_units
            WHERE source_kind = 'provision_embedded_table'
              AND (source_line_start IS NULL OR source_line_end IS NULL)
            ORDER BY doc_id, table_context_id
            """,
            args.sample_limit,
        ),
    )

    bad_quote_rows = scalar(
        con,
        """
        SELECT count(1)
        FROM provisions
        WHERE (source_context = 'quoted_target' AND (quote_id IS NULL OR path NOT LIKE 'q' || quote_id || '.%'))
           OR (source_context = 'own' AND quote_id IS NOT NULL)
        """,
    )
    add_check(
        checks,
        "quote_context_is_consistent",
        "PASS" if bad_quote_rows == 0 else "FAIL",
        f"bad_quote_rows={bad_quote_rows}",
        sample(
            con,
            """
            SELECT doc_id, path, legal_path, source_context, quote_id
            FROM provisions
            WHERE (source_context = 'quoted_target' AND (quote_id IS NULL OR path NOT LIKE 'q' || quote_id || '.%'))
               OR (source_context = 'own' AND quote_id IS NOT NULL)
            ORDER BY doc_id, ord
            """,
            args.sample_limit,
        ),
    )

    bad_ranges = scalar(
        con,
        """
        SELECT count(1)
        FROM provisions p
        JOIN (
          SELECT doc_id, count(1) FILTER (WHERE section = 'body' AND NOT is_blank) AS n_body
          FROM document_lines
          GROUP BY doc_id
        ) b ON b.doc_id = p.doc_id
        WHERE p.line_start IS NULL
           OR p.line_end IS NULL
           OR p.line_start < 0
           OR p.line_end < p.line_start
           OR p.line_start >= b.n_body
        """,
    )
    add_check(
        checks,
        "provision_line_ranges_valid",
        "PASS" if bad_ranges == 0 else "FAIL",
        f"bad_line_ranges={bad_ranges}",
    )

    appendix_table_issues = scalar(
        con,
        """
        SELECT count(1)
        FROM appendix_tables t
        WHERE t.n_rows <= 0
           OR t.n_cols < 2
           OR NOT EXISTS (
             SELECT 1
             FROM appendix_table_rows r
             WHERE r.table_id = t.table_id
           )
        """,
    )
    add_check(
        checks,
        "appendix_tables_have_rows_and_columns",
        "PASS" if appendix_table_issues == 0 else "FAIL",
        f"appendix_table_issues={appendix_table_issues}",
    )

    missing_chunk_refs = scalar(
        con,
        """
        SELECT count(1)
        FROM chunks c
        LEFT JOIN provisions p
          ON p.provision_id = c.provision_id
        WHERE c.provision_id IS NOT NULL
          AND p.provision_id IS NULL
        """,
    )
    add_check(
        checks,
        "chunk_refs_exist",
        "PASS" if missing_chunk_refs == 0 else "FAIL",
        f"missing_chunk_refs={missing_chunk_refs}",
    )

    oversized_chunks = scalar(con, "SELECT count(1) FROM chunks WHERE n_chars > 2200")
    add_check(
        checks,
        "retrieval_chunks_respect_size_limit",
        "PASS" if oversized_chunks == 0 else "FAIL",
        f"oversized_chunks={oversized_chunks}",
        sample(
            con,
            """
            SELECT chunk_id, doc_id, provision_id, level, n_chars, citation
            FROM chunks
            WHERE n_chars > 2200
            ORDER BY n_chars DESC
            """,
            args.sample_limit,
        ),
    )

    missing_retrieval_chunks = scalar(
        con,
        """
        WITH child_counts AS (
          SELECT parent_id AS provision_id, count(1) AS n_children
          FROM provisions
          WHERE parent_id IS NOT NULL
          GROUP BY parent_id
        ),
        expected AS (
          SELECT p.provision_id
          FROM provisions p
          LEFT JOIN child_counts cc ON cc.provision_id = p.provision_id
          WHERE p.level IN ('dieu','khoan','sub_khoan','sub_sub_khoan','diem','tiet')
            AND (
              (COALESCE(cc.n_children, 0) = 0 AND NULLIF(trim(COALESCE(p.text_full, p.text, '')), '') IS NOT NULL)
              OR
              (COALESCE(cc.n_children, 0) > 0 AND NULLIF(trim(COALESCE(p.text, '')), '') IS NOT NULL)
            )
        )
        SELECT count(1)
        FROM expected e
        LEFT JOIN chunks c ON c.provision_id = e.provision_id
        WHERE c.provision_id IS NULL
        """,
    )
    add_check(
        checks,
        "retrieval_chunks_cover_leaf_and_intro_units",
        "PASS" if missing_retrieval_chunks == 0 else "FAIL",
        f"missing_retrieval_chunks={missing_retrieval_chunks}",
        sample(
            con,
            """
            WITH child_counts AS (
              SELECT parent_id AS provision_id, count(1) AS n_children
              FROM provisions
              WHERE parent_id IS NOT NULL
              GROUP BY parent_id
            ),
            expected AS (
              SELECT p.doc_id, p.provision_id, p.level, p.breadcrumb
              FROM provisions p
              LEFT JOIN child_counts cc ON cc.provision_id = p.provision_id
              WHERE p.level IN ('dieu','khoan','sub_khoan','sub_sub_khoan','diem','tiet')
                AND (
                  (COALESCE(cc.n_children, 0) = 0 AND NULLIF(trim(COALESCE(p.text_full, p.text, '')), '') IS NOT NULL)
                  OR
                  (COALESCE(cc.n_children, 0) > 0 AND NULLIF(trim(COALESCE(p.text, '')), '') IS NOT NULL)
                )
            )
            SELECT e.*
            FROM expected e
            LEFT JOIN chunks c ON c.provision_id = e.provision_id
            WHERE c.provision_id IS NULL
            ORDER BY e.doc_id, e.provision_id
            """,
            args.sample_limit,
        ),
    )

    outline_body_text_mismatches = scalar(
        con,
        """
        SELECT count(1)
        FROM document_outline_items o
        JOIN provisions p
          ON p.provision_id = o.provision_id
        WHERE o.section = 'body'
          AND o.provision_id IS NOT NULL
          AND (
            o.text IS DISTINCT FROM COALESCE(NULLIF(trim(p.text), ''), p.heading)
            OR o.text_full IS DISTINCT FROM p.text_full
          )
        """,
    )
    add_check(
        checks,
        "outline_body_text_matches_provisions",
        "PASS" if outline_body_text_mismatches == 0 else "FAIL",
        f"outline_body_text_mismatches={outline_body_text_mismatches}",
        sample(
            con,
            """
            SELECT
              o.outline_id,
              o.provision_id,
              CASE
                WHEN o.text IS DISTINCT FROM COALESCE(NULLIF(trim(p.text), ''), p.heading) THEN 'text'
                ELSE 'text_full'
              END AS mismatch_column,
              CASE
                WHEN o.text IS DISTINCT FROM COALESCE(NULLIF(trim(p.text), ''), p.heading) THEN o.text
                ELSE o.text_full
              END AS outline_text,
              CASE
                WHEN o.text IS DISTINCT FROM COALESCE(NULLIF(trim(p.text), ''), p.heading) THEN COALESCE(NULLIF(trim(p.text), ''), p.heading)
                ELSE p.text_full
              END AS provision_text
            FROM document_outline_items o
            JOIN provisions p
              ON p.provision_id = o.provision_id
            WHERE o.section = 'body'
              AND o.provision_id IS NOT NULL
              AND (
                o.text IS DISTINCT FROM COALESCE(NULLIF(trim(p.text), ''), p.heading)
                OR o.text_full IS DISTINCT FROM p.text_full
              )
            ORDER BY o.doc_id, o.outline_id
            """,
            args.sample_limit,
        ),
    )
    quote_count = scalar(con, "SELECT count(1) FROM provisions WHERE source_context = 'quoted_target'")
    add_check(
        checks,
        "quoted_targets_present",
        "PASS" if quote_count > 0 else "WARN",
        f"quoted_target_nodes={quote_count}",
    )

    self_ref_expire_pattern = (
        "(Lu\u1eadt|Ngh\u1ecb \u0111\u1ecbnh|Ngh\u1ecb quy\u1ebft|"
        "Quy\u1ebft \u0111\u1ecbnh|Th\u00f4ng t\u01b0|Ph\u00e1p l\u1ec7nh)"
        "\\s+n\u00e0y\\s+(?:c\u00f3 hi\u1ec7u l\u1ef1c|\u0111\u01b0\u1ee3c th\u00f4ng qua)"
    )
    doc_ref_pattern = "\\b\\d{1,4}[a-z]?/(?:\\d{4}/)?[A-Z\u0110][A-Z\u01100-9\\-]{1,20}\\b"
    same_clause_doc_ref_pattern = "^[^.;\\n]*" + doc_ref_pattern
    colon_list_doc_ref_pattern = "(?s)^[^.;\\n]*:.*" + doc_ref_pattern
    self_ref_expire_count = con.execute(
        """
        SELECT count(1)
        FROM amendments
        WHERE op = 'EXPIRE'
          AND regexp_matches(evidence_text, ?, 'i')
          AND NOT regexp_matches(evidence_text, ?)
          AND NOT regexp_matches(evidence_text, ?)
        """,
        [self_ref_expire_pattern, same_clause_doc_ref_pattern, colon_list_doc_ref_pattern],
    ).fetchone()[0]
    add_check(
        checks,
        "amendments_no_self_referential_expire",
        "PASS" if self_ref_expire_count == 0 else "FAIL",
        f"self_referential_expire_rows={self_ref_expire_count}",
    )

    failures = [c for c in checks if c[1] == "FAIL"]
    warnings = [c for c in checks if c[1] == "WARN"]

    print(f"DB: {db_path}")
    print("\n## Invariant checks")
    for name, status, detail, sample_text in checks:
        print(f"[{status}] {name}: {detail}")
        if sample_text:
            print(sample_text)

    print("\n## Summary")
    print(f"PASS={sum(1 for c in checks if c[1] == 'PASS')} WARN={len(warnings)} FAIL={len(failures)}")

    con.close()
    if failures or (args.strict_warnings and warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
