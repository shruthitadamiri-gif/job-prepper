import os
import requests
from dotenv import load_dotenv

load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()
SERPAPI_URL = "https://serpapi.com/search"


def search_jobs(title: str, location: str = "United States", days_back: int = 30, max_results: int = 5) -> list[dict]:
    """
    Search Google Jobs via SerpAPI. Includes LinkedIn-originated postings.
    """
    if not SERPAPI_KEY:
        return []

    # Google Jobs date filter chip
    chips = _date_chip(days_back)

    params = {
        "engine": "google_jobs",
        "q": title,
        "location": location,
        "api_key": SERPAPI_KEY,
        "chips": chips,
        "hl": "en",
    }

    try:
        resp = requests.get(SERPAPI_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"SerpAPI error for '{title}': {e}")
        return []

    jobs = []
    for job in data.get("jobs_results", [])[:max_results]:
        # Extract source (LinkedIn, Indeed, etc.)
        extensions = job.get("detected_extensions", {})
        sources = [h.get("link", "") for h in job.get("apply_options", [])]
        via = job.get("via", "")

        jobs.append({
            "title": job.get("title", ""),
            "company": job.get("company_name", ""),
            "location": job.get("location", ""),
            "is_remote": "remote" in job.get("location", "").lower() or "remote" in job.get("title", "").lower(),
            "date_posted": extensions.get("posted_at", ""),
            "url": job.get("apply_options", [{}])[0].get("link", "") if job.get("apply_options") else "",
            "description_snippet": job.get("description", "")[:400],
            "employment_type": extensions.get("schedule_type", ""),
            "via": via,  # e.g. "via LinkedIn", "via Indeed"
        })

    return jobs


def search_all_titles(titles: list[str], location: str = "United States", days_back: int = 30) -> dict[str, list[dict]]:
    """Run search_jobs for each title. Returns {title: [jobs]} dict."""
    results = {}
    for title in titles:
        results[title] = search_jobs(title, location=location, days_back=days_back)
    return results


def _date_chip(days_back: int) -> str:
    if days_back <= 1:
        return "date_posted:today"
    elif days_back <= 3:
        return "date_posted:3days"
    elif days_back <= 7:
        return "date_posted:week"
    else:
        return "date_posted:month"
