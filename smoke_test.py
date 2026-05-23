"""
smoke_test.py
=============
Fires ONE request per target for both ZenRows and Apify.
Use this to validate your API keys and confirm targets are reachable
before the full 200-request benchmark run.

Usage:
  python smoke_test.py
"""

import asyncio
import os
import time

import aiohttp
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

ZENROWS_API_KEY = os.getenv("ZENROWS_API_KEY", "")
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "")
APIFY_ACTOR_ID  = "apify~playwright-scraper"

TARGETS = [
    {"name": "Amazon product page",        "url": "https://www.amazon.com/dp/B09X7CRKRZ"},
    {"name": "Glassdoor company page",     "url": "https://www.glassdoor.com/Overview/Working-at-Google-EI_IE9079.11,17.htm"},
    {"name": "Idealista property listing", "url": "https://www.idealista.com/inmueble/100549085/"},
    {"name": "Google SERP",                "url": "https://www.google.com/search?q=web+scraping+tools"},
    {"name": "Gymshark (Cloudflare)",      "url": "https://www.gymshark.com/collections/all-mens"},
    {"name": "Reuters (unprotected news)", "url": "https://www.reuters.com/technology/"},
    {"name": "Scrapy docs (static docs)",  "url": "https://docs.scrapy.org/en/latest/"},
]


def extract_title(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "lxml")
        tag = soup.find("title")
        return tag.get_text(strip=True) if tag else ""
    except Exception:
        return ""


async def smoke_zenrows(session: aiohttp.ClientSession, target: dict) -> dict:
    params = {
        "apikey": ZENROWS_API_KEY,
        "url":    target["url"],
        "mode":   "auto",
    }
    start = time.monotonic()
    try:
        async with session.get(
            "https://api.zenrows.com/v1/",
            params=params,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            status = resp.status
            html = await resp.text() if status == 200 else ""
    except Exception as e:
        return {"status": 0, "ms": 0, "title": "", "error": str(e)}
    ms = round((time.monotonic() - start) * 1000)
    return {"status": status, "ms": ms, "title": extract_title(html)}


async def smoke_apify(session: aiohttp.ClientSession, target: dict) -> dict:
    payload = {
        "startUrls": [{"url": target["url"]}],
        "pageFunction": """
            async function pageFunction({ page, request }) {
                const title = await page.title();
                return { title, url: request.url };
            }
        """,
        "launchContext": {"useChrome": True},
        "maxRequestsPerCrawl": 1,
        "proxyConfiguration": {"useApifyProxy": True},
    }
    run_url = (
        f"https://api.apify.com/v2/acts/{APIFY_ACTOR_ID}/runs"
        f"?token={APIFY_API_TOKEN}&waitForFinish=120"
    )
    start = time.monotonic()
    try:
        async with session.post(
            run_url, json=payload,
            timeout=aiohttp.ClientTimeout(total=150),
        ) as resp:
            status = resp.status
            run_data = await resp.json()

        title = ""
        if status == 201:
            run_id = run_data.get("data", {}).get("id", "")
            ds_url = (
                f"https://api.apify.com/v2/actor-runs/{run_id}/dataset/items"
                f"?token={APIFY_API_TOKEN}"
            )
            async with session.get(ds_url, timeout=aiohttp.ClientTimeout(total=30)) as ds:
                items = await ds.json()
            title = items[0].get("title", "") if items else ""
    except Exception as e:
        return {"status": 0, "ms": 0, "title": "", "error": str(e)}
    ms = round((time.monotonic() - start) * 1000)
    return {"status": status, "ms": ms, "title": title}


async def main():
    print("ZenRows vs Apify — Smoke Test (1 request per target)\n")

    if not ZENROWS_API_KEY:
        print("ZENROWS_API_KEY missing — check your .env file\n")
    if not APIFY_API_TOKEN:
        print("APIFY_API_TOKEN missing — check your .env file\n")

    async with aiohttp.ClientSession() as session:
        for target in TARGETS:
            print(f"Target: {target['name']}")
            print(f"  URL: {target['url']}")

            if ZENROWS_API_KEY:
                r = await smoke_zenrows(session, target)
                ok = r["status"] == 200 and bool(r.get("title"))
                print(f"  ZenRows  [HTTP {r['status']}]  {r['ms']}ms  title={r.get('title','')[:60]!r}  {'OK' if ok else 'FAIL'}")

            if APIFY_API_TOKEN:
                r = await smoke_apify(session, target)
                ok = r["status"] == 201 and bool(r.get("title"))
                print(f"  Apify    [HTTP {r['status']}]  {r['ms']}ms  title={r.get('title','')[:60]!r}  {'OK' if ok else 'FAIL'}")

            print()


if __name__ == "__main__":
    asyncio.run(main())