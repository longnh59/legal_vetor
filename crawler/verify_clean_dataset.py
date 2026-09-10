"""
Verification script for evaluating cleaned dataset artifacts in data_clean.
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path
import pandas as pd


def verify_cleaned_dataset(data_clean_dir: Path) -> bool:
    print(f"\n==========================================")
    print(f"VERIFYING CLEANED DATASET AT: {data_clean_dir.resolve()}")
    print(f"==========================================")
    
    meta_path = data_clean_dir / "metadata.parquet"
    content_path = data_clean_dir / "content.parquet"
    articles_path = data_clean_dir / "content_articles.parquet"
    rel_path = data_clean_dir / "relationships.parquet"
    
    assert meta_path.exists(), f"Missing {meta_path}"
    assert content_path.exists(), f"Missing {content_path}"
    assert articles_path.exists(), f"Missing {articles_path}"
    assert rel_path.exists(), f"Missing {rel_path}"
    
    df_meta = pd.read_parquet(meta_path)
    df_content = pd.read_parquet(content_path)
    df_articles = pd.read_parquet(articles_path)
    df_rels = pd.read_parquet(rel_path)
    
    print(f"\n1. Metadata Statistics:")
    print(f"   - Total rows: {len(df_meta):,}")
    print(f"   - Columns ({len(df_meta.columns)}): {list(df_meta.columns)}")
    assert 'thong_tin_ap_dung' not in df_meta.columns, "thong_tin_ap_dung was not dropped!"
    
    # 1. NFD Check
    nfd_count = 0
    for col in ['title', 'co_quan_ban_hanh', 'nguoi_ky']:
        non_nulls = df_meta[col].dropna()
        is_nfd = non_nulls.apply(lambda s: s != unicodedata.normalize('NFC', s))
        nfd_count += is_nfd.sum()
    print(f"   - NFD Decomposed strings remaining: {nfd_count} (Expected: 0)")
    assert nfd_count == 0, f"Found {nfd_count} NFD strings in metadata!"
    
    # 2. Dots Placeholder Check
    dots_count = 0
    for col in ['ngay_ban_hanh', 'ngay_co_hieu_luc', 'ngay_het_hieu_luc', 'ngay_dang_cong_bao']:
        dots = (df_meta[col] == '...').sum()
        dots_count += dots
    print(f"   - Literal '...' placeholders remaining in date cols: {dots_count} (Expected: 0)")
    assert dots_count == 0, f"Found {dots_count} literal dots in date columns!"
    
    # 3. ISO Date Statistics
    print(f"\n2. ISO Date Fields Parsed:")
    for date_col in ['ngay_ban_hanh_iso', 'ngay_co_hieu_luc_iso', 'ngay_het_hieu_luc_iso', 'ngay_dang_cong_bao_iso']:
        valid_iso = df_meta[date_col].notna().sum()
        print(f"   - {date_col}: {valid_iso:,} valid ISO dates parsed")
        
    # 4. Content & Articles Verification
    print(f"\n3. Text & Article Chunking:")
    print(f"   - Total HTML documents: {len(df_content):,}")
    non_empty_text = (df_content['content_text'].str.strip() != '').sum()
    print(f"   - Non-empty extracted text rows: {non_empty_text:,}")
    print(f"   - Total extracted legal articles: {len(df_articles):,}")
    assert len(df_articles) > 0, "No articles extracted!"
    
    # 5. Relationships Verification
    print(f"\n4. Relationships:")
    print(f"   - Total unique relationship pairs: {len(df_rels):,}")
    print(f"   - Relationship taxonomy distribution:")
    for cat, count in df_rels['relationship_canonical'].value_counts().items():
        print(f"     * {cat}: {count:,}")
    dangling = (~df_rels['target_exists']).sum()
    print(f"   - Dangling reference targets: {dangling:,} out of {len(df_rels):,}")
    
    print(f"\n==========================================")
    print(f"ALL DATASET VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print(f"==========================================\n")
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("../data_clean"))
    args = parser.parse_args()
    verify_cleaned_dataset(args.data_dir)
