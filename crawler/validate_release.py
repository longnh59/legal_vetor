"""Validate the local Hugging Face dataset release before publishing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq
from huggingface_hub import DatasetCard


CONFIG_PATHS = {
    "metadata": ("data/metadata.parquet", "data"),
    "relationships": ("data/relationships.parquet", "data"),
    "content": ("data/content.parquet", "data"),
    "legacy_metadata": ("legacy/metadata.parquet", "metadata"),
    "legacy_content": ("legacy/content.parquet", "content"),
}


def validate(root: Path) -> dict[str, dict[str, int]]:
    card = DatasetCard.load(root / "README.md")
    card.validate()
    metadata = card.data.to_dict()
    infos = {item["config_name"]: item for item in metadata["dataset_info"]}
    configs = {item["config_name"]: item for item in metadata["configs"]}
    assert set(infos) == set(CONFIG_PATHS)
    assert set(configs) == set(CONFIG_PATHS)

    result = {}
    for name, (relative_path, split_name) in CONFIG_PATHS.items():
        path = root / relative_path
        parquet = pq.ParquetFile(path)
        info = infos[name]
        split = next(item for item in info["splits"] if item["name"] == split_name)
        card_path = configs[name]["data_files"][0]["path"]
        feature_types = {
            feature["name"]: feature["dtype"] for feature in info["features"]
        }
        parquet_types = {
            field.name: str(field.type) for field in parquet.schema_arrow
        }
        assert card_path == relative_path
        assert split["num_examples"] == parquet.metadata.num_rows
        assert info["download_size"] == path.stat().st_size
        assert feature_types == parquet_types
        result[name] = {
            "rows": parquet.metadata.num_rows,
            "download_size": path.stat().st_size,
        }
        parquet.close()

    frames = {
        name: pl.scan_parquet(root / relative_path)
        for name, (relative_path, _) in CONFIG_PATHS.items()
        if name in {"metadata", "content", "relationships"}
    }
    metadata_ids = frames["metadata"].select("id")
    content_ids = frames["content"].select("id")
    relationship_sources = frames["relationships"].select(
        pl.col("doc_id").alias("id")
    )
    assert metadata_ids.select(pl.len()).collect().item() == metadata_ids.unique().select(
        pl.len()
    ).collect().item()
    assert content_ids.select(pl.len()).collect().item() == content_ids.unique().select(
        pl.len()
    ).collect().item()
    assert frames["relationships"].select(pl.len()).collect().item() == frames[
        "relationships"
    ].unique().select(pl.len()).collect().item()
    assert content_ids.join(metadata_ids, on="id", how="anti").collect().is_empty()
    assert relationship_sources.join(
        metadata_ids, on="id", how="anti"
    ).collect().is_empty()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, nargs="?", default=Path(".."))
    args = parser.parse_args()
    print(json.dumps(validate(args.root.resolve()), indent=2))


if __name__ == "__main__":
    main()
