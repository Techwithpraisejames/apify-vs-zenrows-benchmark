# ZenRows vs Apify Benchmark

Reproducible benchmark for the article  
**"Best Apify Alternative for Large-Scale Scraping"** published on zenrows.com.

## What this tests

| # | Target | Type |
|---|--------|------|
| 1 | amazon.com product page | Protected |
| 2 | glassdoor.com company page | Protected (DataDome) |
| 3 | idealista.com property listing | Protected (anti-bot) |
| 4 | google.com SERP | Protected |
| 5 | gymshark.com product listing | Protected (Cloudflare) |
| 6 | reuters.com/technology | Unprotected news |
| 7 | docs.scrapy.org | Static documentation |

**200 requests per target per tool. 2 requests/second. Concurrency: 2.**

## What is recorded per request

- HTTP status code (200 = success for ZenRows; 201 = Actor created for Apify)
- Response time in milliseconds
- Whether the returned HTML contains a valid `<title>` tag
- Tool used

## Setup

```bash
git clone https://github.com/<your-handle>/zenrows-vs-apify-benchmark
cd zenrows-vs-apify-benchmark
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your API keys
```

## Run

```bash
# Validate keys + targets first (1 request each, ~2 min)
python smoke_test.py

# Full ZenRows benchmark (~35 min for 7 targets x 200 requests)
python run_benchmark.py --tool zenrows

# Full Apify benchmark (~several hours — each run is a full Actor execution)
python run_benchmark.py --tool apify

# Calculate effective cost per 1,000 successful requests
# ZenRows — derived from published plan rates, no extra input needed
python cost_calculator.py --tool zenrows --raw results/raw_zenrows_*.csv

# Apify — supply total dashboard spend after the run
python cost_calculator.py --tool apify --raw results/raw_apify_*.csv --apify-spend 14.23
```

## Output files

| File | Contents |
|------|----------|
| `results/raw_<tool>_<ts>.csv` | One row per request — status, ms, title found, success |
| `results/summary_<tool>_<ts>.csv` | Aggregated per target — success rate, p50/p95 latency |
| `results/cost_<tool>_<ts>.csv` | Effective cost per 1,000 successful requests |

## Actor used for Apify

`apify/playwright-scraper` — the most widely used general-purpose Playwright Actor on the Apify Store.  
Residential proxies enabled for protected targets; datacenter proxies for unprotected targets.

## What this benchmark does NOT cover

- Apify's pre-built marketplace Actors for specific sites (Instagram, Google Maps, LinkedIn).
  The test uses a general-purpose Actor only.
- Apify's scheduling, dataset storage, and monitoring features.
- ZenRows' Scraping Browser in a multi-step session workflow.

## Requirements

```
aiohttp>=3.9
beautifulsoup4>=4.12
lxml>=5.0
pandas>=2.0
python-dotenv>=1.0
requests>=2.31
```

## Test date

May 2026. Rerun results may differ as sites update their anti-bot configurations.