# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

import pandas as pd

from vbpl_extract import make_chunks, parse_document
import vbpl_store


def read_rows(root: Path, limit: int) -> pd.DataFrame:
    meta_path = root / "metadata" / "data-00000-of-00001.parquet"
    meta = pd.read_parquet(meta_path)

    rows = []
    wanted_ids = set(meta["id"].head(limit).astype("int64").tolist())
    for content_path in sorted(glob.glob(str(root / "content" / "*.parquet"))):
        content = pd.read_parquet(content_path, columns=["id", "content"])
        hit = content[content["id"].isin(wanted_ids)]
        if not hit.empty:
            rows.append(hit)
        found = sum(len(r) for r in rows)
        if found >= limit:
            break

    if not rows:
        raise RuntimeError("No content rows found")

    content_df = pd.concat(rows, ignore_index=True).drop_duplicates("id")
    sample_ids = meta["id"].head(limit)
    sample = meta[meta["id"].isin(sample_ids)].merge(content_df, on="id", how="inner")
    sample["_ord"] = sample["id"].map({doc_id: i for i, doc_id in enumerate(sample_ids)})
    return sample.sort_values("_ord").drop(columns=["_ord"]).head(limit)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest a parquet sample into DuckDB.")
    parser.add_argument("--root", default=".", help="Dataset root directory")
    parser.add_argument("--db", default="legal_sample_200.duckdb", help="Output DuckDB path")
    parser.add_argument("--limit", type=int, default=200, help="Number of rows to ingest")
    parser.add_argument("--overwrite", action="store_true", help="Remove output DB first")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    db_path = Path(args.db).resolve()
    if args.overwrite and db_path.exists():
        db_path.unlink()

    rows = read_rows(root, args.limit)
    con = vbpl_store.open_db(str(db_path))
    try:
        statuses = {}
        for idx, row in enumerate(rows.itertuples(index=False), 1):
            row_data = row._asdict()
            doc_id = str(row.id)
            text = row.content or ""
            parsed = parse_document(text, doc_id=doc_id, metadata=row_data)
            chunks = make_chunks(parsed)
            result = vbpl_store.upsert(
                con,
                parsed,
                chunks,
                source="thuvienphapluat",
                url=row.url,
            )
            statuses[result["status"]] = statuses.get(result["status"], 0) + 1
            if idx == 1 or idx % 25 == 0 or idx == len(rows):
                print(f"ingested {idx}/{len(rows)} latest={doc_id} status={result['status']}")

        resolution_stats = vbpl_store.resolve_references(con)

        print("\nDB:", db_path)
        print("Statuses:", statuses)
        print("\nResolution:")
        for table in ["amendments", "document_edges"]:
            s = resolution_stats[table]
            print(
                f"{table}: total={s['total']} resolved_docs={s['resolved_docs']} "
                f"resolved_provisions={s['resolved_provisions']} ambiguous={s['ambiguous']} "
                f"not_found={s['not_found']} no_target={s['no_target']} "
                f"provision_miss={s['provision_miss']}"
            )
        if resolution_stats["ambiguous_examples"]:
            print("Ambiguous examples:")
            for so_ky_hieu, co_quan, n_candidates in resolution_stats["ambiguous_examples"]:
                print(f"  {so_ky_hieu}: {n_candidates} candidates ({co_quan})")
        for table in [
            "documents",
            "document_versions",
            "raw_docs",
            "document_lines",
            "document_blocks",
            "provisions",
            "provision_versions",
            "chunks",
            "amendments",
            "document_edges",
            "parse_quality_reports",
        ]:
            count = con.execute(f"SELECT count(1) FROM {table}").fetchone()[0]
            print(f"{table}: {count}")

        print("\nParse quality:")
        print(con.execute("""
            SELECT parse_status, count(1) AS n,
                   min(coverage_ratio) AS min_coverage,
                   avg(coverage_ratio) AS avg_coverage
            FROM parse_quality_reports
            GROUP BY parse_status
            ORDER BY parse_status
        """).fetchdf().to_string(index=False))
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
