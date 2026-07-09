import os
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()
SERPAPI_URL = "https://serpapi.com/search"

ADZUNA_APP_ID  = os.getenv("ADZUNA_APP_ID", "").strip()
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "").strip()
ADZUNA_URL     = "https://api.adzuna.com/v1/api/jobs/us/search/1"

_model = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def job_key(job: dict) -> str:
    """Stable identity for a job — used for dedup and selection state."""
    return job["url"] if job.get("url") else f"{job['title']}|{job['company']}".lower()


def search_jobs(
    title: str,
    location: str = "United States",
    days_back: int = 30,
    max_results: int = 15,
    include_undated: bool = False,
) -> list[dict]:
    """
    Search Google Jobs via SerpAPI with pagination (up to 3 pages per title).

    Date policy: jobs with unparseable or missing posted_at are excluded by
    default (include_undated=False). Set include_undated=True to keep them;
    they will carry date_unknown=True so the UI can badge them.
    """
    if not SERPAPI_KEY:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    jobs: list[dict] = []
    next_page_token: str | None = None

    for page in range(3):  # max 3 pages
        params = {
            "engine": "google_jobs",
            "q": title,
            "location": location,
            "api_key": SERPAPI_KEY,
            "hl": "en",
        }
        if next_page_token:
            params["next_page_token"] = next_page_token

        try:
            resp = requests.get(SERPAPI_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"SerpAPI error for '{title}' page {page + 1}: {e}")
            break

        page_jobs = data.get("jobs_results", [])
        if not page_jobs:
            break

        for job in page_jobs:
            extensions = job.get("detected_extensions", {})
            posted_raw = extensions.get("posted_at", "")
            posted_dt = _parse_relative_date(posted_raw)
            date_unknown = posted_dt is None

            if date_unknown and not include_undated:
                continue
            if posted_dt and posted_dt < cutoff:
                continue

            jobs.append({
                "title": job.get("title", ""),
                "company": job.get("company_name", ""),
                "location": job.get("location", ""),
                "is_remote": (
                    "remote" in job.get("location", "").lower()
                    or "remote" in job.get("title", "").lower()
                ),
                "date_posted": posted_raw,
                "date_dt": posted_dt,
                "date_unknown": date_unknown,
                "url": (
                    job.get("apply_options", [{}])[0].get("link", "")
                    if job.get("apply_options") else ""
                ),
                "description_snippet": job.get("description", "")[:400],
                "employment_type": extensions.get("schedule_type", ""),
                "via": job.get("via", ""),
            })

            if len(jobs) >= max_results:
                break

        if len(jobs) >= max_results:
            break

        next_page_token = data.get("serpapi_pagination", {}).get("next_page_token")
        if not next_page_token:
            break

    return jobs


def _normalize_job(
    title: str, company: str, location: str, url: str,
    description: str, date_posted: str, via: str,
    is_remote: bool = False,
) -> dict:
    """Normalise a job from any provider into the shared schema."""
    return {
        "title": title,
        "company": company,
        "location": location,
        "is_remote": is_remote or "remote" in location.lower() or "remote" in title.lower(),
        "date_posted": date_posted,
        "date_dt": None,
        "date_unknown": not date_posted,
        "url": url,
        "description_snippet": description[:400],
        "employment_type": "",
        "via": via,
    }


