import os
import anthropic
from dotenv import load_dotenv
from tools.jd_parser import parse_jd
from tools.resume_retriever import retrieve_relevant_chunks, build_query_from_jd

load_dotenv()

client = anthropic.Anthropic()

def run_resume_agent(jd_text: str, parsed_jd: dict) -> str:
    """
    Takes a raw JD and its parsed version, retrieves relevant resume
    chunks, and generates a tailored resume using Claude.
    """
    # Step 1: Build query and retrieve relevant chunks
    query = build_query_from_jd(parsed_jd)
    chunks = retrieve_relevant_chunks(query)
    context = "\n\n".join(chunks)

    # Step 2: Generate tailored resume
    prompt = f"""You are an expert AI PM resume writer.

Your job is to tailor the candidate's resume for this specific role.

STRICT RULES:
- Only use facts, experiences, and metrics present in the resume chunks below
- Never invent experience, metrics, or skills that are not in the chunks
- Mirror the language and keywords from the job description where truthful
- Lead every bullet with a metric or outcome where one exists
- Reorder bullets so the most relevant experience comes first

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
