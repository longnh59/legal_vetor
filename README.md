---
language:
- vi
license: cc-by-4.0
pretty_name: Vietnamese Legal Documents
size_categories:
- 100K<n<1M
task_categories:
- text-classification
- text-generation
- question-answering
- summarization
tags:
- legal
- vietnamese
- law
- government
- NLP
- text-mining
configs:
- config_name: metadata
  data_files:
  - split: data
    path: metadata/data-*.parquet
- config_name: content
  data_files:
  - split: data
    path: content/data-*.parquet
dataset_info:
- config_name: metadata
  features:
  - name: id
    dtype: int64
  - name: document_number
    dtype: string
  - name: title
    dtype: string
  - name: url
    dtype: string
  - name: legal_type
    dtype: string
  - name: legal_sectors
    dtype: string
  - name: issuing_authority
    dtype: string
  - name: issuance_date
    dtype: string
  - name: signers
    dtype: string
  num_rows: 518255
- config_name: content
  features:
  - name: id
    dtype: int64
  - name: content
    dtype: string
  num_rows: 518255
---

# Vietnamese Legal Documents

A comprehensive dataset of **518,255 Vietnamese legal documents** sourced from
[thuvienphapluat.vn](https://thuvienphapluat.vn) — the largest Vietnamese legal
document repository. The dataset covers laws, decrees, circulars, decisions, and
other official documents issued by Vietnamese government bodies, spanning from
**1924 to 2026**.

---

## At a Glance

| | |
|---|---|
| 🗂️ **Total documents** | 518,255 |
| 📅 **Date range** | 1924 – 2026 |
| 🏛️ **Issuing authorities** | 1,335 unique bodies |
| 📋 **Document types** | 36 unique types |
| 🌐 **Language** | Vietnamese |
| 💾 **Content size** | ~3.6 GB (parquet) |

---

## Dataset Structure

This dataset is split into **two configs** to allow fast metadata access without loading the full text.

| Config | Split | Rows | Size | Description |
|---|---|---|---|---|
| `metadata` | `data` | 518,255 | ~82 MB | 9 metadata columns, no text content |
| `content` | `data` | 518,255 | ~3.6 GB | `id` + full markdown document text |

Join on the `id` column to get both metadata and content.

---

## Load the Dataset

```python
from datasets import load_dataset

# Load metadata only (fast, ~82 MB)
ds = load_dataset("th1nhng0/vietnamese-legal-documents", "metadata")
df = ds["data"].to_pandas()
print(df.head())

# Load full text content (~3.6 GB)
ds_content = load_dataset("th1nhng0/vietnamese-legal-documents", "content")

# Join metadata + content
import pandas as pd
meta = load_dataset("th1nhng0/vietnamese-legal-documents", "metadata")["data"].to_pandas()
text = load_dataset("th1nhng0/vietnamese-legal-documents", "content")["data"].to_pandas()
df = meta.merge(text, on="id")
print(df.columns.tolist())
```

---

## Schema

### `metadata` config

| Column | Type | Description |
|---|---|---|
| `id` | int64 | Unique numeric document ID |
| `document_number` | string | Official document number (e.g. `115/NQ-HĐBCQG`) |
| `title` | string | Full Vietnamese title |
| `url` | string | Source URL on thuvienphapluat.vn |
| `legal_type` | string | Document type (Quyết định, Công văn, Nghị quyết, …) |
| `legal_sectors` | string | Pipe-separated sector/topic tags |
| `issuing_authority` | string | Name of the issuing government body |
| `issuance_date` | string | Issue date in `DD/MM/YYYY` format |
| `signers` | string | Pipe-separated `name:id` pairs of signatories |

### `content` config

| Column | Type | Description |
|---|---|---|
| `id` | int64 | Document ID — join key with the `metadata` config |
| `content` | string | Full document text converted to Markdown |

---

## Statistics

### Documents by Year

![Documents by year](charts/docs_by_year.png)

### Top 15 Document Types

![Document type distribution](charts/legal_type_distribution.png)


### Top 15 Legal Sectors

![Top sectors](charts/top_sectors.png)

---

## Use Cases

- 🔍 **Legal information retrieval** — build search engines over Vietnamese law
- 🤖 **LLM fine-tuning** — train or fine-tune language models on legal Vietnamese
- 📊 **Legal NLP research** — NER, classification, summarization, QA
- 📈 **Policy analysis** — track legislative trends over time
- 🌏 **Low-resource NLP** — Vietnamese legal text is underrepresented in existing datasets

---

## Data Collection

This is an independent personal research project. Documents were collected from
[thuvienphapluat.vn](https://thuvienphapluat.vn) — a public legal document portal
— via their sitemap and mobile API. This project has **no affiliation with
thuvienphapluat.vn**.

HTML content was converted to Markdown using BeautifulSoup. Only Vietnamese-language
documents were retained; English versions and technical standards (Tiêu chuẩn) were
excluded.

---

## License & Legal Basis

Vietnamese legal documents (laws, decrees, circulars, decisions, and other normative
acts) are **public domain by Vietnamese law**. Under the
[Law on Access to Information (Luật Tiếp cận thông tin, No. 104/2016/QH13)](https://thuvienphapluat.vn/van-ban/Bo-may-hanh-chinh/Luat-tiep-can-thong-tin-2016-280116.aspx)
and the [Law on Promulgation of Legal Documents (No. 64/2025/QH15)](https://thuvienphapluat.vn/van-ban/Bo-may-hanh-chinh/Luat-ban-hanh-van-ban-quy-pham-phap-luat-2025-so-64-2025-QH15-639239.aspx),
official legal normative documents issued by state agencies must be made publicly
accessible free of charge.

The **compiled dataset** (collection, processing, metadata schema, and Markdown
conversion) is released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

**Intended for research purposes only.**

---

## Citation

```bibtex
@dataset{ngo_thinh_2026_vietnamese_legal,
  title        = {Vietnamese Legal Documents},
  author       = {Ngô, Thịnh},
  year         = {2026},
  publisher    = {Hugging Face},
  url          = {https://huggingface.co/datasets/th1nhng0/vietnamese-legal-documents},
  note         = {518,255 Vietnamese legal documents compiled for research purposes}
}
```
