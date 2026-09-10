from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd
import psycopg


SAFE_LTREE_RE = re.compile(r"[^A-Za-z0-9_]+")


def clean_value(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()
    if hasattr(value, "date") and value.__class__.__module__.startswith("pandas"):
        return value.date()
    return value


def ltree_label(label: str) -> str:
    label = label.replace("đ", "dd").replace("Đ", "DD")
    label = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii")
    label = SAFE_LTREE_RE.sub("_", label).strip("_")
    if not label:
        return "x"
    if label[0].isdigit():
        label = f"n{label}"
    return label


def to_ltree(path: str | None) -> str | None:
    path = clean_value(path)
    if not path:
        return None
    return ".".join(ltree_label(part) for part in str(path).split("."))


def to_range(start, end) -> str | None:
    start = clean_value(start)
    end = clean_value(end)
    if start is None and end is None:
        return None
    if start is None:
        return f"(,{int(end)}]"
    if end is None:
        return f"[{int(start)},)"
    return f"[{int(start)},{int(end)}]"


def rows(con: duckdb.DuckDBPyConnection, table: str, columns: Iterable[str] | None = None):
    selected = "*" if columns is None else ", ".join(columns)
    df = con.execute(f"SELECT {selected} FROM {table}").fetchdf()
    for record in df.to_dict("records"):
        yield {key: clean_value(value) for key, value in record.items()}


def execute_many(pg: psycopg.Connection, sql: str, values: list[tuple], page_size: int = 1000) -> None:
    if not values:
        return
    with pg.cursor() as cur:
        for i in range(0, len(values), page_size):
            cur.executemany(sql, values[i : i + page_size])


def truncate_all(pg: psycopg.Connection) -> None:
    with pg.cursor() as cur:
        cur.execute(
            """
            TRUNCATE
              chunks, parse_quality_reports, parse_coverage, footnotes,
              appendix_table_rows, appendix_tables, appendix_blocks,
              semantic_signals, definitions, document_edges,
              amendments, provision_versions, provisions,
              preamble_items, document_outline_items, document_blocks,
              document_lines, document_parts,
              ingest_ledger, document_versions, documents, raw_docs
            RESTART IDENTITY CASCADE
            """
        )


def import_db(duckdb_path: Path, dsn: str, truncate: bool) -> None:
    duck = duckdb.connect(str(duckdb_path))
    with psycopg.connect(dsn) as pg:
        if truncate:
            truncate_all(pg)

        execute_many(
            pg,
            """
            INSERT INTO raw_docs
              (doc_id, source, source_url, fetched_at, content_hash, raw_body)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (doc_id) DO UPDATE SET
              source = excluded.source,
              source_url = excluded.source_url,
              fetched_at = excluded.fetched_at,
              content_hash = excluded.content_hash,
              raw_body = excluded.raw_body
            """,
            [
                (
                    r["doc_id"],
                    r["source"],
                    r["source_url"],
                    r["fetched_at"],
                    r["content_hash"],
                    r["raw_body"],
                )
                for r in rows(duck, "raw_docs")
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO documents
              (doc_id, so_ky_hieu, loai_van_ban, co_quan, scope, trich_yeu,
               ngay_ban_hanh, ngay_hieu_luc, ngay_het_hieu_luc, tinh_trang,
               linh_vuc, nguoi_ky, chuc_danh, content_hash, parser_version)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                (
                    r["doc_id"],
                    r["so_ky_hieu"],
                    r["loai_van_ban"],
                    r["co_quan"],
                    r["scope"],
                    r["trich_yeu"],
                    r["ngay_ban_hanh"],
                    r["ngay_hieu_luc"],
                    r["ngay_het_hieu_luc"],
                    r["tinh_trang"],
                    r["linh_vuc"],
                    r["nguoi_ky"],
                    r["chuc_danh"],
                    r["content_hash"],
                    r["parser_version"],
                )
                for r in rows(duck, "documents")
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO document_versions
              (doc_id, version_no, source, source_url, metadata_hash, content_hash,
               seen_from, seen_to, is_current, change_status, so_ky_hieu, loai_van_ban,
               co_quan, scope, trich_yeu, ngay_ban_hanh, ngay_hieu_luc,
               ngay_het_hieu_luc, tinh_trang, linh_vuc, nguoi_ky, chuc_danh, raw_text)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                (
                    r["doc_id"],
                    r["version_no"],
                    r["source"],
                    r["source_url"],
                    r["metadata_hash"],
                    r["content_hash"],
                    r["seen_from"],
                    r["seen_to"],
                    r["is_current"],
                    r["change_status"],
                    r["so_ky_hieu"],
                    r["loai_van_ban"],
                    r["co_quan"],
                    r["scope"],
                    r["trich_yeu"],
                    r["ngay_ban_hanh"],
                    r["ngay_hieu_luc"],
                    r["ngay_het_hieu_luc"],
                    r["tinh_trang"],
                    r["linh_vuc"],
                    r["nguoi_ky"],
                    r["chuc_danh"],
                    r["raw_text"],
                )
                for r in rows(duck, "document_versions")
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO ingest_ledger
              (doc_id, source, source_url, metadata_hash, content_hash,
               current_version_no, last_snapshot, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                (
                    r["doc_id"],
                    r["source"],
                    r["source_url"],
                    r["metadata_hash"],
                    r["content_hash"],
                    r["current_version_no"],
                    r["last_snapshot"],
                    r["status"],
                )
                for r in rows(duck, "ingest_ledger")
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO document_parts
              (part_id, doc_id, parent_part_id, part_type, title, attachment_label,
               path_prefix, starts_at_ord, ends_at_ord, raw_heading)
            VALUES (%s,%s,%s,%s,%s,%s,%s::ltree,%s,%s,%s)
            """,
            [
                (
                    r["part_id"],
                    r["doc_id"],
                    r["parent_part_id"],
                    r["part_type"],
                    r["title"],
                    r["attachment_label"],
                    to_ltree(r["path_prefix"]),
                    r["starts_at_ord"],
                    r["ends_at_ord"],
                    r["raw_heading"],
                )
                for r in rows(duck, "document_parts")
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO document_lines
              (doc_id, version_no, line_no, section, raw_text, normalized_text, is_blank)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                (
                    r["doc_id"],
                    r["version_no"],
                    r["line_no"],
                    r["section"],
                    r["raw_text"],
                    r["normalized_text"],
                    r["is_blank"],
                )
                for r in rows(duck, "document_lines")
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO document_blocks
              (block_id, doc_id, version_no, part_id, block_type, ord, raw_text, normalized_text)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                (
                    r["block_id"],
                    r["doc_id"],
                    r["version_no"],
                    r["part_id"],
                    r["block_type"],
                    r["ord"],
                    r["raw_text"],
                    r["normalized_text"],
                )
                for r in rows(duck, "document_blocks")
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO preamble_items
              (doc_id, item_type, ord, raw_text, target_so_ky_hieu,
               resolved_doc_id, evidence_span)
            VALUES (%s,%s,%s,%s,%s,%s,%s::int4range)
            """,
            [
                (
                    r["doc_id"],
                    r["item_type"],
                    r["ord"],
                    r["raw_text"],
                    r["target_so_ky_hieu"],
                    r["resolved_doc_id"],
                    to_range(r["evidence_start"], r["evidence_end"]),
                )
                for r in rows(duck, "preamble_items")
            ],
        )

        provision_ids = {r["provision_id"] for r in rows(duck, "provisions", ["provision_id"])}
        provisions = list(rows(duck, "provisions"))
        execute_many(
            pg,
            """
            INSERT INTO provisions
              (provision_id, doc_id, part_id, parent_id, path, legal_path,
               source_context, quote_id, level,
               legal_role, number, heading, breadcrumb, depth, ord, line_start,
               line_end, text, text_full, valid_from, valid_to)
            VALUES (%s,%s,%s,%s,%s::ltree,%s::ltree,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                (
                    r["provision_id"],
                    r["doc_id"],
                    r["part_id"],
                    r["parent_id"] if r["parent_id"] in provision_ids else None,
                    to_ltree(r["path"]),
                    to_ltree(r["legal_path"]),
                    r.get("source_context") or "own",
                    r.get("quote_id"),
                    r["level"],
                    r["legal_role"],
                    r["number"],
                    r["heading"],
                    r["breadcrumb"],
                    r["depth"],
                    r["ord"],
                    r["line_start"],
                    r["line_end"],
                    r["text"],
                    r["text_full"],
                    r["valid_from"],
                    r["valid_to"],
                )
                for r in sorted(provisions, key=lambda x: (x["doc_id"], x["ord"] or 0))
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO provision_versions
              (provision_key, provision_id, doc_id, version_no, legal_path,
               source_context, quote_id, text_full, is_current, effective_status, seen_from, seen_to,
               valid_from, valid_to)
            VALUES (%s,%s,%s,%s,%s::ltree,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (provision_key, valid_from) DO NOTHING
            """,
            [
                (
                    r["provision_id"],
                    r["provision_id"],
                    r["doc_id"],
                    r["version_no"],
                    to_ltree(r["legal_path"]),
                    r.get("source_context") or "own",
                    r.get("quote_id"),
                    r["text_full"],
                    r["is_current"],
                    r["effective_status"],
                    r["seen_from"],
                    r["seen_to"],
                    r["valid_from"],
                    r["valid_to"],
                )
                for r in rows(duck, "provision_versions")
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO amendments
              (src_doc_id, src_provision_id, op, target_so_ky_hieu, target_dieu,
               target_khoan, target_diem, resolved_target_provision_id,
               effective_date, replacement_text, evidence_text, evidence_span)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::int4range)
            """,
            [
                (
                    r["src_doc_id"],
                    r["src_provision_id"] if r["src_provision_id"] in provision_ids else None,
                    r["op"],
                    r["target_so_ky_hieu"],
                    r["target_dieu"],
                    r["target_khoan"],
                    r["target_diem"],
                    r["resolved_target_provision_id"],
                    r["effective_date"],
                    r["replacement_text"],
                    r["evidence_text"],
                    to_range(r["evidence_start"], r["evidence_end"]),
                )
                for r in rows(duck, "amendments")
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO definitions
              (doc_id, provision_id, term, term_norm, definition)
            VALUES (%s,%s,%s,%s,%s)
            """,
            [
                (
                    r["doc_id"],
                    r["provision_id"] if r["provision_id"] in provision_ids else None,
                    r["term"],
                    (r["term"] or "").lower() if r["term"] else None,
                    r["definition"],
                )
                for r in rows(duck, "definitions")
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO document_edges
              (relation_type, src_doc_id, src_part_id, src_provision_id,
               target_doc_id, target_part_id, target_provision_id, target_so_ky_hieu,
               target_dieu, target_khoan, target_diem, evidence_text, evidence_span,
               source_method, confidence, resolved, effective_date)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::int4range,%s,%s,%s,%s)
            """,
            [
                (
                    r["relation_type"],
                    r["src_doc_id"],
                    r["src_part_id"],
                    r["src_provision_id"] if r["src_provision_id"] in provision_ids else None,
                    r["target_doc_id"],
                    r["target_part_id"],
                    r["target_provision_id"] if r["target_provision_id"] in provision_ids else None,
                    r["target_so_ky_hieu"],
                    r["target_dieu"],
                    r["target_khoan"],
                    r["target_diem"],
                    r["evidence_text"],
                    to_range(r["evidence_start"], r["evidence_end"]),
                    r["source_method"],
                    r["confidence"],
                    r["resolved"],
                    r["effective_date"],
                )
                for r in rows(duck, "document_edges")
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO semantic_signals
              (doc_id, provision_id, signal_type, value, value_norm,
               evidence_text, evidence_span, confidence, source_method)
            VALUES (%s,%s,%s,%s,%s,%s,%s::int4range,%s,%s)
            """,
            [
                (
                    r["doc_id"],
                    r["provision_id"] if r["provision_id"] in provision_ids else None,
                    r["signal_type"],
                    r["value"],
                    r["value_norm"],
                    r["evidence_text"],
                    to_range(r["evidence_start"], r["evidence_end"]),
                    r["confidence"],
                    r["source_method"],
                )
                for r in rows(duck, "semantic_signals")
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO appendix_blocks
              (block_id, part_id, doc_id, block_type, ord, title, raw_text, structured_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            [
                (
                    r["block_id"],
                    r["part_id"],
                    r["doc_id"],
                    r["block_type"],
                    r["ord"],
                    r["title"],
                    r["raw_text"],
                    r["structured_json"] if r["structured_json"] else json.dumps(None),
                )
                for r in rows(duck, "appendix_blocks")
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO appendix_tables
              (table_id, doc_id, part_id, table_no, start_ord, end_ord,
               header_json, n_rows, n_cols)
            VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
            """,
            [
                (
                    r["table_id"],
                    r["doc_id"],
                    r["part_id"],
                    r["table_no"],
                    r["start_ord"],
                    r["end_ord"],
                    r["header_json"] if r["header_json"] else json.dumps([]),
                    r["n_rows"],
                    r["n_cols"],
                )
                for r in rows(duck, "appendix_tables")
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO appendix_table_rows
              (table_id, doc_id, part_id, table_no, row_index, source_ord,
               raw_text, cells_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            [
                (
                    r["table_id"],
                    r["doc_id"],
                    r["part_id"],
                    r["table_no"],
                    r["row_index"],
                    r["source_ord"],
                    r["raw_text"],
                    r["cells_json"] if r["cells_json"] else json.dumps({}),
                )
                for r in rows(duck, "appendix_table_rows")
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO footnotes
              (doc_id, version_no, ord, raw_text)
            VALUES (%s,%s,%s,%s)
            """,
            [(r["doc_id"], r["version_no"], r["ord"], r["raw_text"]) for r in rows(duck, "footnotes")],
        )

        execute_many(
            pg,
            """
            INSERT INTO parse_coverage
              (doc_id, version_no, line_no, section, status, provision_id, reason, raw_text)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                (
                    r["doc_id"],
                    r["version_no"],
                    r["line_no"],
                    r["section"],
                    r["status"],
                    r["provision_id"] if r["provision_id"] in provision_ids else None,
                    r["reason"],
                    r["raw_text"],
                )
                for r in rows(duck, "parse_coverage")
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO parse_quality_reports
              (doc_id, version_no, n_lines, n_body_lines, n_parsed_body_lines,
               n_orphan_body_lines, n_footnote_lines, coverage_ratio, parse_status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                (
                    r["doc_id"],
                    r["version_no"],
                    r["n_lines"],
                    r["n_body_lines"],
                    r["n_parsed_body_lines"],
                    r["n_orphan_body_lines"],
                    r["n_footnote_lines"],
                    r["coverage_ratio"],
                    r["parse_status"],
                )
                for r in rows(duck, "parse_quality_reports")
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO chunks
              (chunk_id, doc_id, part_id, provision_id, version_no, level,
               citation, embed_text, raw_text, n_chars)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                (
                    r["chunk_id"],
                    r["doc_id"],
                    r["part_id"],
                    r["provision_id"] if r["provision_id"] in provision_ids else None,
                    r["version_no"],
                    r["level"],
                    r["citation"],
                    r["embed_text"],
                    r["raw_text"],
                    r["n_chars"],
                )
                for r in rows(duck, "chunks")
            ],
        )

        execute_many(
            pg,
            """
            INSERT INTO document_outline_items
              (outline_id, doc_id, version_no, section_ord, item_ord, section,
               item_type, part_id, provision_id, parent_id, level, path,
               legal_path, source_context, quote_id, number, heading, breadcrumb, line_start, line_end,
               text, text_full)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::ltree,%s::ltree,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                (
                    r["outline_id"],
                    r["doc_id"],
                    r["version_no"],
                    r["section_ord"],
                    r["item_ord"],
                    r["section"],
                    r["item_type"],
                    r["part_id"],
                    r["provision_id"] if r["provision_id"] in provision_ids else None,
                    r["parent_id"] if r["parent_id"] in provision_ids else None,
                    r["level"],
                    to_ltree(r["path"]),
                    to_ltree(r["legal_path"]),
                    r.get("source_context"),
                    r.get("quote_id"),
                    r["number"],
                    r["heading"],
                    r["breadcrumb"],
                    r["line_start"],
                    r["line_end"],
                    r["text"],
                    r["text_full"],
                )
                for r in rows(duck, "document_outline_items")
            ],
        )

        pg.commit()

        with pg.cursor() as cur:
            cur.execute(
                """
                SELECT 'documents' AS table_name, count(1) FROM documents
                UNION ALL SELECT 'appendix_tables', count(1) FROM appendix_tables
                UNION ALL SELECT 'appendix_table_rows', count(1) FROM appendix_table_rows
                UNION ALL SELECT 'document_lines', count(1) FROM document_lines
                UNION ALL SELECT 'document_outline_items', count(1) FROM document_outline_items
                UNION ALL SELECT 'provisions', count(1) FROM provisions
                UNION ALL SELECT 'chunks', count(1) FROM chunks
                UNION ALL SELECT 'document_edges', count(1) FROM document_edges
                UNION ALL SELECT 'parse_quality_reports', count(1) FROM parse_quality_reports
                ORDER BY table_name
                """
            )
            for table_name, count in cur.fetchall():
                print(f"{table_name}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import sampled DuckDB VBPL data into Postgres.")
    parser.add_argument("--duckdb", default="legal_sample_200.duckdb", help="Source DuckDB file")
    parser.add_argument(
        "--dsn",
        default="postgresql://vbpl:vbpl_dev@localhost:5433/vbpl",
        help="Postgres DSN",
    )
    parser.add_argument("--truncate", action="store_true", help="Truncate target tables first")
    args = parser.parse_args()

    duckdb_path = Path(args.duckdb).resolve()
    if not duckdb_path.exists():
        raise SystemExit(f"DuckDB file not found: {duckdb_path}")
    import_db(duckdb_path, args.dsn, args.truncate)


if __name__ == "__main__":
    main()
