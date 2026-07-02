import os
import anthropic
from dotenv import load_dotenv
from tools.jd_parser import parse_jd

load_dotenv()

client = anthropic.Anthropic()

RESUME_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resume.txt")


def _load_resume() -> str:
    with open(RESUME_PATH, "r") as f:
        return f.read()


def run_resume_agent(jd_text: str, parsed_jd: dict, missing_keywords: list[str] | None = None) -> str:
    """
    Takes a raw JD and its parsed version, reads resume.txt directly,
    and generates a tailored resume using Claude.

    If missing_keywords is provided (from ATS gap analysis), the prompt
    explicitly instructs Claude to weave those terms into the resume
    wherever they truthfully fit the candidate's experience.
    """
    context = _load_resume()

    # Step 2: Build ATS gap instructions if we have missing keywords
    if missing_keywords:
        gap_list = "\n".join(f"  - {kw}" for kw in missing_keywords)
        ats_section = f"""
ATS KEYWORD GAP — MANDATORY COVERAGE:
The previous resume version was missing these keywords that appear in the JD.
You MUST weave AT LEAST 80% of these into the resume naturally — embed them
in bullet points and skills where they truthfully describe the candidate's
experience. Do NOT add them as a list or force them awkwardly; every use
must read as authentic context.

Missing keywords to incorporate:
{gap_list}
"""
    else:
        ats_section = ""

    # Step 3: Generate tailored resume
    prompt = f"""You are an expert AI PM resume writer.

Your job is to tailor the candidate's resume for this specific role.

STRICT RULES:
- Only use facts, experiences, and metrics present in the resume chunks below
- Never invent experience, metrics, or skills that are not in the chunks
- Mirror the language and keywords from the job description where truthful
- Lead every bullet with a metric or outcome where one exists
- Reorder bullets so the most relevant experience comes first
{ats_section}
JOB DESCRIPTION:
{jd_text}

CANDIDATE'S RELEVANT EXPERIENCE (retrieved from resume):
{context}

Write a tailored resume section covering Work Experience and Skills.
Format cleanly with the company, role, dates, and bullet points.
Do not include a summary or education section."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    return message.content[0].text


if __name__ == "__main__":
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

    print("Parsing JD...")
    parsed = parse_jd(test_jd)

    print("Running resume agent...")
    result = run_resume_agent(test_jd, parsed)

    print("\n--- TAILORED RESUME OUTPUT ---\n")
    print(result)
