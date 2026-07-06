import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

JSEARCH_KEY = os.getenv("JSEARCH_API_KEY", "").strip()
JSEARCH_HOST = "jsearch.p.rapidapi.com"


def _date_posted_param(days_back: int) -> str:
    """Convert days_back to JSearch date_posted param value."""
    if days_back <= 1:
        return "today"
    elif days_back <= 3:
        return "3days"
    elif days_back <= 7:
        return "week"
    else:
        return "month"


def search_jobs(title: str, location: str = "United States", days_back: int = 30, max_results: int = 5) -> list[dict]:
    """
    Search for jobs by title using JSearch API.

    Returns a list of job dicts:
      {title, company, location, date_posted, url, description_snippet, employment_type}
    """
    if not JSEARCH_KEY:
        return []

    headers = {
        "X-RapidAPI-Key": JSEARCH_KEY,
        "X-RapidAPI-Host": JSEARCH_HOST,
    }

    params = {
        "query": f"{title} in {location}",
        "page": "1",
        "num_pages": "1",
        "date_posted": _date_posted_param(days_back),
        "employment_types": "FULLTIME",
    }

    try:
        resp = requests.get(
            f"https://{JSEARCH_HOST}/search",
            headers=headers,
            params=params,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"JSearch error for '{title}': {e}")
        return []

    jobs = []
    for job in data.get("data", [])[:max_results]:
        posted_raw = job.get("job_posted_at_datetime_utc", "")
        try:
            posted_date = datetime.fromisoformat(posted_raw.replace("Z", "+00:00")).strftime("%b %d, %Y")
        except Exception:
            posted_date = posted_raw[:10] if posted_raw else "Unknown"

        jobs.append({
            "title": job.get("job_title", ""),
            "company": job.get("employer_name", ""),
            "location": job.get("job_city", "") + (f", {job.get('job_state','')}" if job.get("job_state") else "") or job.get("job_country", ""),
            "is_remote": job.get("job_is_remote", False),
            "date_posted": posted_date,
            "url": job.get("job_apply_link") or job.get("job_google_link", ""),
            "description_snippet": (job.get("job_description", "")[:400] + "...") if job.get("job_description") else "",
            "employment_type": job.get("job_employment_type", ""),
        })

    return jobs


def search_all_titles(titles: list[str], location: str = "United States", days_back: int = 30) -> dict[str, list[dict]]:
    """
    Run search_jobs for each title. Returns {title: [jobs]} dict.
    """
    results = {}
    for title in titles:
        results[title] = search_jobs(title, location=location, days_back=days_back)
    return results
