"""Scrapy settings for the VBPL crawler project."""

BOT_NAME = "vbpl"

SPIDER_MODULES = ["vbpl.spiders"]
NEWSPIDER_MODULE = "vbpl.spiders"

ADDONS = {}

ROBOTSTXT_OBEY = False

# Tune concurrency down if the target starts rate-limiting.
CONCURRENT_REQUESTS = 100
CONCURRENT_REQUESTS_PER_DOMAIN = 100
RANDOMIZE_DOWNLOAD_DELAY = False

COOKIES_ENABLED = False

# The spider removes this middleware unless ``-a proxy_file=<path>`` is passed.
DOWNLOADER_MIDDLEWARES = {
    "vbpl.middlewares.RotatingProxyMiddleware": 610,
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
)

PROXY_COOLDOWN_SECONDS = 30
PROXY_MAX_RETRIES = 20
PROXY_RETRY_HTTP_CODES = [403, 407, 429, 500, 502, 503, 504]

FEED_EXPORT_ENCODING = "utf-8"

# Output goes to the dataset data/ folder (one level up from crawler/).
FEEDS = {
    "../data/metadata_raw.jsonl": {
        "format": "jsonlines",
        "encoding": "utf-8",
        "overwrite": False,
    }
}