def search_jobs_remotive(title: str, days_back: int = 30) -> list[dict]:
    """
    Search Remotive for remote tech/PM jobs. No auth required.
    Filters by title keyword match since Remotive has no location param
    (it's remote-only by definition).
    """
    try:
        resp = requests.get(
            "https://remotive.com/api/remote-jobs",
            params={"search": title, "limit": 20},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Remotive error for '{title}': {e}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    jobs = []
    for job in data.get("jobs", []):
        # Parse ISO date
        pub = job.get("publication_date", "")
        try:
            pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            if pub_dt < cutoff:
                continue
            date_str = pub_dt.strftime("%Y-%m-%d")
        except Exception:
            date_str = pub[:10] if pub else ""

        jobs.append(_normalize_job(
            title=job.get("title", ""),
            company=job.get("company_name", ""),
            location="Remote",
            url=job.get("url", ""),
            description=job.get("description", "")[:400],
            date_posted=date_str,
            via="Remotive",
            is_remote=True,
        ))

    return jobs


def search_jobs_adzuna(
    title: str,
    location: str = "San Francisco, CA",
    days_back: int = 30,
    max_results: int = 15,
) -> list[dict]:
    """
    Search Adzuna (aggregates Indeed, Glassdoor, and others).
    Requires ADZUNA_APP_ID and ADZUNA_APP_KEY env vars.
    """
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        return []

    # Map location string to a simple city name for Adzuna's where param
    where = location.split(",")[0].strip() if location else "San Francisco"
    # Adzuna uses max_days_old for date filtering
    max_days = min(days_back, 30)

    try:
        resp = requests.get(
            ADZUNA_URL,
            params={
                "app_id": ADZUNA_APP_ID,
                "app_key": ADZUNA_APP_KEY,
                "what": title,
                "where": where,
                "results_per_page": max_results,
                "max_days_old": max_days,
                "content-type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Adzuna error for '{title}': {e}")
        return []

    jobs = []
    for job in data.get("results", []):
        created = job.get("created", "")
        try:
            date_str = created[:10]
        except Exception:
            date_str = ""

        jobs.append(_normalize_job(
            title=job.get("title", ""),
            company=(job.get("company") or {}).get("display_name", ""),
            location=(job.get("location") or {}).get("display_name", location),
            url=job.get("redirect_url", ""),
            description=job.get("description", ""),
            date_posted=date_str,
            via="Adzuna",
        ))

    return jobs


def search_all_titles(
    titles: list[str],
    location: str = "United States",
    days_back: int = 30,
) -> dict[str, list[dict]]:
    """
    Search each title, dedup across titles, then compute title_match scores.

    Dedup key: (job_title.lower(), company.lower()). First occurrence wins;
    later duplicates add the searched_title to the winner's matched_titles list.

    title_match (0-100 int): cosine similarity between the searched title and
    the returned job title, computed once via the cached SentenceTransformer.

    Returns {searched_title: [jobs_unique_to_that_title]}, sorted by
    title_match descending within each group.
    """
    seen: dict[tuple, dict] = {}   # dedup key → surviving job dict
    result: dict[str, list[dict]] = {t: [] for t in titles}

    has_serpapi  = bool(SERPAPI_KEY)
    has_adzuna   = bool(ADZUNA_APP_ID and ADZUNA_APP_KEY)
    is_remote    = "remote" in location.lower()

    def _fetch_all_for_title(searched_title: str) -> list[tuple[str, dict]]:
        """Return list of (searched_title, job) pairs from all active providers."""
        pairs = []
        fns = []
        if has_serpapi:
            fns.append(lambda t=searched_title: search_jobs(t, location=location, days_back=days_back))
        if has_adzuna:
            fns.append(lambda t=searched_title: search_jobs_adzuna(t, location=location, days_back=days_back))
        # Always include Remotive for remote coverage
        fns.append(lambda t=searched_title: search_jobs_remotive(t, days_back=days_back))

        with ThreadPoolExecutor(max_workers=len(fns)) as ex:
            for jobs in ex.map(lambda f: f(), fns):
                for job in jobs:
                    pairs.append((searched_title, job))
        return pairs

    for searched_title in titles:
        for _, job in _fetch_all_for_title(searched_title):
            dk = (job["title"].lower().strip(), job["company"].lower().strip())
            if dk in seen:
                existing = seen[dk]
                if searched_title not in existing.get("matched_titles", []):
                    existing.setdefault("matched_titles", []).append(searched_title)
            else:
                job["matched_titles"] = [searched_title]
                seen[dk] = job
                result[searched_title].append(job)

    # Compute title_match for all surviving jobs in one batch
    survivors = list(seen.values())
    if survivors:
        model = _get_model()
        searched_texts = [j["matched_titles"][0] for j in survivors]
        returned_texts = [j["title"] for j in survivors]
        s_embs = model.encode(searched_texts)
        r_embs = model.encode(returned_texts)
        for job, s_emb, r_emb in zip(survivors, s_embs, r_embs):
            score = cosine_similarity([s_emb], [r_emb])[0][0]
            job["title_match"] = int(round(float(score) * 100))

    # Sort each group by title_match descending
    for title in result:
        result[title].sort(key=lambda j: j.get("title_match", 0), reverse=True)

    return result


def _parse_relative_date(text: str) -> datetime | None:
    """
    Parse Google Jobs relative date strings like:
      '3 days ago', '2 weeks ago', '1 month ago', 'just now', 'today'
    Returns a timezone-aware datetime, or None if the string is unparseable.
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
