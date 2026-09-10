from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import duckdb


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


DOC_TYPE_RE = re.compile(
    r"\b(LUẬT|NGHỊ\s+ĐỊNH|NGHỊ\s+QUYẾT|QUYẾT\s+ĐỊNH|THÔNG\s+TƯ|"
    r"THÔNG\s+TƯ\s+LIÊN\s+TỊCH|CHỈ\s+THỊ|CÔNG\s+VĂN|KẾ\s+HOẠCH|"
    r"VĂN\s+BẢN\s+HỢP\s+NHẤT)\b",
    re.IGNORECASE,
)
AUTHORITY_HINT_RE = re.compile(
    r"\b(QUỐC HỘI|CHÍNH PHỦ|THỦ TƯỚNG|BỘ |ỦY BAN|HỘI ĐỒNG|TÒA ÁN|"
    r"VIỆN KIỂM SÁT|NGÂN HÀNG|TỔNG CỤC|CỤC )",
    re.IGNORECASE,
)


def df(con: duckdb.DuckDBPyConnection, sql: str):
    return con.execute(sql).fetchdf()


def show(title: str, frame, max_rows: int = 30) -> None:
    print(f"\n## {title}")
    if frame.empty:
        print("(empty)")
    else:
        print(frame.head(max_rows).to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit parse quality beyond coverage.")
    parser.add_argument("--db", default="legal_sample_200.duckdb")
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    con = duckdb.connect(str(db_path))

    docs = df(
        con,
        """
        SELECT doc_id, so_ky_hieu, loai_van_ban, co_quan, trich_yeu,
               ngay_ban_hanh, nguoi_ky
        FROM documents
        ORDER BY doc_id
        """,
    )

    suspicious = []
    for row in docs.to_dict("records"):
        reasons = []
        co_quan = str(row.get("co_quan") or "")
        trich_yeu = str(row.get("trich_yeu") or "")
        loai = str(row.get("loai_van_ban") or "")
        if not row.get("loai_van_ban"):
            reasons.append("missing_loai_van_ban")
        if not row.get("so_ky_hieu"):
            reasons.append("missing_so_ky_hieu")
        if not row.get("co_quan"):
            reasons.append("missing_co_quan")
        if DOC_TYPE_RE.search(co_quan) and not AUTHORITY_HINT_RE.search(co_quan):
            reasons.append("co_quan_looks_like_title")
        if len(co_quan) > 140:
            reasons.append("co_quan_too_long")
        if not trich_yeu:
            reasons.append("missing_trich_yeu")
        if len(loai) > 40:
            reasons.append("loai_van_ban_too_long")
        if reasons:
            suspicious.append({**row, "reasons": ",".join(reasons)})

    show("Suspicious Documents", duckdb.sql("SELECT * FROM suspicious").df() if False else __import__("pandas").DataFrame(suspicious), args.limit)

    show(
        "Parse Quality Summary",
        df(
            con,
            """
            SELECT parse_status, count(1) AS n,
                   min(coverage_ratio) AS min_coverage,
                   avg(coverage_ratio) AS avg_coverage,
                   max(n_orphan_body_lines) AS max_orphan_lines
            FROM parse_quality_reports
            GROUP BY parse_status
            ORDER BY parse_status
            """,
        ),
    )

    show(
        "Header Lines For Suspicious Docs",
        df(
            con,
            f"""
            SELECT l.doc_id, l.line_no, l.section, left(l.raw_text, 220) AS raw_text
            FROM document_lines l
            WHERE l.doc_id IN (
              SELECT doc_id FROM documents
              WHERE co_quan IS NULL
                 OR length(co_quan) > 140
                 OR trich_yeu IS NULL
              ORDER BY doc_id
              LIMIT {args.limit}
            )
            AND l.line_no <= 35
            ORDER BY l.doc_id, l.line_no
            """,
        ),
        args.limit * 8,
    )

    show(
        "Provision Level Counts",
        df(
            con,
            """
            SELECT level, count(1) AS n
            FROM provisions
            GROUP BY level
            ORDER BY n DESC
            """,
        ),
    )

    show(
        "Documents With Duplicate Legal Paths",
        df(
            con,
            """
            SELECT doc_id, count(1) AS duplicate_path_groups, sum(n) AS duplicated_nodes
            FROM (
              SELECT doc_id, legal_path, count(1) AS n
              FROM provisions
              GROUP BY doc_id, legal_path
              HAVING count(1) > 1
            )
            GROUP BY doc_id
            ORDER BY duplicated_nodes DESC
            LIMIT 20
            """,
        ),
    )

    show(
        "Appendix Heavy Docs",
        df(
            con,
            """
            SELECT doc_id, count(1) AS appendix_blocks
            FROM appendix_blocks
            GROUP BY doc_id
            ORDER BY appendix_blocks DESC
            LIMIT 20
            """,
        ),
    )


if __name__ == "__main__":
    main()
