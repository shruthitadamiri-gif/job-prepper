import os
import time
import anthropic
from dotenv import load_dotenv
from tools.llm_json import parse_llm_json
from tools.usage_logger import log_usage

load_dotenv()

client = anthropic.Anthropic(max_retries=4)


def run_evaluator(
    resume_output: str,
    source_resume: str,
    jd_text: str,
    parsed_jd: dict,
    session_id: str = "unknown",
) -> dict:
    """
    Scores the tailored resume against three dimensions.
    source_resume is the original resume.txt content — used as ground truth
    for factual accuracy so the evaluator can detect invented claims.
    Returns scores, feedback, and a list of any unsupported claims found.
    """
    role = parsed_jd.get("role", "this role")
    keywords = ", ".join(parsed_jd.get("keywords", []))

    prompt = f"""You are a strict quality evaluator for AI-generated job application materials.

Evaluate the tailored resume below against this job description.
Score each dimension from 0-10. Be honest and critical.

JOB DESCRIPTION:
{jd_text}

SOURCE RESUME (ground truth — the only facts the tailored resume may use):
{source_resume}

TAILORED RESUME TO EVALUATE:
{resume_output}

Score these three dimensions:

1. JD RELEVANCE (0-10)
Does the resume mirror the JD language and prioritize the most relevant experience?
Key keywords to check: {keywords}

2. FACTUAL ACCURACY (0-10)
Every metric, job title, company name, date, and outcome claim in the tailored resume
must be directly traceable to the SOURCE RESUME above. Check each specific claim:
- If ALL claims are fully supported by the source: score 7-10 based on precision
- If ANY claim is invented, exaggerated, or not present in the source: score MUST be 4 or lower
List every unsupported claim verbatim in the "unsupported_claims" array.
An empty array means the tailored resume is factually clean.

3. ATS KEYWORD COVERAGE (0-10)
How well does the resume incorporate the important keywords from the JD?

Return ONLY a valid JSON object with this exact structure:
{{
  "relevance_score": <0-10>,
  "accuracy_score": <0-10>,
  "ats_score": <0-10>,
  "overall_score": <average of the three, rounded to 2 decimal places>,
  "passes": <true if all scores >= 7, false otherwise>,
  "unsupported_claims": ["<exact claim text from the tailored resume that is not in the source>"],
  "feedback": {{
    "relevance": "<one sentence of specific feedback>",
    "accuracy": "<one sentence of specific feedback — name any unsupported claims>",
    "ats": "<one sentence of specific feedback>"
  }},
  "retry_reason": "<if passes is false, explain what needs to improve. Empty string if passes is true>"
}}"""

    _model = "claude-sonnet-4-6"
    _t0 = time.monotonic()
    message = client.messages.create(
        model=_model,
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    log_usage(session_id, "evaluator", _model, message, int((time.monotonic() - _t0) * 1000))

    return parse_llm_json(message.content[0].text)


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from tools.jd_parser import parse_jd
    from agents.resume_agent import run_resume_agent

    RESUME_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resume.txt")
    with open(RESUME_PATH) as f:
        source_resume = f.read()

    test_jd = """
    Senior AI Product Manager - Google DeepMind

    We are looking for a Senior AI Product Manager to lead our machine learning
    platform products. You will own the roadmap for our ML infrastructure tools,
    work closely with research and engineering teams, and drive adoption across
    the organization.

    Requirements:
    - 5+ years of product management experience
    - Strong understanding of machine learning concepts and MLOps
    - Experience with LLMs, model monitoring, and AI safety
    - Proven ability to work with cross-functional engineering teams
    - Track record of shipping AI products at scale
    """

    print("Parsing JD...")
    parsed = parse_jd(test_jd)

    print("Running resume agent...")
    resume_output = run_resume_agent(test_jd, parsed)

    # Plant a fake metric to verify unsupported_claims catches it
    resume_with_fake = resume_output + "\n- Grew revenue by $999M through AI transformation"

    print("Running evaluator with planted fake metric...")
    result = run_evaluator(resume_with_fake, source_resume, test_jd, parsed)

    import json
    print("\n--- EVALUATOR OUTPUT ---\n")
    print(json.dumps(result, indent=2))
    print(f"\nunsupported_claims: {result.get('unsupported_claims', [])}")
    print(f"accuracy_score: {result['accuracy_score']} (should be <= 4 due to fake metric)")
