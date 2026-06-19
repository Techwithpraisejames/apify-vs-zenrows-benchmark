# ZenRows vs Apify Benchmark

Reproducible benchmark for the article  
**"Best Apify Alternative for Large-Scale Scraping"** published on zenrows.com.

## What this tests

| # | Target | Type |
|---|--------|------|
| 1 | walmart.com product page | Protected |
| 2 | glassdoor.com company page | Protected (DataDome) |
| 3 | bayut.com property search | Protected |
| 4 | google.com SERP | Protected |
| 5 | ikea.com product page | Protected |
| 6 | news.ycombinator.com | Unprotected |
| 7 | docs.scrapy.org | Static documentation |

**200 requests per target per tool. 2 requests/second. Concurrency: 2.**

## What is recorded per request

- HTTP status code (200 = success)
- Response time in milliseconds
- Whether the returned HTML contains a valid `<title>` tag

## Actor used for Apify

`apify/playwright-scraper` — the most widely used general-purpose Playwright Actor on the Apify Store.  

## What this benchmark does NOT cover

- Apify's pre-built marketplace Actors for specific sites (Instagram, Google Maps, LinkedIn).
  The test uses a general-purpose Actor only.
- Apify's scheduling, dataset storage, and monitoring features.
- ZenRows' Scraping Browser in a multi-step session workflow.

## Test date

19th June 2026. Rerun results may differ as sites update their anti-bot configurations.
