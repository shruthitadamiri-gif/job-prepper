import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic()

def run_evaluator(
    resume_output: str,
    prep_output: str,
    jd_text: str,
    parsed_jd: dict
) -> dict:
    """
    Scores the resume and prep outputs against three dimensions.
    Returns scores and feedback. If any score < 7, flags for retry.
    """
    role = parsed_jd.get("role", "this role")
    keywords = ", ".join(parsed_jd.get("keywords", []))

    prompt = f"""You are a strict quality evaluator for AI-generated job application materials.

Evaluate the resume output below against this job description.
Score each dimension from 0-10. Be honest and critical.

JOB DESCRIPTION:
{jd_text}

RESUME OUTPUT TO EVALUATE:
{resume_output}

Score these three dimensions:

1. JD RELEVANCE (0-10)
Does the resume mirror the JD language and prioritize the most relevant experience?
Key keywords to check: {keywords}

2. FACTUAL ACCURACY (0-10)
Does the resume only use facts that would be in the candidate's actual background?
Penalize any invented metrics, roles, or experiences.

3. ATS KEYWORD COVERAGE (0-10)
How well does the resume incorporate the important keywords from the JD?

Return ONLY a valid JSON object with this exact structure:
{{
  "relevance_score": <0-10>,
  "accuracy_score": <0-10>,
  "ats_score": <0-10>,
  "overall_score": <average of the three>,
  "passes": <true if all scores >= 7, false otherwise>,
  "feedback": {{
    "relevance": "<one sentence of specific feedback>",
    "accuracy": "<one sentence of specific feedback>",
    "ats": "<one sentence of specific feedback>"
  }},
  "retry_reason": "<if passes is false, explain what needs to improve. Empty string if passes is true>"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    result = json.loads(raw)
    return result


if __name__ == "__main__":
    from tools.jd_parser import parse_jd
    from agents.resume_agent import run_resume_agent
    from agents.prep_agent import run_prep_agent

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

    Nice to have:
    - Background in data science or ML engineering
    - Experience with agentic AI systems
    - Knowledge of responsible AI practices
    """

    print("Step 1: Parsing JD...")
    parsed = parse_jd(test_jd)

    print("Step 2: Running resume agent...")
    resume_output = run_resume_agent(test_jd, parsed)

    print("Step 3: Running prep agent...")
    prep_output = run_prep_agent(test_jd, parsed)

    print("Step 4: Running evaluator...")
    result = run_evaluator(resume_output, prep_output, test_jd, parsed)

    print("\n--- EVALUATOR OUTPUT ---\n")
    print(json.dumps(result, indent=2))

    if result["passes"]:
        print("\n✅ Output passes quality threshold — ready for human review")
    else:
        print(f"\n❌ Output needs improvement: {result['retry_reason']}")
