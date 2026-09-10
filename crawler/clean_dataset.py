"""
Vietnamese Legal Documents - Comprehensive Data Cleaning and Processing Engine.

This script cleans metadata, extracts clean plain-text/markdown from HTML,
parses legal documents into article-level structural chunks for RAG,
and standardizes relationship taxonomies.
"""

from __future__ import annotations

import argparse
import html
from datetime import datetime
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def normalize_unicode_nfc(val: Any) -> Any:
    """Normalize string value to canonical NFC Unicode and strip surrounding space."""
    if not isinstance(val, str):
        return val
    val = unicodedata.normalize('NFC', val)
    val = val.replace('\xa0', ' ').replace('&nbsp;', ' ')
    val = re.sub(r'\s+', ' ', val).strip()
    return val if val != '' and val != '...' else None


def parse_vietnamese_date(val: Any) -> Optional[str]:
    """Parse DD/MM/YYYY text into YYYY-MM-DD ISO date string."""
    if not isinstance(val, str) or val in ('...', '', 'None'):
        return None
    val = val.strip()
    match = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', val)
    if match:
        day, month, year = match.groups()
        day_i, month_i, year_i = int(day), int(month), int(year)
        if 1900 <= year_i <= 2100:
            try:
                parsed = datetime(year_i, month_i, day_i)
            except ValueError:
                return None
            return parsed.strftime("%Y-%m-%d")
    return None


def clean_html_to_text(html_str: str) -> str:
    """Extract clean plain text from raw HTML body."""
    if not isinstance(html_str, str) or not html_str.strip():
        return ""
    
    # 1. Normalize unicode first
    text = unicodedata.normalize('NFC', html_str)
    
    # 2. Remove script, style, and comments
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    
    # 3. Replace block breaks with newlines
    text = re.sub(r'</?(p|br|div|tr|h[1-6]|li)\b[^>]*>', '\n', text, flags=re.IGNORECASE)
    
    # 4. Strip remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # 5. Decode HTML entities
    text = html.unescape(text).replace('\xa0', ' ')
    
    # 6. Normalize paragraph newlines & blank lines
    lines = [line.strip() for line in text.splitlines()]
    non_empty_lines = [line for line in lines if line]
    clean_text = '\n'.join(non_empty_lines)
    
    return clean_text


def extract_articles_from_text(doc_id: str, clean_text: str) -> List[Dict[str, Any]]:
    """Parse text into discrete Article chunks (Điều 1, Điều 2, etc.) for RAG."""
    if not clean_text:
        return []
    
    # Regex to find "Điều 1.", "Điều 2:", "Điều 10.-" allowing optional leading whitespace
    article_pattern = re.compile(r'(?m)^\s*(Điều\s+\d+[\.\:\-\s][^\n]*)', re.IGNORECASE)
    matches = list(article_pattern.finditer(clean_text))
    
    if not matches:
        return []
    
    articles = []
    for i, match in enumerate(matches):
        start_idx = match.start()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(clean_text)
        
        header = match.group(1).strip()
        full_article_text = clean_text[start_idx:end_idx].strip()
        
        # Extract article number
        num_match = re.search(r'Điều\s+(\d+)', header, re.IGNORECASE)
        article_num = int(num_match.group(1)) if num_match else i + 1
        
        articles.append({
            "doc_id": doc_id,
            "article_number": article_num,
            "article_header": header,
            "article_text": full_article_text
        })
        
    return articles


