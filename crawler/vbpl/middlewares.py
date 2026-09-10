import base64
import logging
import time
from pathlib import Path

from scrapy import signals


class RotatingProxyMiddleware:
    """Round-robin proxy rotation with temporary cooldown for failed proxies."""

    def __init__(self, proxies, cooldown_seconds, retry_http_codes, max_proxy_retries):
        self.proxies = proxies
        self.cooldown_seconds = cooldown_seconds
        self.retry_http_codes = set(retry_http_codes)
        self.max_proxy_retries = max_proxy_retries
        self._cursor = 0
        self._banned_until = {}
        self.crawler = None

    @classmethod
    def from_crawler(cls, crawler):
        proxy_file = crawler.settings.get("PROXY_LIST_FILE", "Webshare 100 proxies.txt")
        cooldown_seconds = crawler.settings.getint("PROXY_COOLDOWN_SECONDS", 30)
        retry_http_codes = crawler.settings.getlist(
            "PROXY_RETRY_HTTP_CODES", [403, 407, 429, 500, 502, 503, 504]
        )
        max_proxy_retries = crawler.settings.getint("PROXY_MAX_RETRIES", 2)

        proxy_path = Path(proxy_file)
        if not proxy_path.is_absolute():
            # Scrapy command is executed from project root (where scrapy.cfg lives).
            proxy_path = Path.cwd() / proxy_path

        proxies = cls._load_proxies(proxy_path)

        if not proxies:
            raise RuntimeError(
                f"No valid proxies found in PROXY_LIST_FILE: {proxy_path}"
            )

        middleware = cls(
            proxies=proxies,
            cooldown_seconds=cooldown_seconds,
            retry_http_codes=[int(code) for code in retry_http_codes],
            max_proxy_retries=max_proxy_retries,
        )
        middleware.crawler = crawler
        crawler.signals.connect(middleware.spider_opened, signal=signals.spider_opened)
        return middleware

    @staticmethod
    def _load_proxies(proxy_path):
        proxies = []
        if not proxy_path.exists():
            return proxies

        for raw_line in proxy_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            # Expected format: host:port[:username[:password]]
            parts = line.split(":", 3)
            if len(parts) < 2:
                continue

            host, port = parts[0], parts[1]
            username = parts[2] if len(parts) >= 3 else None
            password = parts[3] if len(parts) >= 4 else None

            proxies.append(
                {
                    "url": f"http://{host}:{port}",
                    "username": username,
                    "password": password,
                }
            )

        return proxies

    def _logger(self):
        spider = getattr(self.crawler, "spider", None) if self.crawler else None
        if spider:
            return spider.logger
        return logging.getLogger("vbpl.proxy")

    def _next_proxy(self):
        count = len(self.proxies)
        now = time.time()

        for _ in range(count):
            index = self._cursor % count
            self._cursor += 1
            proxy = self.proxies[index]
            if self._banned_until.get(proxy["url"], 0) <= now:
                return proxy

        # If all proxies are cooling down, still return next one to avoid deadlock.
        index = self._cursor % count
        self._cursor += 1
        return self.proxies[index]

    def _ban_proxy(self, proxy_url):
        self._banned_until[proxy_url] = time.time() + self.cooldown_seconds

    def _retry_with_new_proxy(self, request):
        retry_times = request.meta.get("proxy_retry_times", 0) + 1
        if retry_times > self.max_proxy_retries:
            return None

        retry_request = request.copy()
        retry_request.meta["proxy_retry_times"] = retry_times
        retry_request.dont_filter = True
        retry_request.headers.pop(b"Proxy-Authorization", None)
        return retry_request

    def process_request(self, request):
        proxy = self._next_proxy()
        request.meta["proxy"] = proxy["url"]
        request.meta["_active_proxy_url"] = proxy["url"]

        username = proxy.get("username")
        password = proxy.get("password")
        if username and password:
            token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode(
                "ascii"
            )
            request.headers[b"Proxy-Authorization"] = f"Basic {token}".encode("ascii")

    def process_response(self, request, response):
        if response.status in self.retry_http_codes:
            proxy_url = request.meta.get("_active_proxy_url")
            if proxy_url:
                self._ban_proxy(proxy_url)
                self._logger().debug(
                    "Banned proxy %s for %ss after HTTP %s",
                    proxy_url,
                    self.cooldown_seconds,
                    response.status,
                )

            retry_request = self._retry_with_new_proxy(request)
            if retry_request is not None:
                return retry_request

        return response

    def process_exception(self, request, exception):
        proxy_url = request.meta.get("_active_proxy_url")
        if proxy_url:
            self._ban_proxy(proxy_url)
            self._logger().debug(
                "Banned proxy %s for %ss after exception: %s",
                proxy_url,
                self.cooldown_seconds,
                repr(exception),
            )

        return self._retry_with_new_proxy(request)

    def spider_opened(self, spider):
        spider.logger.info("Loaded %d proxies", len(self.proxies))
