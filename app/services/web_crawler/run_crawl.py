from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import scrapy
from scrapy import Request
from scrapy.crawler import CrawlerProcess
from scrapy.linkextractors import LinkExtractor
from scrapy_playwright.page import PageMethod


_META_PREFIX = "[WEBCRAWLER_META]"
_IMAGE_EXTS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".bmp",
    ".tif",
    ".tiff",
    ".ico",
)


def _is_xpath(selector: str) -> bool:
    s = selector.strip()
    return s.startswith("/") or s.startswith("./") or s.startswith("(")


def _normalize_domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _build_output_path(config: dict[str, Any]) -> str:
    out_dir = Path(config["output_dir"]).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = "json" if config.get("result_format") == "json" else "csv"
    return str(out_dir / f"{config.get('project_name', 'crawl')}_{stamp}.{ext}")


def _count_output_items(path: str, fmt: str) -> int:
    if not os.path.exists(path):
        return 0
    if fmt == "csv":
        with open(path, "r", encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))
        return max(0, len(rows) - 1)
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return len(payload) if isinstance(payload, list) else 0


class DynamicCrawlerSpider(scrapy.Spider):
    name = "owl_web_crawler"

    def __init__(self, config: dict[str, Any], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.config = config
        self.start_urls = [config["target_url"]]
        self.allowed_domains = [config["allowed_domain"]]
        self.link_extractor = LinkExtractor(allow_domains=self.allowed_domains)
        self.item_count = 0

    def _request_meta(self) -> dict[str, Any]:
        if not self.config.get("rendered", False):
            return {}
        mode = self.config.get("wait_mode", "Smart Wait (Wait for Network)")
        if mode == "Basic (HTML Only)":
            wait_until = "domcontentloaded"
        else:
            wait_until = "networkidle"
        meta: dict[str, Any] = {
            "playwright": True,
            "playwright_page_goto_kwargs": {"wait_until": wait_until},
        }
        if mode == "Wait for Element...":
            selector = (self.config.get("wait_selector") or "").strip()
            if selector:
                meta["playwright_page_methods"] = [
                    PageMethod("wait_for_selector", selector, timeout=15000),
                ]
        return meta

    def start_requests(self):  # type: ignore[override]
        for url in self.start_urls:
            print(f"[i] Seed URL: {url}")
            yield Request(url=url, callback=self.parse_page, meta=self._request_meta())

    def _extract_field(self, response: scrapy.http.Response, selector: str) -> str:
        values = (
            response.xpath(selector).getall()
            if _is_xpath(selector)
            else response.css(selector).getall()
        )
        cleaned = [v.strip() for v in values if isinstance(v, str) and v.strip()]
        return " | ".join(cleaned)

    def _is_image_url(self, url: str) -> bool:
        lower = url.lower()
        return any(lower.endswith(ext) for ext in _IMAGE_EXTS)

    def parse_page(self, response: scrapy.http.Response):  # type: ignore[override]
        print(f"[DONE] Request: {response.url} ({response.status} OK)")
        item: dict[str, str] = {}
        for field in self.config.get("fields", []):
            name = str(field.get("name", "")).strip()
            selector = str(field.get("selector", "")).strip()
            if not name or not selector:
                continue
            item[name] = self._extract_field(response, selector)

        if any(v for v in item.values()):
            self.item_count += 1
            yield item

        for link in self.link_extractor.extract_links(response):
            url = link.url
            if self.config.get("ignore_images", True) and self._is_image_url(url):
                print(f"[SKIP] Request: {url} (Image URL)")
                continue
            if _normalize_domain(url) != self.allowed_domains[0]:
                continue
            yield Request(url=url, callback=self.parse_page, meta=self._request_meta())


def run(config: dict[str, Any]) -> tuple[str, int]:
    output_path = _build_output_path(config)
    fmt = config.get("result_format", "csv").lower()
    feeds: dict[str, Any] = {
        output_path: {
            "format": fmt,
            "encoding": "utf-8",
            "indent": 2 if fmt == "json" else None,
            "overwrite": True,
        }
    }
    settings: dict[str, Any] = {
        "ROBOTSTXT_OBEY": bool(config.get("robots_obey", True)),
        "DOWNLOAD_DELAY": float(config.get("download_delay", 2.0)),
        "DEPTH_LIMIT": int(config.get("depth_limit", 2)),
        "LOG_ENABLED": False,
        "FEEDS": feeds,
    }
    if config.get("rendered", False):
        settings.update(
            {
                "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
                "DOWNLOAD_HANDLERS": {
                    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
                    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
                },
                "PLAYWRIGHT_BROWSER_TYPE": "chromium",
                "PLAYWRIGHT_LAUNCH_OPTIONS": {"headless": True},
            }
        )

    process = CrawlerProcess(settings=settings)
    process.crawl(DynamicCrawlerSpider, config=config)
    process.start()
    count = _count_output_items(output_path, fmt)
    return output_path, count


def main() -> int:
    if len(sys.argv) < 2:
        print("Missing config file path.")
        return 2
    cfg_path = sys.argv[1]
    with open(cfg_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    try:
        output_path, item_count = run(config)
    except Exception as exc:
        print(f"[x ERR] {exc}")
        return 1
    finally:
        try:
            os.remove(cfg_path)
        except Exception:
            pass
    print(
        f"{_META_PREFIX}{json.dumps({'output_file': output_path, 'item_count': item_count})}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

