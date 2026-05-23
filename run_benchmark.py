"""
run_benchmark.py
================
ZenRows vs Apify — 7 targets, 200 requests each, 2 req/s.

Records per request (as specified in the brief):
  - HTTP status code (200 = success for ZenRows; 201 = success for Apify)
  - Response time in milliseconds
  - Whether the returned HTML contains a valid page title
  - Tool used / target name

Cost per request is calculated separately in cost_calculator.py.

Usage:
  python run_benchmark.py --tool zenrows
  python run_benchmark.py --tool apify
  python run_benchmark.py --tool both

Environment variables (set in .env):
  ZENROWS_API_KEY
  APIFY_API_TOKEN

Output:
  results/raw_<tool>_<timestamp>.csv   — one row per request
  results/summary_<tool>_<timestamp>.csv — aggregated per target
"""

import asyncio
import argparse
import csv
import os
import time
from datetime import datetime
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REQUESTS_PER_TARGET = 200
CONCURRENCY         = 2      # max in-flight requests at once
RATE_PER_SECOND     = 2.0    # 2 req/s as specified in the brief

ZENROWS_API_KEY = os.getenv("ZENROWS_API_KEY", "")
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "")
APIFY_ACTOR_ID  = "apify~playwright-scraper"

# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

TARGETS = [
    {"name": "Amazon product page",        "url": "https://www.amazon.com/dp/B09X7CRKRZ"},
    {"name": "Glassdoor company page",     "url": "https://www.glassdoor.com/Overview/Working-at-Google-EI_IE9079.11,17.htm"},
    {"name": "Idealista property listing", "url": "https://www.idealista.com/inmueble/100549085/"},
    {"name": "Google SERP",                "url": "https://www.google.com/search?q=web+scraping+tools"},
    {"name": "Gymshark",                   "url": "https://www.gymshark.com/collections/all-mens"},
    {"name": "HackerNews",                 "url": "https://news.ycombinator.com"},
    {"name": "Scrapy docs",                "url": "https://docs.scrapy.org/en/latest/"},
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_title(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "lxml")
        tag = soup.find("title")
        return tag.get_text(strip=True) if tag else ""
    except Exception:
        return ""

def has_valid_title(html: str) -> bool:
    return bool(extract_title(html))

def ensure_results_dir():
    Path("results").mkdir(exist_ok=True)

def now_ts() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class TokenBucket:
    def __init__(self, rate: float):
        self.rate   = rate
        self.tokens = rate
        self.last   = time.monotonic()

    async def acquire(self):
        while True:
            now           = time.monotonic()
            self.tokens  += (now - self.last) * self.rate
            self.last     = now
            if self.tokens > self.rate:
                self.tokens = self.rate
            if self.tokens >= 1:
                self.tokens -= 1
                return
            await asyncio.sleep(0.05)

# ---------------------------------------------------------------------------
# ZenRows — mode=auto
# ---------------------------------------------------------------------------

async def zenrows_request(
    session:   aiohttp.ClientSession,
    target:    dict,
    semaphore: asyncio.Semaphore,
) -> dict:
    params = {
        "apikey": ZENROWS_API_KEY,
        "url":    target["url"],
        "mode":   "auto",
    }
    async with semaphore:
        start = time.monotonic()
        status, html = 0, ""
        try:
            async with session.get(
                "https://api.zenrows.com/v1/",
                params=params,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                status = resp.status
                if status == 200:
                    html = await resp.text()
        except Exception:
            pass
        ms = round((time.monotonic() - start) * 1000)

    title = extract_title(html)
    return {
        "tool":        "zenrows",
        "target":      target["name"],
        "url":         target["url"],
        "status_code": status,
        "response_ms": ms,
        "has_title":   bool(title),
        "title":       title,
        "success":     status == 200 and bool(title),
    }

# ---------------------------------------------------------------------------
# Apify — apify~playwright-scraper (general-purpose, all targets)
# ---------------------------------------------------------------------------

async def apify_request(
    session:   aiohttp.ClientSession,
    target:    dict,
    semaphore: asyncio.Semaphore,
) -> dict:
    payload = {
        "startUrls": [{"url": target["url"]}],
        "pageFunction": """
            async function pageFunction({ page, request }) {
                const title = await page.title();
                return { title, url: request.url };
            }
        """,
        "launchContext":      {"useChrome": True},
        "maxRequestsPerCrawl": 1,
        "proxyConfiguration": {"useApifyProxy": True},
    }
    run_url = (
        f"https://api.apify.com/v2/acts/{APIFY_ACTOR_ID}/runs"
        f"?token={APIFY_API_TOKEN}&waitForFinish=120"
    )
    async with semaphore:
        start = time.monotonic()
        status, title = 0, ""
        try:
            async with session.post(
                run_url, json=payload,
                timeout=aiohttp.ClientTimeout(total=150),
            ) as resp:
                status   = resp.status
                run_data = await resp.json()

            if status == 201:
                run_id = run_data.get("data", {}).get("id", "")
                ds_url = (
                    f"https://api.apify.com/v2/actor-runs/{run_id}/dataset/items"
                    f"?token={APIFY_API_TOKEN}"
                )
                async with session.get(ds_url, timeout=aiohttp.ClientTimeout(total=30)) as ds:
                    items = await ds.json()
                title = items[0].get("title", "") if items else ""
        except Exception:
            pass
        ms = round((time.monotonic() - start) * 1000)

    return {
        "tool":        "apify",
        "target":      target["name"],
        "url":         target["url"],
        "status_code": status,
        "response_ms": ms,
        "has_title":   bool(title),
        "title":       title,
        "success":     status == 201 and bool(title),
    }

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_tool(tool: str, targets: list[dict]) -> list[dict]:
    semaphore = asyncio.Semaphore(CONCURRENCY)
    bucket    = TokenBucket(RATE_PER_SECOND)
    all_results = []

    async with aiohttp.ClientSession() as session:
        for target in targets:
            print(f"\n[{tool.upper()}] {target['name']}")
            results = []

            async def task(i, t=target):
                await bucket.acquire()
                if tool == "zenrows":
                    r = await zenrows_request(session, t, semaphore)
                else:
                    r = await apify_request(session, t, semaphore)
                if i % 20 == 0:
                    mark = "OK" if r["success"] else "FAIL"
                    print(f"  [{i}/{REQUESTS_PER_TARGET}] {mark}  {r['response_ms']}ms")
                return r

            results = await asyncio.gather(*[task(i+1) for i in range(REQUESTS_PER_TARGET)])
            ok = sum(1 for r in results if r["success"])
            print(f"  Done — {ok}/{REQUESTS_PER_TARGET} successful")
            all_results.extend(results)

    return all_results

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

RAW_FIELDS = ["tool", "target", "url", "status_code", "response_ms", "has_title", "title", "success"]

def write_raw(results: list[dict], tool: str, ts: str):
    path = Path("results") / f"raw_{tool}_{ts}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RAW_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    print(f"\nRaw results  → {path}")

def write_summary(results: list[dict], tool: str, ts: str):
    import statistics
    by_target: dict[str, list] = {}
    for r in results:
        by_target.setdefault(r["target"], []).append(r)

    path = Path("results") / f"summary_{tool}_{ts}.csv"
    fields = ["tool", "target", "total", "successful", "success_rate_pct", "avg_ms", "p50_ms", "p95_ms"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for target, reqs in by_target.items():
            times  = sorted(r["response_ms"] for r in reqs)
            n      = len(times)
            ok     = sum(1 for r in reqs if r["success"])
            writer.writerow({
                "tool":             tool,
                "target":           target,
                "total":            n,
                "successful":       ok,
                "success_rate_pct": round(ok / n * 100, 1),
                "avg_ms":           round(statistics.mean(times)),
                "p50_ms":           times[n // 2],
                "p95_ms":           times[int(n * 0.95)],
            })
    print(f"Summary      → {path}")

def print_table(results: list[dict], tool: str):
    import statistics
    by_target: dict[str, list] = {}
    for r in results:
        by_target.setdefault(r["target"], []).append(r)

    print(f"\n{'─'*68}")
    print(f"  {tool.upper()}")
    print(f"{'─'*68}")
    print(f"  {'Target':<36} {'OK':>5} {'Total':>6} {'Rate':>7} {'Avg ms':>8}")
    print(f"{'─'*68}")
    for target, reqs in by_target.items():
        ok  = sum(1 for r in reqs if r["success"])
        avg = round(statistics.mean(r["response_ms"] for r in reqs))
        print(f"  {target[:36]:<36} {ok:>5} {len(reqs):>6} {ok/len(reqs)*100:>6.1f}% {avg:>7}ms")
    print(f"{'─'*68}")

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    global REQUESTS_PER_TARGET
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", choices=["zenrows", "apify", "both"], default="zenrows")
    parser.add_argument("--requests", type=int, default=REQUESTS_PER_TARGET)
    args = parser.parse_args()

    if args.tool in ("zenrows", "both") and not ZENROWS_API_KEY:
        print("ERROR: ZENROWS_API_KEY not set in .env"); return
    if args.tool in ("apify", "both") and not APIFY_API_TOKEN:
        print("ERROR: APIFY_API_TOKEN not set in .env"); return

    REQUESTS_PER_TARGET = args.requests

    ensure_results_dir()
    ts   = now_ts()
    tools = ["zenrows", "apify"] if args.tool == "both" else [args.tool]

    for tool in tools:
        print(f"\n{'='*68}")
        print(f"  {tool.upper()} — {len(TARGETS)} targets × {REQUESTS_PER_TARGET} requests @ {RATE_PER_SECOND} req/s")
        print(f"{'='*68}")
        results = asyncio.run(run_tool(tool, TARGETS))
        print_table(results, tool)
        write_raw(results, tool, ts)
        write_summary(results, tool, ts)


if __name__ == "__main__":
    main()