import os
import chromadb
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------
# YOUR RESUME — edit this whenever your resume changes,
# then re-run: python3 resume_store.py
# The vector database will rebuild automatically.
# ---------------------------------------------------------------
RESUME_TEXT = """
SHRUTHI TADAMIRI
Boston, MA | shruthi.tadamiri@gmail.com | 860-992-7814 | linkedin.com/in/shruthi-tadamiri

SUMMARY
Principal AI/ML Product Manager with 5+ years owning the end-to-end lifecycle of production ML
systems at Verizon. Background as a data scientist enables deep technical fluency — bridging
engineering teams and business stakeholders to ship AI products that drive measurable outcomes.
Reduced pipeline failure detection from 14 days to real-time and delivered $127M+ in combined
cost savings and revenue. Experienced in Agile product ownership, cross-functional alignment,
and responsible AI deployment.

EXPERIENCE

Verizon — Principal Engineer, Tech Product Management | Boston, MA | 2021–Present

Model Monitoring & Optimization (MMO) Platform
Led product vision, roadmap, and cross-functional delivery of MMO — Verizon's internal AI
observability platform monitoring 346+ ML models and 70+ data insights across Enterprise Personalization Platform, Force to
Load, AI Coach, and Churn programs. Reduced pipeline failure detection from 14 days to
near-real-time by shipping automated alerting and intelligent JIRA ticket creation routed to
the right team — cutting total system downtime from 28 days to ~5 days. Served as Scrum Master
and Product Owner for the ACT (Agile Core Team); led grooming, sprint planning, and backlog
management. ACT recognized as best-performing team for 100% sprint delivery across all quarters
in 2023. Drove stakeholder alignment across 8+ teams: AI&D, ML Engineering, GTS, Data
Engineering, SOI API, Ops Excellence, and Product — securing buy-in for a standard monitoring
framework adopted enterprise-wide. VP-nominated Spotlight Award (2025) for leading
MLOps/Data Observability effort enabling ML Model Performance and Data Quality Monitoring
and intelligent pipeline alerting at scale.

NBx Model Portfolio & AI Product Delivery
Part of team that led delivery of 75+ predictive models powering Next Best Action decisioning across 30+ Sales
and Service intents — enabling $127.3M in combined cost avoidance and revenue in 2023. Exceeded
2024 KPIs: CVO Volume CV by 13% (3.5M vs 3.1M) and cost savings CV by 35% ($60.5M vs $44.7M).
Managed model lifecycle from ideation through deployment: deployed 39 new models, enhanced 40
existing models, re-used 65 models in new implementations (2021–2023). Led Agent Specialization
Model Refresh — analyzed performance metrics, identified skewness in predictive output, and
reduced bias by 20%. Established AI/ML benefits measurement framework mapping models to benefit
streams and KPIs — used in monthly, quarterly, and annual leadership readouts.

Agentic AI & AICO Program (2025)
Key technical partner for IVR team on Agentic AI integration — leading deployment of Dynamic
Decisioning Automation and IVR Banner Process Automation for Next Gen IVR capabilities.
Validated 50,000+ records as Human-in-the-Loop reviewer for ConvoIQ, ensuring high-fidelity
AI outputs and mitigating risk of inaccurate AI in customer-facing experiences. Served as key
technical partner for integration and deployment of Agentic AI capabilities translating complex
business needs into automated, smarter customer experiences.

Channel Orchestration & No Intent Experience (2025)
Orchestrated cross-functional strategy for Next Best Channel program — collaborated with PEGA,
IVR, Chatbot, AI&D, and ConvoIQ teams to create unified customer routing strategy designed for
Agentic AI adoption. Initiated strategic reassessment of AI product monitoring, documented
critical operational gaps, and presented alternatives to senior leadership to define the path
forward for resilient AI operations. Successfully resolved two complex high-visibility customer
service escalations related to No Intent Model and CS100 High Risk Customers — requiring swift
cross-functional coordination to pinpoint root cause and mitigate customer impact. Helped define
core concept and strategic roadmap for Agentic AI Central Brain Hub — a unified solution for
seamless customer engagement across all touchpoints. VP-nominated Spotlight Award (2026) for
collaboration and teamwork on Contact Orchestrator project.

RepTrak — Data Scientist | 2018–2020
Built NLP and sentiment analysis models to quantify brand reputation metrics for Fortune 500
clients. Delivered client-facing analytics dashboards translating model outputs into actionable
business recommendations. Transitioned from pure data science into client-facing product work,
developing skills in requirements gathering, stakeholder communication, and insight delivery.

EDUCATION
Master of Science, Business Analystics & Project Management from University of Connecticut (2019)
Bachelor of Engineering, Electronics & Communication from VTU, India (2010)

SKILLS
Product Management: Roadmapping, Agile/Scrum, backlog management, stakeholder alignment,
KPI frameworks, responsible AI, product vision, OKRs, sprint planning
Technical: ML model lifecycle, data observability, MLOps, NLP, Python, SQL, Pega, JIRA,
LangGraph, ChromaDB, vector databases, agentic AI systems
AI/ML: Model monitoring, predictive modeling, recommender systems, LLMs, agentic AI,
RAG, A/B testing, Human-in-the-Loop systems, AI governance

AWARDS
VP-nominated Spotlight Award 2025 — Quality/Process Improvement (MLOps/Data Observability)
VP-nominated Spotlight Award 2026 — Living the Credo (Contact Orchestrator collaboration)
VP-nominated Spotlight Award 2023 — Quality/Process Improvement (ACT launch)
Best Performing ACT — 100% sprint delivery, all quarters 2023
"""

# ---------------------------------------------------------------
# No need to edit anything below this line
# ---------------------------------------------------------------

def chunk_resume(text, chunk_size=300):
    """Split resume into overlapping chunks for better retrieval."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - 50):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks

def build_resume_store():
    """Embed resume chunks and store in ChromaDB."""
    print("Loading embedding model...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    print("Chunking resume...")
    chunks = chunk_resume(RESUME_TEXT)
    print(f"Created {len(chunks)} chunks")

    print("Setting up ChromaDB...")
    client = chromadb.PersistentClient(path="./chroma_db")

    # Delete existing collection if rebuilding
    try:
        client.delete_collection("resume")
    except:
        pass

    collection = client.create_collection("resume")

    print("Embedding and storing chunks...")
    embeddings = model.encode(chunks).tolist()

    collection.add(
        documents=chunks,
        embeddings=embeddings,
        ids=[f"chunk_{i}" for i in range(len(chunks))]
    )

    print(f"\nDone! {len(chunks)} chunks stored in ChromaDB.")
    return collection

def retrieve_relevant_chunks(query, top_k=5):
    """Retrieve the most relevant resume chunks for a given JD query."""
    model = SentenceTransformer("all-MiniLM-L6-v2")
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_collection("resume")

    query_embedding = model.encode([query]).tolist()
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=top_k
    )

    return results["documents"][0]

if __name__ == "__main__":
    build_resume_store()

    # Quick test — make sure retrieval is working
    print("\nTesting retrieval...")
    test_query = "AI product manager machine learning agentic systems"
    chunks = retrieve_relevant_chunks(test_query)
    print(f"Top chunk retrieved:\n{chunks[0][:300]}...")
    print("\nResume store is ready.")
