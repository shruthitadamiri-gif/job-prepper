import os
import anthropic
from dotenv import load_dotenv
from tools.llm_json import parse_llm_json

load_dotenv()

client = anthropic.Anthropic(max_retries=4)

RESUME_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resume.txt")


def _load_resume() -> str:
    with open(RESUME_PATH, "r") as f:
        return f.read()


def discover_titles() -> dict:
    """
    Reads resume.txt and returns two lists of job titles:
      - direct_fit: titles that closely match current experience
      - worth_exploring: adjacent/emerging titles worth considering

    Each title has a rationale string.

    Returns:
      {
        "direct_fit": [{"title": str, "rationale": str}, ...],
        "worth_exploring": [{"title": str, "rationale": str}, ...]
      }
    """
    resume = _load_resume()

    prompt = f"""You are a career advisor for senior AI/ML product professionals.

Read this resume and suggest job titles to search for.

Return ONLY a valid JSON object with exactly this structure:
{{
  "direct_fit": [
    {{"title": "exact job title to search", "rationale": "one sentence why"}},
    ...
  ],
  "worth_exploring": [
    {{"title": "exact job title to search", "rationale": "one sentence why this adjacent role fits"}},
    ...
  ]
}}

Rules:
- direct_fit: 4-6 titles that are a near-exact match for this person's current level and experience
- worth_exploring: 4-6 adjacent, emerging, or stretch titles this person could credibly apply to
  (e.g. "Forward Deployed Engineer", "AI Solutions Architect", "Head of AI Product")
- Titles should be searchable as-is on job boards — use real market titles, not invented ones
- Do not include seniority prefixes like "Senior" or "Principal" in every title — vary them
- Return only the JSON, no explanation

RESUME:
{resume}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    return parse_llm_json(message.content[0].text)


if __name__ == "__main__":
    result = discover_titles()
    print("DIRECT FIT:")
    for t in result["direct_fit"]:
        print(f"  {t['title']} — {t['rationale']}")
    print("\nWORTH EXPLORING:")
    for t in result["worth_exploring"]:
        print(f"  {t['title']} — {t['rationale']}")
