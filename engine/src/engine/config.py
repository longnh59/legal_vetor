"""Central place for every tunable threshold and path. No magic numbers elsewhere."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

DATA_DIR = REPO_ROOT / "data"
CONTENT_PARQUET = DATA_DIR / "content.parquet"
METADATA_PARQUET = DATA_DIR / "metadata.parquet"
RELATIONSHIPS_PARQUET = DATA_DIR / "relationships.parquet"

PROFILING_DIR = REPO_ROOT / "profiling"
REPORTS_DIR = REPO_ROOT / "reports"
GOLDEN_DIR = REPO_ROOT / "engine" / "tests" / "golden"

HF_REPO_ID = "th1nhng0/vietnamese-legal-documents"
HF_REPO_TYPE = "dataset"

# --- T0 sample counts expected from the HF dataset card (sanity checks after download) ---
EXPECTED_CONTENT_ROWS = 170_824
EXPECTED_METADATA_ROWS = 171_556
EXPECTED_RELATIONSHIPS_ROWS = 1_033_255

# --- Validator thresholds (P3) ---
CHAR_COVERAGE_CLEAN_MIN = 0.97
CHAR_COVERAGE_WARN_MIN = 0.90

# --- Profiling / sampling (P0) ---
DEV_SAMPLE_SIZE = 5_000
GOLDEN_SET_SIZE = 30

# --- Vietnamese "diem" (a/b/c...) alphabet used by parsers, never f/j/w/z ---
DIEM_ALPHABET = list("abcdđeghiklmnopqrstuvxy")
