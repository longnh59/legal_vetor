"""P5 - load parsed nodes + metadata + relationships into a local DuckDB file
(PLAN_v2 section 4, "P5 | PostgreSQL + ltree, nap metadata + relationships").
No live Postgres in this environment - DuckDB stands in, single embedded file.

Per plan section 7: only 'clean' and 'warn' docs get indexed into `nodes`;
'failed' docs are excluded (queued for review, not indexed).
"""

from pathlib import Path

import duckdb

from engine.classify import Classifier
from engine.config import METADATA_PARQUET, REPORTS_DIR, REPO_ROOT, RELATIONSHIPS_PARQUET
from engine.io import iter_content_rows, metadata_by_id
from engine.parse_document import parse_document

DB_PATH = REPO_ROOT / "engine" / "legal.duckdb"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

NODE_COLUMNS = [
    "node_id", "doc_id", "part_id", "parent_id", "path", "depth", "order_index",
    "node_type", "number_raw", "number_norm", "heading", "text", "text_full",
    "breadcrumb", "html_raw", "confidence", "classified_by",
]


def _parse_date_sql(col: str) -> str:
    # metadata dates are DD/MM/YYYY strings (plan section 2.2: "phai parse, khong tin kieu du lieu")
    return f"TRY_STRPTIME({col}, '%d/%m/%Y')::DATE AS {col}"


def load_all(db_path: Path = DB_PATH, batch_size: int = 2000) -> duckdb.DuckDBPyConnection:
    db_path.unlink(missing_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute(SCHEMA_PATH.read_text(encoding="utf-8"))

    con.execute(f"""
        INSERT INTO documents
        SELECT id, title, so_ky_hieu,
               {_parse_date_sql("ngay_ban_hanh")},
               loai_van_ban,
               {_parse_date_sql("ngay_co_hieu_luc")},
               {_parse_date_sql("ngay_het_hieu_luc")},
               nguon_thu_thap, nganh, linh_vuc, co_quan_ban_hanh,
               chuc_danh, nguoi_ky, pham_vi, thong_tin_ap_dung, tinh_trang_hieu_luc
        FROM read_parquet('{METADATA_PARQUET.as_posix()}')
    """)
    print("documents:", con.execute("SELECT count(*) FROM documents").fetchone()[0])

    con.execute(f"INSERT INTO document_relationships SELECT * FROM read_parquet('{RELATIONSHIPS_PARQUET.as_posix()}')")
    print("document_relationships:", con.execute("SELECT count(*) FROM document_relationships").fetchone()[0])

    quality_path = REPORTS_DIR / "quality.parquet"
    con.execute(f"INSERT INTO parse_quality SELECT * FROM read_parquet('{quality_path.as_posix()}')")
    print("parse_quality:", con.execute("SELECT count(*) FROM parse_quality").fetchone()[0])

    indexable = {
        row[0]
        for row in con.execute("SELECT doc_id FROM parse_quality WHERE verdict IN ('clean', 'warn')").fetchall()
    }
    print(f"{len(indexable)} docs to parse into nodes (clean+warn)")

    meta = metadata_by_id()
    classifier = Classifier()
    placeholders = ",".join(["?"] * len(NODE_COLUMNS))
    batch: list[tuple] = []
    total_nodes = 0

    def flush():
        nonlocal batch, total_nodes
        if not batch:
            return
        con.executemany(f"INSERT INTO nodes VALUES ({placeholders})", batch)
        total_nodes += len(batch)
        batch = []

    for row in iter_content_rows():
        doc_id = row["id"]
        if doc_id not in indexable:
            continue
        m = meta.get(doc_id, {})
        nodes = parse_document(doc_id, row.get("content_html") or "", classifier, so_ky_hieu=m.get("so_ky_hieu"))
        for n in nodes:
            d = n.model_dump()
            batch.append(tuple(d[c] for c in NODE_COLUMNS))
        if len(batch) >= batch_size:
            flush()
    flush()
    print("nodes:", total_nodes)

    return con


def demo() -> None:
    """Schema-only smoke test: no parquet files touched, verifies schema.sql is
    valid DuckDB DDL and the nodes table accepts a row shaped like Node.model_dump()."""
    con = duckdb.connect(":memory:")
    con.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    con.execute("INSERT INTO documents (id, title) VALUES ('d1', 'Test Doc')")
    placeholders = ",".join(["?"] * len(NODE_COLUMNS))
    row = tuple(
        {
            "node_id": "d1/p1/dieu-1", "doc_id": "d1", "part_id": "p1", "parent_id": None,
            "path": "dieu_1", "depth": 0, "order_index": 0, "node_type": "dieu",
            "number_raw": "1", "number_norm": "1", "heading": "Điều 1", "text": "Điều 1. Test",
            "text_full": "Điều 1. Test", "breadcrumb": "Điều 1", "html_raw": "<p>Điều 1. Test</p>",
            "confidence": 0.95, "classified_by": "regex",
        }[c]
        for c in NODE_COLUMNS
    )
    con.execute(f"INSERT INTO nodes VALUES ({placeholders})", row)
    assert con.execute("SELECT count(*) FROM nodes WHERE doc_id = 'd1'").fetchone()[0] == 1
    assert con.execute("SELECT node_type FROM nodes WHERE node_id = 'd1/p1/dieu-1'").fetchone()[0] == "dieu"
    con.close()
    print("load_duckdb.py demo OK")


if __name__ == "__main__":
    demo()
