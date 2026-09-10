"""Stream a combined VBPL JSONL crawl into versioned Parquet datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


METADATA_FIELDS = (
    "id",
    "title",
    "so_ky_hieu",
    "ngay_ban_hanh",
    "loai_van_ban",
    "ngay_co_hieu_luc",
    "ngay_het_hieu_luc",
    "nguon_thu_thap",
    "ngay_dang_cong_bao",
    "nganh",
    "linh_vuc",
    "co_quan_ban_hanh",
    "chuc_danh",
    "nguoi_ky",
    "pham_vi",
    "thong_tin_ap_dung",
    "tinh_trang_hieu_luc",
    "crawl_status",
)
METADATA_SCHEMA = pa.schema([(field, pa.string()) for field in METADATA_FIELDS])
CONTENT_SCHEMA = pa.schema([("id", pa.string()), ("content_html", pa.string())])
RELATIONSHIP_SCHEMA = pa.schema(
    [
        ("doc_id", pa.string()),
        ("other_doc_id", pa.string()),
        ("relationship", pa.string()),
    ]
)


def flush(writer: pq.ParquetWriter, rows: list[dict], schema: pa.Schema) -> None:
    if rows:
        writer.write_table(pa.Table.from_pylist(rows, schema=schema))
        rows.clear()


def build(input_path: Path, output_dir: Path, batch_size: int) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "metadata": output_dir / "metadata.parquet",
        "content": output_dir / "content.parquet",
        "relationships": output_dir / "relationships.parquet",
    }
    for path in paths.values():
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite {path}")

    counts = {"metadata": 0, "content": 0, "relationships": 0}
    metadata_rows: list[dict] = []
    content_rows: list[dict] = []
    relationship_rows: list[dict] = []

    with (
        pq.ParquetWriter(paths["metadata"], METADATA_SCHEMA, compression="zstd") as metadata_writer,
        pq.ParquetWriter(paths["content"], CONTENT_SCHEMA, compression="zstd") as content_writer,
        pq.ParquetWriter(
            paths["relationships"], RELATIONSHIP_SCHEMA, compression="zstd"
        ) as relationship_writer,
        input_path.open("r", encoding="utf-8") as source,
    ):
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}") from exc

            item["id"] = str(item["id"])
            metadata_rows.append({field: item.get(field) for field in METADATA_FIELDS})
            counts["metadata"] += 1

            content = item.get("content")
            if isinstance(content, str) and content.strip():
                content_rows.append({"id": item["id"], "content_html": content})
                counts["content"] += 1

            for relationship, other_ids in (item.get("relationships") or {}).items():
                for other_id in other_ids or ():
                    relationship_rows.append(
                        {
                            "doc_id": item["id"],
                            "other_doc_id": str(other_id),
                            "relationship": relationship,
                        }
                    )
                    counts["relationships"] += 1

            if len(metadata_rows) >= batch_size:
                flush(metadata_writer, metadata_rows, METADATA_SCHEMA)
                flush(content_writer, content_rows, CONTENT_SCHEMA)
                flush(relationship_writer, relationship_rows, RELATIONSHIP_SCHEMA)

        flush(metadata_writer, metadata_rows, METADATA_SCHEMA)
        flush(content_writer, content_rows, CONTENT_SCHEMA)
        flush(relationship_writer, relationship_rows, RELATIONSHIP_SCHEMA)

    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--batch-size", type=int, default=5_000)
    args = parser.parse_args()
    print(json.dumps(build(args.input, args.output_dir, args.batch_size), indent=2))


if __name__ == "__main__":
    main()
