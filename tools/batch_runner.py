from concurrent.futures import ThreadPoolExecutor, as_completed
import anthropic as _anthropic
from graph import build_graph, make_initial_state
from agents.prep_agent import run_prep_agent

MAX_WORKERS = 3

# Compiled once at module level — LangGraph compiled graphs are stateless;
# each .invoke() call gets its own independent state dict, so concurrent
# invocations are safe.
_graph = build_graph()


def _run_single(job: dict) -> dict:
    """Run the full pipeline for one job via the compiled graph."""
    # Use full JD snapshot if available (set by screening flow); fall back to snippet
    jd_text = job.get("_jd_snapshot") or (
        f"{job['title']} at {job['company']}\n\n"
        f"Location: {job.get('location', '')}\n\n"
        f"{job.get('description_snippet', '')}"
    )
    try:
        result = _graph.invoke(make_initial_state(jd_text))
    except _anthropic.RateLimitError:
        return {"job": job, "error": "Rate limited — rerun this job individually"}
    except _anthropic.APIStatusError as e:
        return {"job": job, "error": f"API error ({e.status_code}) — rerun this job individually"}

    return {
        "job": job,
        "jd_text": jd_text,
        "parsed_jd": result["parsed_jd"],
        "resume_output": result["resume_output"],
        "ats_result": result["ats_result"],
        "eval_result": result["eval_result"],
        "prep_output": None,
    }


def run_batch(jobs: list[dict]) -> list[dict]:
    """Run the pipeline for each job in parallel. Returns results in input order."""
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
