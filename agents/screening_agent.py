"""
Screening agent — cheap Haiku call to judge fit before tailoring.

Runs check_visa_sponsorship first; a not_sponsored result is an automatic
dealbreaker appended to the output regardless of the LLM verdict.

Hard filters come from config/screening.yaml so they can be changed
without touching code.
"""

import os
import re
import yaml
import anthropic
from dotenv import load_dotenv
from tools.llm_json import parse_llm_json
from tools.visa_check import check_visa_sponsorship

load_dotenv()

# Haiku — high-volume cheap call, not Sonnet
client = anthropic.Anthropic(max_retries=4)

RESUME_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resume.txt")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "screening.yaml")


def _load_resume() -> str:
    with open(RESUME_PATH) as f:
        return f.read()


def _load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def _check_hard_filters(jd_text: str, location: str, config: dict) -> list[str]:
    """Returns a list of dealbreaker strings triggered by hard filters."""
    dealbreakers = []

    # Dealbreaker keywords
    jd_lower = jd_text.lower()
    for kw in config.get("dealbreaker_keywords", []):
        if kw.lower() in jd_lower:
            dealbreakers.append(f"Dealbreaker keyword in JD: '{kw}'")

    # Location check (only if location is known and non-empty)
    if location:
        ok_locations = [loc.lower() for loc in config.get("location_ok", [])]
        loc_lower = location.lower()
        if ok_locations and not any(ok in loc_lower for ok in ok_locations):
            dealbreakers.append(f"Location '{location}' not in acceptable locations list")

    return dealbreakers


def run_screening(
    jd_text: str,
    company: str = "",
    location: str = "",
    hard_filters: dict | None = None,
) -> dict:
    """
    Screen a job description for fit before tailoring.

    Returns:
      {
        "verdict":               "strong_fit" | "borderline" | "no_fit",
        "fit_score":             0-100,
        "rationale":             str (2 sentences),
        "dealbreakers":          [str],
        "matched_strengths":     [str],
        "missing_qualifications":[str],
        "visa_status":           str,
        "screened_from_snippet": bool  # set by caller, default False
      }
    """
    config = hard_filters if hard_filters is not None else _load_config()
    resume = _load_resume()

    # 1. Visa check first — automatic dealbreaker if not_sponsored
    try:
        visa = check_visa_sponsorship(jd_text, company)
        visa_status = visa.get("status", "unknown")
        visa_headline = visa.get("headline", "")
    except Exception as e:
        visa_status = "unknown"
        visa_headline = f"Visa check failed: {e}"

    # 2. Hard filter checks (location, keywords)
    hard_dealbreakers = _check_hard_filters(jd_text, location, config)

    # 3. LLM screening call (Haiku)
    min_seniority = config.get("min_seniority", "mid")
    comp_floor = config.get("comp_floor")

    comp_instruction = (
        f"If the JD explicitly states compensation, flag it as a dealbreaker if it is below ${comp_floor:,}/year."
        if comp_floor else
        "Ignore compensation in your assessment."
    )

    visa_context = f"Visa sponsorship status: {visa_status} — {visa_headline}"

    prompt = f"""You are a career advisor screening a job description for fit against a candidate's resume.

{visa_context}

Minimum seniority required: {min_seniority}
{comp_instruction}

Return ONLY valid JSON with exactly this structure:
{{
  "verdict": "strong_fit" | "borderline" | "no_fit",
  "fit_score": <integer 0-100>,
  "rationale": "<exactly 2 sentences explaining the verdict>",
  "dealbreakers": ["<string>", ...],
  "matched_strengths": ["<string>", ...],
  "missing_qualifications": ["<string>", ...]
}}

Scoring guide:
- strong_fit (75-100): role matches candidate's level, domain, and skills well
- borderline (40-74): some gaps but candidate could credibly apply
- no_fit (0-39): significant mismatch in level, domain, or hard requirements

CANDIDATE RESUME:
{resume}

JOB DESCRIPTION:
{jd_text}

Return only the JSON object, no explanation."""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}]
    )

    result = parse_llm_json(message.content[0].text)

    # Merge hard dealbreakers into the LLM result
    all_dealbreakers = list(result.get("dealbreakers", []))
    all_dealbreakers.extend(hard_dealbreakers)

    # Visa dealbreaker always appended if not sponsored
    if visa_status == "not_sponsored":
        all_dealbreakers.append(f"Visa: {visa_headline}")

    # Force no_fit verdict if any dealbreaker exists
    if all_dealbreakers and result.get("verdict") != "no_fit":
        result["verdict"] = "no_fit"
        result["fit_score"] = min(result.get("fit_score", 0), 30)

    result["dealbreakers"] = all_dealbreakers
    result["visa_status"] = visa_status
    result.setdefault("screened_from_snippet", False)

    return result


if __name__ == "__main__":
    test_jd = """
    Senior AI Product Manager - Acme Corp (Boston, MA / Hybrid)

    We are looking for a Senior AI Product Manager to own the roadmap for our
    ML infrastructure platform. You will work closely with data scientists and
    engineers to ship AI-powered features at scale.

    Requirements:
    - 5+ years of product management experience
    - Strong understanding of machine learning concepts and MLOps
    - Experience with LLMs and model monitoring
    - Must be authorized to work in the US without sponsorship

    Compensation: $180,000 - $220,000
    """

    result = run_screening(test_jd, company="Acme Corp", location="Boston, MA")
    import json
    print(json.dumps(result, indent=2))
