import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic()

def run_prep_agent(jd_text: str, parsed_jd: dict) -> str:
    """
    Generates interview prep topics and likely questions
    based on the JD and the candidate's background.
    """
    role = parsed_jd.get("role", "this role")
    company = parsed_jd.get("company", "this company")
    skills = ", ".join(parsed_jd.get("required_skills", []))
    keywords = ", ".join(parsed_jd.get("keywords", []))

    prompt = f"""You are an expert technical interview coach specializing in AI Product Management roles.

The candidate is Shruthi Tadamiri — a Principal AI/ML PM at Verizon with 5+ years experience.
Her background: led Model Monitoring platform (346+ ML models), owned NBx model portfolio 
($127M impact), working on Agentic AI and Channel Orchestration. Prior data scientist at RepTrak.

She is interviewing for: {role} at {company}

Job requires: {skills}
Key keywords from JD: {keywords}

Generate two things:

1. TOP 8 PREPARATION TOPICS
For each topic: name it, explain in 2 sentences why it matters for THIS specific role,
and give one concrete thing she should prepare from her own experience.

2. LIKELY INTERVIEW QUESTIONS (12 total)
- 3 behavioral (leadership, stakeholder, conflict)
- 3 technical AI/ML (specific to this JD)
- 3 product sense (strategy, prioritization, metrics)
- 3 situational (how would you handle...)

For each question add a one-line hint: which part of her background to draw from.

Format clearly with headers and numbered lists."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    return message.content[0].text


if __name__ == "__main__":
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

    Nice to have:
    - Background in data science or ML engineering
    - Experience with agentic AI systems
    - Knowledge of responsible AI practices
    """

    print("Parsing JD...")
    parsed = parse_jd(test_jd)

    print("Running interview prep agent...")
    result = run_prep_agent(test_jd, parsed)

    print("\n--- INTERVIEW PREP OUTPUT ---\n")
    print(result)
