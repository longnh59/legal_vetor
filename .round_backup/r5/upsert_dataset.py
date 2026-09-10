"""Merge a verified VBPL refresh into the published Parquet datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.compute as pc
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
)
RELATIONSHIP_PAIR = ("doc_id", "other_doc_id")


def string_columns(fields: tuple[str, ...]) -> list[pl.Expr]:
    return [pl.col(field).cast(pl.String, strict=False) for field in fields]


def write_huggingface_parquet(
    frame: pl.LazyFrame,
    output_path: Path,
    fields: tuple[str, ...],
    batch_size: int = 5_000,
) -> None:
    """Write bounded Arrow string row groups that ``datasets`` can load."""
    table = frame.collect().to_arrow()
    schema = pa.schema([(field, pa.string()) for field in fields])
    clean_table = pa.Table.from_arrays(
        [pc.cast(table.column(field), pa.string()) for field in fields],
        schema=schema,
    )
    pq.write_table(clean_table, output_path, compression="zstd", row_group_size=batch_size)



def upsert_metadata(current_dir: Path, refresh_dir: Path, output_dir: Path) -> None:
    current = (
        pl.scan_parquet(current_dir / "metadata.parquet")
        .select(string_columns(METADATA_FIELDS))
        .unique("id", keep="last")
    )
    refresh = (
        pl.scan_parquet(refresh_dir / "metadata.parquet")
        .select(string_columns(METADATA_FIELDS))
        .unique("id", keep="last")
    )

    current_values = current.rename(
        {field: f"{field}_current" for field in METADATA_FIELDS if field != "id"}
    )
    joined = refresh.join(current_values, on="id", how="left")
    merged_refresh = joined.select(
        pl.col("id"),
        *[
            pl.when(pl.col(field).is_null() | (pl.col(field).str.strip_chars() == ""))
            .then(pl.col(f"{field}_current"))
            .otherwise(pl.col(field))
            .alias(field)
            for field in METADATA_FIELDS
            if field != "id"
        ],
    )
    current_only = current.join(refresh.select("id"), on="id", how="anti")
    write_huggingface_parquet(
        pl.concat([merged_refresh, current_only], how="vertical"),
        output_dir / "metadata.parquet",
        METADATA_FIELDS,
    )


def upsert_content(current_dir: Path, refresh_dir: Path, output_dir: Path) -> None:
    current = (
        pl.scan_parquet(current_dir / "content.parquet")
        .select(pl.col("id").cast(pl.String), pl.col("content_html"))
        .unique("id", keep="last")
    )
    refresh = (
        pl.scan_parquet(refresh_dir / "content.parquet")
        .select(pl.col("id").cast(pl.String), pl.col("content_html"))
        .unique("id", keep="last")
    )
    current_only = current.join(refresh.select("id"), on="id", how="anti")
    write_huggingface_parquet(
        pl.concat([refresh, current_only], how="vertical"),
        output_dir / "content.parquet",
        ("id", "content_html"),
    )


def upsert_relationships(
    current_dir: Path, refresh_dir: Path, output_dir: Path
) -> None:
    columns = ("doc_id", "other_doc_id", "relationship")
    current = (
        pl.scan_parquet(current_dir / "relationships.parquet")
        .select(string_columns(columns))
        .unique(columns)
    )
    refresh = (
        pl.scan_parquet(refresh_dir / "relationships.parquet")
        .select(string_columns(columns))
        .unique(columns)
    )

    # The new portal renamed relationship labels. New edges therefore replace
    # every old label for the same directed document pair. Only pairs absent
    # from the current portal are retained with their historical labels.
    refresh_pairs = refresh.select(RELATIONSHIP_PAIR).unique()
    current_only_pairs = current.join(
        refresh_pairs, on=RELATIONSHIP_PAIR, how="anti"
    )
    write_huggingface_parquet(
        pl.concat([refresh, current_only_pairs], how="vertical").unique(columns),
        output_dir / "relationships.parquet",
        columns,
    )


def row_counts(output_dir: Path) -> dict[str, int]:
    return {
        name: pl.scan_parquet(output_dir / f"{name}.parquet")
        .select(pl.len())
        .collect()
        .item()
        for name in ("metadata", "content", "relationships")
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("refresh_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--current-dir", type=Path, default=Path("../data"))
    args = parser.parse_args()

    if args.output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite {args.output_dir}")
    args.output_dir.mkdir(parents=True)

    upsert_metadata(args.current_dir, args.refresh_dir, args.output_dir)
    upsert_content(args.current_dir, args.refresh_dir, args.output_dir)
    upsert_relationships(args.current_dir, args.refresh_dir, args.output_dir)
    print(json.dumps(row_counts(args.output_dir), indent=2))


if __name__ == "__main__":
    main()
