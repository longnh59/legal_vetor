import json
import math
from collections import defaultdict
from pathlib import Path

import scrapy

from vbpl.api import (
    CATALOG_ACTION_ID,
    CATALOG_URL,
    DOCUMENT_URL_TEMPLATE,
    REFERENCE_TYPES,
    catalog_body,
    feed_settings,
    format_date,
    join_unique,
    unwrap_catalog,
    unwrap_document,
)


class VbplSpider(scrapy.Spider):
    """Crawl VBPL metadata and relationships from seed document IDs."""

    name = "vbpl"

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        proxy_file = kwargs.get("proxy_file")
        output = kwargs.get("output")
        if output:
            crawler.settings.set("FEEDS", feed_settings(output), priority="spider")
        if proxy_file:
            crawler.settings.set("PROXY_LIST_FILE", proxy_file, priority="spider")
        else:
            middlewares = dict(crawler.settings.getwithbase("DOWNLOADER_MIDDLEWARES"))
            middlewares.pop("vbpl.middlewares.RotatingProxyMiddleware", None)
            crawler.settings.set(
                "DOWNLOADER_MIDDLEWARES", middlewares, priority="spider"
            )
        return super().from_crawler(crawler, *args, **kwargs)

    def __init__(
        self,
        seed_ids="1",
        seed_file=None,
        proxy_file=None,
        resume=0,
        resume_from="data.jsonl",
        full=0,
        page_size=100,
        max_pages=0,
        catalog_action_id=CATALOG_ACTION_ID,
        output=None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.proxy_file = proxy_file
        self.full = bool(int(full))
        self.page_size = int(page_size)
        self.max_pages = int(max_pages)
        self.catalog_action_id = catalog_action_id
        self.output = output
        if seed_file:
            self.seed_ids = [
                line.strip()
                for line in Path(seed_file).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:
            self.seed_ids = [item_id.strip() for item_id in str(seed_ids).split(",")]

        self.seen_ids = set()
        if int(resume):
            resume_path = Path(resume_from)
            if resume_path.exists():
                with resume_path.open(encoding="utf-8") as source:
                    for line in source:
                        try:
                            item = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if "id" in item:
                            self.seen_ids.add(str(item["id"]))
                self.logger.info(
                    "Resume mode: loaded %d already-scraped IDs from %s",
                    len(self.seen_ids),
                    resume_from,
                )

    async def start(self):
        if self.full:
            yield self._catalog_request(1)
            return
        for item_id in self.seed_ids:
            request = self._request_if_new(item_id)
            if request:
                yield request

    def _catalog_request(self, page_number):
        return scrapy.Request(
            CATALOG_URL,
            method="POST",
            body=catalog_body(page_number, self.page_size),
            callback=self.parse_catalog,
            cb_kwargs={"page_number": page_number},
            headers={
                "Accept": "text/x-component",
                "Content-Type": "text/plain;charset=UTF-8",
                "Next-Action": self.catalog_action_id,
                "Origin": "https://vbpl.vn",
                "Referer": CATALOG_URL,
            },
        )

    def parse_catalog(self, response, page_number):
        catalog = unwrap_catalog(response.text)
        if not catalog:
            retry_times = response.meta.get("invalid_response_retries", 0)
            if retry_times < 3:
                self.logger.warning(
                    "Retrying invalid catalog page %d (%d/3)",
                    page_number,
                    retry_times + 1,
                )
                yield response.request.replace(
                    dont_filter=True,
                    meta={**response.meta, "invalid_response_retries": retry_times + 1},
                )
                return
            self.logger.error(
                "Could not parse catalog page %d after 3 retries. "
                "The catalog action ID may have changed.",
                page_number,
            )
            return

        if page_number == 1:
            total = int(catalog.get("total") or 0)
            total_page_count = math.ceil(total / self.page_size)
            page_count = total_page_count
            if self.max_pages:
                page_count = min(page_count, self.max_pages)
            self.logger.info(
                "Full crawl discovered %d documents; scheduling %d of %d catalog pages",
                total,
                page_count,
                total_page_count,
            )
            for next_page in range(2, page_count + 1):
                yield self._catalog_request(next_page)

        for item in catalog["items"]:
            request = self._request_if_new(item.get("id"), catalog_item=item)
            if request:
                yield request

    def _request_if_new(self, item_id, catalog_item=None):
        item_id = str(item_id)
        if not item_id or item_id in self.seen_ids:
            return None
        self.seen_ids.add(item_id)
        return scrapy.Request(
            DOCUMENT_URL_TEMPLATE.format(item_id),
            callback=self.parse_document,
            cb_kwargs={"doc_id": item_id, "catalog_item": catalog_item},
            headers={"Accept": "application/json", "Referer": "https://vbpl.vn/"},
            meta={"handle_httpstatus_all": True},
        )

    def parse_document(self, response, doc_id, catalog_item=None):
        """Extract one API document and follow its linked document IDs."""
        if response.status >= 400:
            if catalog_item:
                yield self._catalog_fallback(
                    catalog_item, f"catalog_only_http_{response.status}"
                )
            else:
                self.logger.error("Skipping %s after HTTP %d", doc_id, response.status)
            return

        try:
            document = unwrap_document(response.json())
        except ValueError:
            document = None

        if not document:
            retry_times = response.meta.get("invalid_response_retries", 0)
            if retry_times < 3:
                self.logger.warning(
                    "Retrying invalid document %s (%d/3)", doc_id, retry_times + 1
                )
                yield response.request.replace(
                    dont_filter=True,
                    meta={**response.meta, "invalid_response_retries": retry_times + 1},
                )
                return
            self.logger.error("Skipping %s after 3 invalid API responses", doc_id)
            if catalog_item:
                yield self._catalog_fallback(catalog_item, "catalog_only_invalid_detail")
            return

        issues = document.get("documentIssues") or []
        majors = document.get("documentMajors") or []
        fields = document.get("documentFields") or []
        references = document.get("references") or []

        relationships = defaultdict(list)
        linked_ids = []
        for reference in references:
            target = reference.get("targetDocument") or {}
            target_id = target.get("id")
            if not target_id:
                continue
            target_id = str(target_id)
            relationship = REFERENCE_TYPES.get(
                reference.get("referenceType"),
                f"Loại quan hệ {reference.get('referenceType')}",
            )
            if target_id not in relationships[relationship]:
                relationships[relationship].append(target_id)
            linked_ids.append(target_id)

        agency = join_unique(issue.get("agencyName") for issue in issues)
        if not agency:
            agency = document.get("agencyName")

        yield {
            "id": str(document.get("id") or doc_id),
            "title": document.get("title"),
            "so_ky_hieu": document.get("docNum"),
            "ngay_ban_hanh": format_date(document.get("issueDate")),
            "loai_van_ban": (document.get("docType") or {}).get("name"),
            "ngay_co_hieu_luc": format_date(document.get("effFrom")),
            "ngay_het_hieu_luc": format_date(document.get("effTo")),
            "nguon_thu_thap": None,
            "ngay_dang_cong_bao": format_date(document.get("publicDate")),
            "nganh": join_unique(major.get("name") for major in majors),
            "linh_vuc": join_unique(field.get("name") for field in fields),
            "co_quan_ban_hanh": agency,
            "chuc_danh": join_unique(issue.get("jobTitleName") for issue in issues),
            "nguoi_ky": join_unique(issue.get("personName") for issue in issues),
            "pham_vi": (
                "Trung ương"
                if document.get("isLw") is True
                else "Địa phương"
                if document.get("isLw") is False
                else None
            ),
            "thong_tin_ap_dung": None,
            "tinh_trang_hieu_luc": (document.get("effStatus") or {}).get("name"),
            "content": (document.get("documentContent") or {}).get("content"),
            "relationships": dict(relationships),
        }

        if not self.full:
            for linked_id in linked_ids:
                request = self._request_if_new(linked_id)
                if request:
                    yield request

    @staticmethod
    def _catalog_fallback(document, crawl_status):
        majors = document.get("documentMajors") or []
        return {
            "id": str(document.get("id")),
            "title": document.get("title"),
            "so_ky_hieu": document.get("docNum"),
            "ngay_ban_hanh": format_date(document.get("issueDate")),
            "loai_van_ban": (document.get("docType") or {}).get("name"),
            "ngay_co_hieu_luc": format_date(document.get("effFrom")),
            "ngay_het_hieu_luc": format_date(document.get("effTo")),
            "nguon_thu_thap": None,
            "ngay_dang_cong_bao": format_date(document.get("publicDate")),
            "nganh": join_unique(major.get("name") for major in majors),
            "linh_vuc": None,
            "co_quan_ban_hanh": document.get("agencyName"),
            "chuc_danh": None,
            "nguoi_ky": None,
            "pham_vi": (
                "Trung ương"
                if document.get("isLw") is True
                else "Địa phương"
                if document.get("isLw") is False
                else None
            ),
            "thong_tin_ap_dung": None,
            "tinh_trang_hieu_luc": (document.get("effStatus") or {}).get("name"),
            "content": None,
            "relationships": {},
            "crawl_status": crawl_status,
        }
