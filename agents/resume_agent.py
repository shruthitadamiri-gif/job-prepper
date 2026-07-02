import os
import anthropic
from dotenv import load_dotenv
from tools.jd_parser import parse_jd

load_dotenv()

client = anthropic.Anthropic()

RESUME_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resume.txt")

FORMAT_RULES = """
OUTPUT FORMAT — FOLLOW EXACTLY, NO EXCEPTIONS:

SKILLS
AI/ML & Data: [comma-separated skills]
Product: [comma-separated skills]
Tools: [comma-separated skills]

EXPERIENCE

[Company] | [Title] | [Location] | [Dates]
- [Bullet starting with metric or outcome]
- [Bullet]
- [Bullet]

[Next company, same pattern]

Rules:
- Section headers in ALL CAPS with no extra punctuation
- Job title lines: Company | Title | Location | Dates (pipe-separated, no bold markers)
- Every bullet starts with "- "
- No sub-headers, no summaries, no education section, no extra blank lines between bullets
- Keep every company and role present in the source resume — do not drop any
"""


def _load_resume() -> str:
    with open(RESUME_PATH, "r") as f:
        return f.read()


def run_resume_agent(
    jd_text: str,
    parsed_jd: dict,
    missing_keywords: list[str] | None = None,
    current_resume: str | None = None,
) -> str:
    """
    Generates a tailored resume for the given JD.

    On first run, uses resume.txt as the source.
    On regeneration, uses current_resume as the base so coverage
    improvements are cumulative rather than starting from scratch.

    missing_keywords: ATS gap keywords to weave in (from latest ATS result).
    """
    source = current_resume if current_resume else _load_resume()

    if missing_keywords:
        gap_list = "\n".join(f"  - {kw}" for kw in missing_keywords)
        ats_section = f"""
ATS KEYWORD GAP — MANDATORY:
The current resume is missing these JD keywords. Weave AT LEAST 90% of them
into bullets and skills lines where they truthfully apply. Do not add them
as a standalone list. Every use must read as authentic experience.

Missing keywords:
{gap_list}
"""
    else:
        ats_section = ""

    prompt = f"""You are an expert resume writer specializing in AI/ML product roles.

TASK: Rewrite the resume below to be a stronger match for this job description.

STRICT CONTENT RULES:
- Only use facts, experiences, and metrics already present in the source resume
- Never invent experience, metrics, titles, or skills
- Mirror the language and keywords from the JD where truthful
- Lead every bullet with a metric or outcome where one exists in the source
- Reorder bullets within each role so the most JD-relevant ones come first
- Keep ALL companies and roles — do not drop any position
{ats_section}
{FORMAT_RULES}
JOB DESCRIPTION:
{jd_text}

SOURCE RESUME:
{source}

Output only the resume. No commentary, no preamble."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1800,
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
    """

    print("Parsing JD...")
    parsed = parse_jd(test_jd)

    print("Running resume agent...")
    result = run_resume_agent(test_jd, parsed)

    print("\n--- TAILORED RESUME OUTPUT ---\n")
    print(result)