def categorize_relationship(rel_str: str) -> str:
    """Map raw relationship text into a canonical taxonomy code distinguishing active vs passive roles."""
    if not isinstance(rel_str, str):
        return 'KHAC'
    rel = unicodedata.normalize('NFC', rel_str).strip().lower()
    
    if 'quy định hết hiệu lực 1 phần' in rel:
        return 'QUY_DINH_HET_HIEU_LUC_1_PHAN'
    elif 'bị hết hiệu lực 1 phần' in rel:
        return 'BI_HET_HIEU_LUC_1_PHAN'
    elif 'quy định hết hiệu lực' in rel:
        return 'QUY_DINH_HET_HIEU_LUC'
    elif 'bãi bỏ' in rel or rel == 'văn bản hết hiệu lực':
        return 'BAI_BO'
    elif 'thay thế' in rel:
        return 'THAY_THE'
    elif rel == 'văn bản sửa đổi':
        return 'DUOC_SUA_DOI'
    elif rel == 'văn bản bổ sung':
        return 'DUOC_BO_SUNG'
    elif 'sửa đổi' in rel or 'bổ sung' in rel:
        return 'SUA_DOI_BO_SUNG'
    elif rel == 'văn bản hd, qđ chi tiết':
        return 'DUOC_HUONG_DAN_CHI_TIET'
    elif 'hướng dẫn' in rel or 'chi tiết' in rel:
        return 'HUONG_DAN_CHI_TIET'
    elif rel == 'văn bản căn cứ':
        return 'LA_CAN_CU_CHO'
    elif 'căn cứ' in rel:
        return 'CAN_CU'
    elif rel == 'văn bản dẫn chiếu':
        return 'DUOC_DAN_CHIEU'
    elif 'dẫn chiếu' in rel:
        return 'DAN_CHIEU'
    elif 'hợp nhất' in rel:
        return 'HOP_NHAT'
    elif 'đính chính' in rel:
        return 'DINH_CHINH'
    elif 'tạm ngưng' in rel:
        return 'TAM_NGUNG_HIEU_LUC'
    elif 'bị đình chỉ' in rel:
        return 'BI_DINH_CHI'
    elif 'đình chỉ' in rel:
        return 'DINH_CHI_THI_HANH'
    elif 'giải thích' in rel:
        return 'GIAI_THICH'
    elif 'bản dịch' in rel:
        return 'BAN_DICH'
    else:
        return 'KHAC'




def process_metadata(input_file: Path) -> pd.DataFrame:
    print(f"Reading metadata from {input_file}...")
    df = pd.read_parquet(input_file)
    original_rows = len(df)
    
    # 1. Drop 100% empty column thong_tin_ap_dung if present
    if 'thong_tin_ap_dung' in df.columns:
        df = df.drop(columns=['thong_tin_ap_dung'])
    
    # 2. Apply Unicode NFC normalization and placeholder removal across string columns
    str_cols = df.select_dtypes(include=['object', 'string']).columns
    for col in str_cols:
        df[col] = df[col].apply(normalize_unicode_nfc)
        
    # 3. Parse date fields into ISO YYYY-MM-DD
    date_fields = ['ngay_ban_hanh', 'ngay_co_hieu_luc', 'ngay_het_hieu_luc', 'ngay_dang_cong_bao']
    for field in date_fields:
        if field in df.columns:
            df[f'{field}_iso'] = df[field].apply(parse_vietnamese_date)
            
    # 4. Impute missing effect status (tinh_trang_hieu_luc)
    if 'tinh_trang_hieu_luc' not in df.columns:
        df['tinh_trang_hieu_luc'] = pd.NA
    missing_status = df['tinh_trang_hieu_luc'].isna()
    today_str = pd.Timestamp.now().strftime('%Y-%m-%d')
    if 'ngay_het_hieu_luc_iso' in df.columns:
        expired_mask = df['ngay_het_hieu_luc_iso'].notna() & (df['ngay_het_hieu_luc_iso'] <= today_str)
    else:
        expired_mask = pd.Series(False, index=df.index)
    df.loc[missing_status & expired_mask, 'tinh_trang_hieu_luc'] = 'Hết hiệu lực toàn bộ'
    df['tinh_trang_hieu_luc'] = df['tinh_trang_hieu_luc'].fillna('Chưa xác định')
    
    print(f"Cleaned metadata: {len(df)} rows preserved ({original_rows - len(df)} removed).")
    return df


