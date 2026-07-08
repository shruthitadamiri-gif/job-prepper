"""
Daily discovery script — runs headless (no Streamlit).

Flow:
  discover_titles() → search_all_titles → dedup vs seen_keys()
  → for each new job: create_opportunity(discovered)
  → screen (full JD fetch attempted) → advance to screened_in / screened_out

Cap: max 25 new screenings per run (cost guard).

Run locally:
    cd /path/to/job-prepper
    source venv/bin/activate
    python3 scripts/daily_discovery.py

Or via GitHub Actions (see .github/workflows/daily_discovery.yml).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from concurrent.futures import ThreadPoolExecutor, as_completed
from agents.title_discovery_agent import discover_titles
from agents.screening_agent import run_screening
from tools.job_search import search_all_titles
from tools.jd_fetcher import fetch_jd_from_url
from tools.opportunity_store import (
    create_opportunity, update_stage, update_fields,
    seen_keys, title_performance_context,
)

MAX_NEW_SCREENINGS = 25


def _screen_job(job: dict) -> dict:
    url = job.get("url", "")
    jd_text = (
        f"{job['title']} at {job['company']}\n\n"
        f"Location: {job.get('location', '')}\n\n"
        f"{job.get('description_snippet', '')}"
    )
    screened_from_snippet = True
    if url:
        fetch = fetch_jd_from_url(url)
        if fetch["success"]:
            jd_text = fetch["jd_text"]
            screened_from_snippet = False

    result = run_screening(jd_text, company=job.get("company", ""), location=job.get("location", ""))
    result["_jd_text"] = jd_text
    result["_screened_from_snippet"] = screened_from_snippet
    return result


def run_discovery() -> None:
    print("=== Daily discovery starting ===")

    # 1. Build performance context from funnel history
    perf_ctx = title_performance_context()
    if perf_ctx:
        print(f"Title performance context:\n{perf_ctx}")

    # 2. Discover titles
    print("Discovering titles from resume...")
    titles_data = discover_titles(performance_context=perf_ctx)
    all_titles = (
        [t["title"] for t in titles_data.get("direct_fit", [])] +
        [t["title"] for t in titles_data.get("worth_exploring", [])]
    )
    print(f"Searching {len(all_titles)} titles...")

    # 3. Search
    raw = search_all_titles(all_titles)
    all_jobs = []
    for title, jobs in raw.items():
        for job in jobs:
            job["searched_title"] = title
        all_jobs.extend(jobs)

    print(f"Found {len(all_jobs)} jobs total.")

    # 4. Dedup against existing opportunities
    existing = seen_keys()
    new_jobs = []
    for job in all_jobs:
        key = job.get("url") or f"{job.get('title','').lower()}|{job.get('company','').lower()}"
        if key not in existing:
            new_jobs.append(job)

    print(f"{len(new_jobs)} new (not seen before), capping at {MAX_NEW_SCREENINGS}.")
    new_jobs = new_jobs[:MAX_NEW_SCREENINGS]

    if not new_jobs:
        print("Nothing new to screen — done.")
        return

    # 5. Create opportunities at 'discovered' stage
    opp_map = {}  # job index → opp_id
    for job in new_jobs:
        try:
            opp_id = create_opportunity(
                title=job.get("title", ""),
                company=job.get("company", ""),
                location=job.get("location", ""),
                url=job.get("url", ""),
                searched_title=job.get("searched_title", ""),
                jd_snapshot=job.get("description_snippet", ""),
                source="search",
                stage="discovered",
            )
            opp_map[id(job)] = opp_id
        except Exception as e:
            print(f"  WARN: failed to create opportunity for {job.get('company')} — {job.get('title')}: {e}")

    # 6. Screen in parallel
    screened_in = 0
    screened_out = 0

    def _process(job):
        opp_id = opp_map.get(id(job))
        if not opp_id:
            return
        try:
            sr = _screen_job(job)
            is_out = bool(sr.get("dealbreakers")) or sr.get("verdict") == "no_fit"
            new_stage = "screened_out" if is_out else "screened_in"
            update_stage(opp_id, new_stage)
            update_fields(opp_id, {
                "fit_score": sr.get("fit_score"),
                "fit_verdict": sr.get("verdict"),
                "dealbreakers": sr.get("dealbreakers"),
                "visa_status": sr.get("visa_status"),
                "jd_snapshot": sr["_jd_text"],
            })
            return new_stage
        except Exception as e:
            print(f"  WARN: screening failed for {job.get('company')}: {e}")
            return None

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_process, job): job for job in new_jobs}
        for future in as_completed(futures):
            result = future.result()
            if result == "screened_in":
                screened_in += 1
            elif result == "screened_out":
                screened_out += 1

    print(
        f"=== Done: found={len(all_jobs)} | new={len(new_jobs)} | "
        f"screened_in={screened_in} | screened_out={screened_out} ==="
    )


if __name__ == "__main__":
    run_discovery()
