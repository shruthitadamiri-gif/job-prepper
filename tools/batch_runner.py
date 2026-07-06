from concurrent.futures import ThreadPoolExecutor, as_completed
from tools.jd_parser import parse_jd
from agents.resume_agent import run_resume_agent
from agents.ats_agent import run_ats_agent
from agents.evaluator import run_evaluator
from agents.prep_agent import run_prep_agent

MAX_WORKERS = 5


def _run_single(job: dict) -> dict:
    """Run parse → resume → ATS → eval for one job. Returns enriched result dict."""
    jd_text = f"{job['title']} at {job['company']}\n\nLocation: {job.get('location','')}\n\n{job.get('description_snippet','')}"

    try:
        parsed_jd = parse_jd(jd_text)
    except Exception:
        parsed_jd = {
            "role": job["title"], "company": job["company"],
            "location": job.get("location", ""), "salary_range": "",
            "seniority": "", "required_skills": [], "preferred_skills": [],
            "keywords": job["title"].lower().split(), "key_responsibilities": [],
        }

    resume_output = run_resume_agent(jd_text, parsed_jd)
    ats_result = run_ats_agent(resume_output, parsed_jd)
    eval_result = run_evaluator(resume_output, "", jd_text, parsed_jd)

    return {
        "job": job,
        "jd_text": jd_text,
        "parsed_jd": parsed_jd,
        "resume_output": resume_output,
        "ats_result": ats_result,
        "eval_result": eval_result,
        "prep_output": None,
    }


def run_batch(jobs: list[dict]) -> list[dict]:
    """
    Run job prepper for each job in parallel (up to MAX_WORKERS at once).
    Returns results in the same order as input jobs.
    """
    results = [None] * len(jobs)
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(jobs))) as executor:
        futures = {executor.submit(_run_single, job): i for i, job in enumerate(jobs)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                results[idx] = {"job": jobs[idx], "error": str(e)}
    return results


def run_prep_for_result(result: dict) -> dict:
    """Run interview prep agent for a single batch result. Returns updated result."""
    prep = run_prep_agent(result["jd_text"], result["parsed_jd"])
    result["prep_output"] = prep
    return result