def process_content_and_articles(input_file: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    print(f"Reading content from {input_file}...")
    df_content = pd.read_parquet(input_file)
    
    print("Normalizing HTML and extracting clean text...")
    df_content['id'] = df_content['id'].astype(str)
    df_content['content_html'] = df_content['content_html'].apply(lambda x: x if isinstance(x, str) else "")
    df_content['content_text'] = df_content['content_html'].apply(clean_html_to_text)
    df_content['content_html'] = df_content['content_html'].apply(lambda x: unicodedata.normalize('NFC', x))
    
    print("Parsing legal articles for chunked RAG dataset...")
    all_articles = []
    for doc_id, text in zip(df_content['id'], df_content['content_text']):
        articles = extract_articles_from_text(doc_id, text)
        all_articles.extend(articles)
        
    df_articles = pd.DataFrame(all_articles)
    if df_articles.empty:
        df_articles = pd.DataFrame(columns=["doc_id", "article_number", "article_header", "article_text"])
        
    print(f"Content cleaned: {len(df_content)} docs. Extracted {len(df_articles)} structured articles.")
    return df_content, df_articles


def process_relationships(input_file: Path, valid_meta_ids: set) -> pd.DataFrame:
    print(f"Reading relationships from {input_file}...")
    df = pd.read_parquet(input_file)
    
    df['doc_id'] = df['doc_id'].astype(str)
    df['other_doc_id'] = df['other_doc_id'].astype(str)
    df['relationship'] = df['relationship'].apply(normalize_unicode_nfc)
    df['relationship_canonical'] = df['relationship'].apply(categorize_relationship)
    df['target_exists'] = df['other_doc_id'].isin(valid_meta_ids)
    
    # Deduplicate relationships
    original_cnt = len(df)
    df = df.drop_duplicates(subset=['doc_id', 'other_doc_id', 'relationship'])
    print(f"Relationships cleaned: {len(df)} rows ({original_cnt - len(df)} duplicate pairs removed).")
    return df


def clean_dataset(input_dir: Path, output_dir: Path) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    
    meta_path = input_dir / "metadata.parquet"
    content_path = input_dir / "content.parquet"
    rel_path = input_dir / "relationships.parquet"
    
    if not meta_path.exists() or not content_path.exists() or not rel_path.exists():
        raise FileNotFoundError(f"Required parquet files missing in input directory: {input_dir}")
        
    # Process metadata
    df_meta = process_metadata(meta_path)
    clean_meta_path = output_dir / "metadata.parquet"
    df_meta.to_parquet(clean_meta_path, index=False, compression="zstd")
    
    # Process content and articles
    valid_ids = set(df_meta['id'].dropna().astype(str))
    df_content, df_articles = process_content_and_articles(content_path)
    
    clean_content_path = output_dir / "content.parquet"
    df_content.to_parquet(clean_content_path, index=False, compression="zstd")
    
    clean_articles_path = output_dir / "content_articles.parquet"
    df_articles.to_parquet(clean_articles_path, index=False, compression="zstd")
    
    # Process relationships
    df_rels = process_relationships(rel_path, valid_ids)
    clean_rel_path = output_dir / "relationships.parquet"
    df_rels.to_parquet(clean_rel_path, index=False, compression="zstd")
    
    summary = {
        "metadata_rows": len(df_meta),
        "content_rows": len(df_content),
        "extracted_articles_rows": len(df_articles),
        "relationships_rows": len(df_rels),
        "dangling_relationship_targets": int((~df_rels['target_exists']).sum())
    }
    return summary


def main():
    parser = argparse.ArgumentParser(description="Clean and process Vietnamese legal document datasets.")
    parser.add_argument("--input-dir", type=Path, default=Path("../data"))
    parser.add_argument("--output-dir", type=Path, default=Path("../data_clean"))
    args = parser.parse_args()
    
    print(f"Starting dataset cleaning execution...")
    print(f"Input Directory: {args.input_dir.resolve()}")
    print(f"Output Directory: {args.output_dir.resolve()}")
    
    stats = clean_dataset(args.input_dir, args.output_dir)
    print("\nDataset Cleaning Summary:")
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
