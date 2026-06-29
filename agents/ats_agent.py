import re


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", text.lower())


def run_ats_agent(resume_output: str, parsed_jd: dict) -> dict:
    """
    Compares the tailored resume against the JD's required/preferred skills
    and keywords to find which ones are missing — a deterministic ATS
    keyword gap check (no LLM call, so results are exact and reproducible).
    """
    candidate_terms = []
    for field in ("required_skills", "preferred_skills", "keywords"):
        candidate_terms.extend(parsed_jd.get(field, []))

    seen = set()
    terms = []
    for term in candidate_terms:
        key = term.strip().lower()
        if key and key not in seen:
            seen.add(key)
            terms.append(term.strip())

    normalized_resume = _normalize(resume_output)

    matched = []
    missing = []
    for term in terms:
        normalized_term = _normalize(term)
        if normalized_term and normalized_term in normalized_resume:
            matched.append(term)
        else:
            missing.append(term)

    coverage_percent = round(100 * len(matched) / len(terms)) if terms else 100

    return {
        "matched_keywords": matched,
        "missing_keywords": missing,
        "coverage_percent": coverage_percent,
        "total_keywords": len(terms),
    }


if __name__ == "__main__":
    sample_resume = """
    EXPERIENCE
    Led machine learning platform roadmap, working with engineering teams
    on MLOps and model monitoring. Drove adoption of LLMs across the org.
    """
    sample_parsed_jd = {
        "required_skills": ["machine learning", "MLOps", "LLMs", "AI safety"],
        "preferred_skills": ["agentic AI systems"],
        "keywords": ["roadmap", "responsible AI"],
    }

    result = run_ats_agent(sample_resume, sample_parsed_jd)
    print(result)
