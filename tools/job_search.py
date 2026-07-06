import os
import requests
from dotenv import load_dotenv

load_dotenv()

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "").strip()
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "").strip()
ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs"


def search_jobs(title: str, location: str = "us", days_back: int = 30, max_results: int = 5) -> list[dict]:
    """
    Search for jobs by title using Adzuna API.
    location: country code — 'us', 'gb', 'ca', 'au'
    """
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        return []

    # Adzuna uses country code in URL path
    country = _parse_country(location)

    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": max_results,
        "what": title,
        "where": location if country == "us" else "",
        "max_days_old": days_back,
        "content-type": "application/json",
        "sort_by": "date",
    }

    try:
        resp = requests.get(
            f"{ADZUNA_BASE}/{country}/search/1",
            params=params,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Adzuna error for '{title}': {e}")
        return []

    jobs = []
    for job in data.get("results", []):
        created = job.get("created", "")
        date_posted = created[:10] if created else "Unknown"

        jobs.append({
            "title": job.get("title", ""),
            "company": job.get("company", {}).get("display_name", ""),
            "location": job.get("location", {}).get("display_name", ""),
            "is_remote": "remote" in job.get("title", "").lower() or "remote" in job.get("description", "").lower(),
            "date_posted": date_posted,
            "url": job.get("redirect_url", ""),
            "description_snippet": job.get("description", "")[:400],
            "employment_type": job.get("contract_time", ""),
        })

    return jobs


def search_all_titles(titles: list[str], location: str = "United States", days_back: int = 30) -> dict[str, list[dict]]:
    """Run search_jobs for each title. Returns {title: [jobs]} dict."""
    results = {}
    for title in titles:
        results[title] = search_jobs(title, location=location, days_back=days_back)
    return results


def _parse_country(location: str) -> str:
    loc = location.lower()
    if any(x in loc for x in ["uk", "united kingdom", "britain", "england"]):
        return "gb"
    if any(x in loc for x in ["canada", "toronto", "vancouver"]):
        return "ca"
    if any(x in loc for x in ["australia", "sydney", "melbourne"]):
        return "au"
    return "us"
