"""One-time fetch of the correct `data/` (vbpl.vn, HTML) split from Hugging Face.

Do not confuse with the `legacy/` split already vendored in the repo's `content/` and
`metadata/` folders (plain text, wrong corpus for this engine) - see PLAN_v2 section 2.
"""

import shutil

from huggingface_hub import hf_hub_download

from engine.config import DATA_DIR, HF_REPO_ID, HF_REPO_TYPE


FILES = ["content.parquet", "metadata.parquet", "relationships.parquet"]


def download_all() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        cached_path = hf_hub_download(
            HF_REPO_ID, f"data/{name}", repo_type=HF_REPO_TYPE
        )
        dest = DATA_DIR / name
        shutil.copy(cached_path, dest)
        size_mb = dest.stat().st_size // 10**6
        print(f"OK {name} {size_mb} MB -> {dest}")


if __name__ == "__main__":
    download_all()
