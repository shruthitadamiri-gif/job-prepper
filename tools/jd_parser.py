import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic()

def parse_jd(jd_text: str) -> dict:
    """
    Takes raw job description text and extracts structured data.
    Returns a dict with role, company, skills, seniority, keywords.
    """
    prompt = f"""Extract structured information from this job description.
    
Return ONLY a valid JSON object with these exact keys:
- role: job title (string)
- company: company name (string)  
- seniority: level like "senior", "principal", "director" (string)
- required_skills: list of must-have skills (list of strings)
- preferred_skills: list of nice-to-have skills (list of strings)
- keywords: most important words/phrases to mirror in a resume (list of strings)
- key_responsibilities: top 5 responsibilities in plain English (list of strings)

Job description:
{jd_text}

Return only the JSON. No explanation, no markdown, no code blocks."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    raw = message.content[0].text.strip()
    parsed = json.loads(raw)
    return parsed


if __name__ == "__main__":
    # Quick test with a sample JD
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
    result = parse_jd(test_jd)
    print(json.dumps(result, indent=2))

