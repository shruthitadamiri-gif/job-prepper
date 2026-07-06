import os
import re
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()
SERPAPI_URL = "https://serpapi.com/search"


def search_jobs(title: str, location: str = "United States", days_back: int = 30, max_results: int = 5) -> list[dict]:
    """
    Search Google Jobs via SerpAPI. Includes LinkedIn-originated postings.
    Results are client-side filtered to respect days_back exactly.
    """
    if not SERPAPI_KEY:
        return []

    params = {
        "engine": "google_jobs",
        "q": title,
        "location": location,
        "api_key": SERPAPI_KEY,
        "chips": _date_chip(days_back),
        "hl": "en",
    }

    try:
        resp = requests.get(SERPAPI_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"SerpAPI error for '{title}': {e}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    jobs = []

    for job in data.get("jobs_results", []):
        extensions = job.get("detected_extensions", {})
        posted_raw = extensions.get("posted_at", "")

        # Parse relative date string ("3 days ago", "2 weeks ago") → datetime
        posted_dt = _parse_relative_date(posted_raw)

        # Client-side filter: skip jobs outside the requested window
        if posted_dt and posted_dt < cutoff:
            continue

        jobs.append({
            "title": job.get("title", ""),
            "company": job.get("company_name", ""),
            "location": job.get("location", ""),
            "is_remote": "remote" in job.get("location", "").lower() or "remote" in job.get("title", "").lower(),
            "date_posted": posted_raw,
            "date_dt": posted_dt,
            "url": job.get("apply_options", [{}])[0].get("link", "") if job.get("apply_options") else "",
            "description_snippet": job.get("description", "")[:400],
            "employment_type": extensions.get("schedule_type", ""),
            "via": job.get("via", ""),
        })

        if len(jobs) >= max_results:
            break

    return jobs


def search_all_titles(titles: list[str], location: str = "United States", days_back: int = 30) -> dict[str, list[dict]]:
    """Run search_jobs for each title. Returns {title: [jobs]} dict."""
    return {title: search_jobs(title, location=location, days_back=days_back) for title in titles}


def _date_chip(days_back: int) -> str:
    """Map days_back to the closest SerpAPI chip (we filter precisely client-side)."""
    if days_back <= 1:
        return "date_posted:today"
    elif days_back <= 3:
        return "date_posted:3days"
    elif days_back <= 7:
        return "date_posted:week"
    else:
        return "date_posted:month"


def _parse_relative_date(text: str) -> datetime | None:
    """
    Parse Google Jobs relative date strings like:
      '3 days ago', '2 weeks ago', '1 month ago', 'just now', 'today'
    Returns a timezone-aware datetime or None if unparseable.
    """
    if not text:
        return None
    now = datetime.now(timezone.utc)
    text = text.lower().strip()

    if text in ("just now", "today", "1 day ago"):
        return now - timedelta(hours=12)

    m = re.match(r"(\d+)\s+(hour|day|week|month)s?\s+ago", text)
    if not m:
        return None

    n, unit = int(m.group(1)), m.group(2)
    if unit == "hour":
        return now - timedelta(hours=n)
    elif unit == "day":
        return now - timedelta(days=n)
    elif unit == "week":
        return now - timedelta(weeks=n)
    elif unit == "month":
        return now - timedelta(days=n * 30)
    return None
