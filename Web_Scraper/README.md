# Project 3: Web Scraper with Robust Request Handling

## Overview

This project is an educational web scraper built with Python, `requests`, and BeautifulSoup.

It demonstrates:

- HTTP request handling with `requests.Session`
- connection pooling and keep-alive
- retry handling with exponential backoff
- transient HTTP status handling
- configurable request timing
- optional legitimate proxy configuration
- CAPTCHA/access-block detection
- HTML parsing with BeautifulSoup and CSS selectors
- structured JSON and CSV output
- data validation and DOM-change detection
- logging and command-line configuration

### Important safety boundary

The scraper is designed for websites that permit automated access. It intentionally **does not bypass CAPTCHAs, access controls, rate limits, geo-restrictions, or anti-bot systems**, and it does not automate CAPTCHA solving or stealth/evasion techniques.

If a target returns a CAPTCHA or an access-denied/rate-limit response, the program stops safely instead of attempting to defeat that control.

## Files

```text
web_scraper_project/
├── web_scraper.py
├── README.md
├── requirements.txt
├── test_web_scraper.py
└── .gitignore
```

## Installation

```bash
python -m pip install -r requirements.txt
```

## Usage

```bash
python web_scraper.py "https://example.com/product"
```

Optional output files:

```bash
python web_scraper.py "https://example.com/product" \
  --json scraped_data.json \
  --csv scraped_data.csv \
  --log scraper.log
```

Windows PowerShell:

```powershell
python web_scraper.py "https://example.com/product" --json scraped_data.json --csv scraped_data.csv
```

Optional legitimate proxy configuration:

```bash
python web_scraper.py "https://example.com/product" --proxy http://127.0.0.1:8080
```

The proxy option is intended for authorized network routing/testing. It is not a mechanism for bypassing website restrictions.

## Retry and resilience

The HTTP adapter retries transient failures including:

- 429
- 500
- 502
- 503
- 504
- connection/read failures

Exponential backoff is handled by urllib3's `Retry` implementation.

For 401/403/429 responses or pages containing common CAPTCHA/access-control markers, the scraper stops and reports the reason.

## Data extraction

The parser uses CSS selectors:

```text
h1.product-title
.price
.description
```

It falls back to:

```text
h1
title
[itemprop='price']
[itemprop='description']
```

If a required title cannot be found, the program reports a DOM-change error instead of silently producing invalid data.

## Output

JSON example:

```json
[
  {
    "url": "https://example.com/product",
    "title": "Example Product",
    "price": "$10",
    "description": "Example description",
    "scraped_at": "2026-08-17T12:00:00Z"
  }
]
```

CSV contains the same fields as columns.

## Testing

Run:

```bash
python -m unittest test_web_scraper.py -v
```

The tests cover:

- successful parsing
- fallback selectors
- CAPTCHA/access-block detection
- HTTP error handling
- JSON/CSV generation

## Ethical scraping checklist

Before scraping a real website:

1. Check its Terms of Service.
2. Check its `robots.txt` and applicable policies.
3. Use a reasonable request rate.
4. Collect only data you are authorized to collect.
5. Do not attempt to defeat CAPTCHAs or access controls.
6. Store credentials/API keys outside source code.
