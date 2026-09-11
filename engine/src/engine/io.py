"""Parquet access for the `data/` split. Streams content in batches - it is too large
(170k rows, some up to ~600KB of HTML each) to hold fully in memory at once.
"""

from collections.abc import Iterator
from typing import Any

import pyarrow.dataset as ds
import pyarrow.parquet as pq

from engine.config import CONTENT_PARQUET, METADATA_PARQUET, RELATIONSHIPS_PARQUET


def iter_content_rows(batch_size: int = 500) -> Iterator[dict[str, Any]]:
    """Yield {"id": str, "content_html": str} for every row in content.parquet."""
    parquet_file = pq.ParquetFile(CONTENT_PARQUET)
    for batch in parquet_file.iter_batches(batch_size=batch_size):
        yield from batch.to_pylist()


def load_metadata_rows() -> list[dict[str, Any]]:
    """Metadata is small enough (171k rows x 16 string cols) to load fully."""
    table = pq.read_table(METADATA_PARQUET)
    return table.to_pylist()


def metadata_by_id() -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in load_metadata_rows()}


def load_relationships_rows() -> list[dict[str, Any]]:
    table = pq.read_table(RELATIONSHIPS_PARQUET)
    return table.to_pylist()


def get_content_by_id(doc_id: str) -> dict[str, Any] | None:
    dataset = ds.dataset(CONTENT_PARQUET, format="parquet")
    table = dataset.to_table(filter=ds.field("id") == doc_id)
    rows = table.to_pylist()
    return rows[0] if rows else None


def get_metadata_by_id(doc_id: str) -> dict[str, Any] | None:
    dataset = ds.dataset(METADATA_PARQUET, format="parquet")
    table = dataset.to_table(filter=ds.field("id") == doc_id)
    rows = table.to_pylist()
    return rows[0] if rows else None


def count_rows(path) -> int:
    return pq.ParquetFile(path).metadata.num_rows
