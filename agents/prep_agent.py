import os
import anthropic
from dotenv import load_dotenv
from tools.web_search import search_interview_questions
from tools.llm_json import parse_llm_json

load_dotenv()

client = anthropic.Anthropic(max_retries=4)

ROUND_EMPHASIS = {
    "recruiter_screen": (
        "Focus on narrative, compensation expectations, logistics (remote/hybrid/relocation), "
        "and why this role/company now. Behavioral and Situational questions should dominate."
    ),
    "hiring_manager": (
        "Balance product sense, cross-functional leadership, and specific examples of shipping "
        "AI/ML products. Mix Behavioral and Product Sense questions."
    ),
    "technical": (
        "Emphasise AI/ML system design, MLOps, model monitoring, agentic AI architecture, "
        "and hands-on data/ML depth from her background. Technical AI/ML questions should dominate."
    ),
    "onsite_loop": (
        "Full mix across all categories — include one case study / product design question, "
        "one system design question, and at least two behavioral questions."
    ),
}


def run_prep_agent(
    jd_text: str,
    parsed_jd: dict,
    round: str = "hiring_manager",
    invite_context: str = "",
) -> dict:
    """
    Generates a structured interview prep guide with topic tags and
    2-3 answer options per question. Augments with real interview
    questions from the web via Tavily. Returns a dict (not a string).
    """
    role = parsed_jd.get("role", "this role")
    company = parsed_jd.get("company", "this company")
    skills = ", ".join(parsed_jd.get("required_skills", []))
    keywords = ", ".join(parsed_jd.get("keywords", []))

    round_label = round.replace("_", " ").title()
    round_emphasis = ROUND_EMPHASIS.get(round, ROUND_EMPHASIS["hiring_manager"])

    invite_section = (
        f"\nINTERVIEW INVITE / RECRUITER EMAIL (treat as ground truth about format and interviewers):\n"
        f"{invite_context}\n"
        if invite_context else ""
    )

    search_result = search_interview_questions(role, company)
    if search_result["success"]:
        web_section = f"""
REAL INTERVIEW QUESTIONS REPORTED ONLINE (Glassdoor, Blind, etc.):
Use these to inform the questions you generate. Set "reported": true for any
question that closely matches something from these sources.

{search_result["context"]}
"""
    else:
        web_section = f"(Web search unavailable: {search_result['message']})"

    prompt = f"""You are an expert technical interview coach specializing in AI Product Management roles.

The candidate is Shruthi Tadamiri — a Principal AI/ML PM at Verizon with 5+ years experience.
Her background: led Model Monitoring platform (346+ ML models), owned NBx model portfolio
($127M impact), working on Agentic AI and Channel Orchestration. Prior data scientist at RepTrak.

She is interviewing for: {role} at {company}
Interview round: {round_label}
Round emphasis: {round_emphasis}

Job requires: {skills}
Key keywords from JD: {keywords}
{invite_section}
{web_section}

Return ONLY a valid JSON object with this exact structure — no markdown, no code fences:

{{
  "prep_topics": [
    {{
      "title": "topic name (3-6 words)",
      "why_it_matters": "2 sentences: why this topic is critical for THIS specific role at THIS company",
      "what_to_prepare": "one concrete thing to prep from Shruthi's own experience"
    }}
  ],
  "questions": [
    {{
      "category": "Behavioral" | "Technical AI/ML" | "Product Sense" | "Situational",
      "topic": "specific topic tag, 2-5 words, e.g. 'MLOps at Scale', 'Stakeholder Alignment', 'RAG Implementation', 'Responsible AI Tradeoffs'",
      "question": "the full interview question",
      "reported": true | false,
      "hint": "one line: which part of Shruthi's background to draw from",
      "answer_options": [
        {{
          "angle": "short label for this answer angle, e.g. 'Lead with impact', 'Lead with process', 'Lead with conflict resolution'",
          "outline": "2-4 sentence answer outline using Shruthi's real experience — specific enough to build from"
        }}
      ]
    }}
  ]
}}

Requirements:
- prep_topics: exactly 8 entries
- questions: exactly 12 entries — 3 Behavioral, 3 Technical AI/ML, 3 Product Sense, 3 Situational
- answer_options: exactly 2 per question (not 3), each a genuinely different angle, outline max 2 sentences
- topic tags must be specific and scannable (not generic like "Leadership" — use "Cross-team Roadmap Conflict" instead)
- reported: true only if the question closely matches something from the web search results above
- All answer outlines must reference Shruthi's actual experience — no generic frameworks"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}]
    )

    return parse_llm_json(message.content[0].text)


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from tools.jd_parser import parse_jd

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

    print("Running interview prep agent with web search...")
    result = run_prep_agent(test_jd, parsed)

    print("\n--- STRUCTURED OUTPUT ---\n")
    print(json.dumps(result, indent=2)[:2000])
