#!/usr/bin/env python3
"""
Project 3: Robust Web Scraper

Safety/ethics:
- Intended for websites that permit automated access.
- Does not bypass CAPTCHAs, access controls, robots restrictions, or
  anti-bot mechanisms.
- Does not implement stealth/evasion behavior.
- Optional proxy support is for legitimate network routing/testing only;
  it is not used to bypass restrictions.

Features:
- requests.Session with connection reuse
- configurable User-Agent
- retry with exponential backoff for transient HTTP/network errors
- CAPTCHA/access-block detection and safe stop
- BeautifulSoup CSS-selector extraction
- structured JSON and CSV output
- validation of extracted records
- logging
- optional single proxy supplied by the user
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_UA = (
    "Mozilla/5.0 (compatible; EducationalWebScraper/1.0; "
    "+https://example.com/bot-info)"
)

BLOCK_MARKERS = (
    "captcha",
    "verify you are human",
    "access denied",
    "cf-chl-",
    "unusual traffic",
)


class ScraperError(Exception):
    """Base exception for scraper failures."""


class AccessBlockedError(ScraperError):
    """Raised when a site asks for human verification or blocks access."""


@dataclass
class ScrapeResult:
    url: str
    title: str
    price: str
    description: str
    scraped_at: str


def configure_logging(log_file: Path) -> logging.Logger:
    logger = logging.getLogger("web_scraper")
    logger.setLevel(logging.INFO)

    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger


class ScraperEngine:
    def __init__(
        self,
        *,
        timeout: float = 15,
        max_retries: int = 4,
        user_agent: str = DEFAULT_UA,
        proxy: str | None = None,
        min_delay: float = 1.0,
        max_delay: float = 3.0,
        logger: logging.Logger | None = None,
    ) -> None:
        self.timeout = timeout
        self.min_delay = min_delay
        self.max_delay = max(max_delay, min_delay)
        self.logger = logger or logging.getLogger("web_scraper")

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.8",
        })

        if proxy:
            self.session.proxies.update({
                "http": proxy,
                "https": proxy,
            })

        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )

        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _polite_delay(self) -> None:
        delay = random.uniform(self.min_delay, self.max_delay)
        time.sleep(delay)

    @staticmethod
    def _looks_blocked(html: str) -> bool:
        lowered = html.lower()
        return any(marker in lowered for marker in BLOCK_MARKERS)

    def fetch(self, url: str) -> str:
        self.logger.info("Fetching: %s", url)
        self._polite_delay()

        try:
            response = self.session.get(
                url,
                timeout=self.timeout,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            self.logger.error("Request failed: %s", exc)
            raise ScraperError(str(exc)) from exc

        self.logger.info(
            "HTTP %s | final URL: %s | bytes: %d",
            response.status_code,
            response.url,
            len(response.content),
        )

        if response.status_code in (401, 403, 429):
            raise AccessBlockedError(
                f"Access was refused/rate-limited (HTTP {response.status_code}). "
                "The scraper will stop rather than attempt to bypass the restriction."
            )

        if response.status_code >= 400:
            raise ScraperError(f"HTTP error: {response.status_code}")

        if self._looks_blocked(response.text):
            raise AccessBlockedError(
                "The response appears to contain a CAPTCHA or access-control page. "
                "Human verification/access controls are not bypassed."
            )

        response.raise_for_status()
        return response.text

    @staticmethod
    def parse_product(html: str, url: str) -> ScrapeResult:
        soup = BeautifulSoup(html, "html.parser")

        def text(selector: str) -> str:
            node = soup.select_one(selector)
            return node.get_text(" ", strip=True) if node else ""

        title = text("h1.product-title") or text("h1") or text("title")
        price = text(".price") or text("[itemprop='price']")
        description = text(".description") or text("[itemprop='description']")

        if not title:
            raise ScraperError(
                "Required title field was not found. "
                "The site's DOM may have changed."
            )

        return ScrapeResult(
            url=url,
            title=title,
            price=price,
            description=description,
            scraped_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )


def save_json(records: list[ScrapeResult], path: Path) -> None:
    path.write_text(
        json.dumps([asdict(r) for r in records], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def save_csv(records: list[ScrapeResult], path: Path) -> None:
    rows = [asdict(r) for r in records]
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Educational, permission-based web scraper."
    )
    parser.add_argument("url", help="URL of a page you are permitted to scrape")
    parser.add_argument("--json", default="scraped_data.json")
    parser.add_argument("--csv", default="scraped_data.csv")
    parser.add_argument("--log", default="scraper.log")
    parser.add_argument("--proxy", help="Optional single proxy for legitimate routing/testing")
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--min-delay", type=float, default=1.0)
    parser.add_argument("--max-delay", type=float, default=3.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logger = configure_logging(Path(args.log))

    if args.min_delay < 0 or args.max_delay < args.min_delay:
        print("Invalid delay range.", flush=True)
        return 2

    engine = ScrapingEngine(
        timeout=args.timeout,
        proxy=args.proxy,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        logger=logger,
    )

    try:
        html = engine.fetch(args.url)
        record = engine.parse_product(html, args.url)
        records = [record]
        save_json(records, Path(args.json))
        save_csv(records, Path(args.csv))

        print("Scrape completed successfully.")
        print(f"JSON: {Path(args.json).resolve()}")
        print(f"CSV : {Path(args.csv).resolve()}")
        return 0

    except AccessBlockedError as exc:
        logger.warning("%s", exc)
        print(f"Stopped safely: {exc}")
        return 3
    except ScraperError as exc:
        logger.error("%s", exc)
        print(f"Scrape failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
