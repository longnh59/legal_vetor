"""Helpers for the public VBPL JSON API and catalog action."""

import json
import re
from datetime import datetime


BASE_URL = "https://vbpl-bientap-gateway.moj.gov.vn/api"
DOCUMENT_URL_TEMPLATE = f"{BASE_URL}/qtdc/public/doc/{{}}"
CATALOG_URL = "https://vbpl.vn/van-ban/trung-uong"

# The portal keeps catalog search behind a Next.js server action. This value can
# be overridden with ``-a catalog_action_id=...`` after a future deployment.
CATALOG_ACTION_ID = "c529d164f28418e5898a834422629e64c6816af1"


def feed_settings(output_path):
    """Build an explicit single-file Scrapy feed configuration."""
    return {
        output_path: {
            "format": "jsonlines",
            "encoding": "utf-8",
            "overwrite": False,
        }
    }

# Official relationship labels used by the current VBPL frontend.
REFERENCE_TYPES = {
    1: "Bãi bỏ",
    2: "Bản dịch",
    3: "Căn cứ",
    4: "Dẫn chiếu",
    5: "Đình chỉ thi hành",
    6: "Đính chính",
    7: "Hợp nhất",
    8: "Hướng dẫn áp dụng",
    9: "Quy định chi tiết, hướng dẫn thi hành",
    10: "Sửa đổi, bổ sung",
    11: "Tạm ngưng hiệu lực",
    12: "Thay thế",
    13: "Bổ sung",
    14: "Giải thích",
    15: "Công bố",
}


def unwrap_document(payload):
    """Return document data from a successful gateway response."""
    if not isinstance(payload, dict) or payload.get("success") is not True:
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def format_date(value):
    """Convert an API ISO datetime to the dataset's DD/MM/YYYY format."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return value


def join_unique(values):
    """Join non-empty values while preserving their original order."""
    unique = list(dict.fromkeys(filter(None, values)))
    return ", ".join(unique) if unique else None



def catalog_body(page_number, page_size):
    """Build the argument array expected by the portal's catalog action."""
    return json.dumps(
        [{"pageNumber": page_number, "pageSize": page_size}],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def unwrap_catalog(response_text):
    """Extract catalog JSON from a Next.js React Server Components response."""
    decoder = json.JSONDecoder()
    # Large RSC strings use length-prefixed chunks, so the following JSON chunk
    # is not necessarily line-aligned (for example ``...title1:{...}``).
    for marker in re.finditer(r"[0-9a-f]+:(?=\{)", response_text):
        try:
            payload, _ = decoder.raw_decode(response_text, marker.end())
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            return payload
    return None
