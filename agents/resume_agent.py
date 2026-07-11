import os
import re
import time
import anthropic
from dotenv import load_dotenv
from tools.jd_parser import parse_jd
from tools.usage_logger import log_usage

load_dotenv()

client = anthropic.Anthropic(max_retries=4)

RESUME_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resume.txt")

FORMAT_RULES = """
OUTPUT FORMAT — FOLLOW EXACTLY, NO EXCEPTIONS:

[Full name]
[Phone] | [Email] | [LinkedIn] | [Location]

SUMMARY
[2-3 sentence narrative tailored to the JD. Must be a high-level overview — do NOT repeat specific metrics, project names, or phrases that appear in the experience bullets below. The summary and bullets should complement each other, not duplicate each other.]

SKILLS
AI/ML & Data: [comma-separated skills]
Product: [comma-separated skills]
Tools: [comma-separated skills]

EXPERIENCE

[Company] | [Title] | [Location] | [Dates]
- [Bullet starting with metric or outcome]
- [Bullet]
- [Bullet]

[Next company, same pattern — keep ALL companies from source resume]

EDUCATION
[Degree] — [University] ([GPA if present]) | [Year]
[Degree] — [University] | [Year]

Rules:
- Section headers in ALL CAPS with no extra punctuation
- Name on its own line, contact info on the next line (no labels)
- Job title lines: Company | Title | Location | Dates (pipe-separated, no bold markers)
- Every bullet starts with "- "
- No extra blank lines between bullets within a role
- Do not drop any company or role from the source resume
- Copy name, contact, and education exactly from the source — do not alter them
- Do not add new bullets that don't exist in the source resume. Preserve all metrics and specifics — do not compress or summarise existing bullets.
"""


def _load_resume() -> str:
    with open(RESUME_PATH, "r") as f:
        return f.read()


def _count_source_items() -> dict[str, int]:
    """
    Parse resume.txt and return {company_name: paragraph_count} for each role.
    Used to enforce exact per-role bullet counts in the generated resume.
    """
    text = _load_resume()
    counts: dict[str, int] = {}
    current_company: str | None = None
    item_count = 0
    in_experience = False

    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.upper() == "EXPERIENCE":
            in_experience = True
            continue
        if s.upper() in ("EDUCATION", "SKILLS", "SUMMARY", "CERTIFICATIONS", "AWARDS"):
            if current_company and item_count:
                counts[current_company] = item_count
            in_experience = False
            current_company = None
            item_count = 0
            continue
        if not in_experience:
            continue
        # Role header: "Company | Title | Location | Dates"
        if "|" in s and re.search(r"\b(20\d\d|Present)\b", s):
            if current_company and item_count:
                counts[current_company] = item_count
            current_company = s.split("|")[0].strip()
            item_count = 0
        elif current_company:
            item_count += 1

    if current_company and item_count:
        counts[current_company] = item_count

    return counts


def run_resume_agent(
    jd_text: str,
    parsed_jd: dict,
    missing_keywords: list[str] | None = None,
    current_resume: str | None = None,
    evidence_chunks: list[dict] | None = None,
    session_id: str = "unknown",
) -> str:
    """
    Generates a tailored resume for the given JD.

    On first run, uses resume.txt as the source. evidence_chunks (retrieved
    from the career corpus) are injected as supplementary evidence to help
    the LLM write stronger, more specific bullets.

    On regeneration, uses current_resume as the base so coverage improvements
    are cumulative. evidence_chunks are not re-retrieved on retry.

    missing_keywords: ATS gap keywords to weave in (from latest ATS result).
    """
    source = current_resume if current_resume else _load_resume()

    bullet_cap_section = ""

    if missing_keywords:
        # Cap to 6 most relevant to avoid bloat and awkward insertions
        top_kws = missing_keywords[:6]
        gap_list = "\n".join(f"  - {kw}" for kw in top_kws)
        ats_section = f"""
ATS KEYWORD GAP:
The resume is missing these high-priority JD keywords. Weave them into
existing bullets or the skills section where they fit naturally and truthfully.
Do NOT add new bullets or expand existing ones to fit them in — only substitute
or append to language that already exists. Skip any keyword that cannot be
added without sounding forced.

Missing keywords:
{gap_list}
"""
    else:
        ats_section = ""

    if evidence_chunks:
        evidence_lines = []
        for chunk in evidence_chunks:
            evidence_lines.append(f"[Source: {chunk['source']}]\n{chunk['text']}")
        evidence_section = (
            "\nADDITIONAL EVIDENCE from the candidate's project history:\n"
            "Use these to strengthen and specify bullets where they apply truthfully.\n"
            "Never invent claims not present in the source resume or evidence below.\n\n"
            + "\n\n".join(evidence_lines)
            + "\n"
        )
    else:
        evidence_section = ""

    prompt = f"""You are an expert resume writer specializing in AI/ML product roles.

TASK: Rewrite the resume below to be a stronger match for this job description.

STRICT CONTENT RULES:
- Only use facts, experiences, and metrics already present in the source resume or the additional evidence below
- Never invent experience, metrics, titles, or skills
- Mirror the language and keywords from the JD where truthful
- Lead every bullet with a metric or outcome where one exists in the source
- Reorder bullets within each role so the most JD-relevant ones come first
- Keep ALL companies and roles — do not drop any position
{bullet_cap_section}{ats_section}{evidence_section}
{FORMAT_RULES}
JOB DESCRIPTION:
{jd_text}

SOURCE RESUME:
{source}

Output only the resume. No commentary, no preamble, no markdown code blocks."""

    _model = "claude-sonnet-4-6"
    _t0 = time.monotonic()
    message = client.messages.create(
        model=_model,
        max_tokens=1400,
        messages=[{"role": "user", "content": prompt}]
    )
    log_usage(session_id, "resume_agent", _model, message, int((time.monotonic() - _t0) * 1000))

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
