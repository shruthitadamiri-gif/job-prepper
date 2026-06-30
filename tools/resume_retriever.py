import os
import sys
import chromadb
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_PATH = os.path.join(PROJECT_ROOT, "chroma_db")


def _get_or_build_collection(client):
    try:
        return client.get_collection("resume")
    except Exception:
        sys.path.insert(0, PROJECT_ROOT)
        from resume_store import build_resume_store
        print("Resume collection not found — rebuilding from resume.txt...")
        build_resume_store()
        return client.get_collection("resume")


def retrieve_relevant_chunks(query: str, top_k: int = 5) -> list[str]:
    """
    Takes a query string (built from JD keywords) and returns
    the most semantically relevant chunks from the resume store.
    Auto-rebuilds the collection if it doesn't exist.
    """
    model = SentenceTransformer("all-MiniLM-L6-v2")
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = _get_or_build_collection(client)

    query_embedding = model.encode([query]).tolist()
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=top_k
    )

    return results["documents"][0]


def build_query_from_jd(parsed_jd: dict) -> str:
    """
    Builds a retrieval query from the structured JD output.
    Combines role, skills, and keywords for best semantic match.
    """
    parts = [
        parsed_jd.get("role", ""),
        parsed_jd.get("seniority", ""),
        " ".join(parsed_jd.get("required_skills", [])),
        " ".join(parsed_jd.get("keywords", []))
    ]
    return " ".join(p for p in parts if p)


if __name__ == "__main__":
    # Simulate what the orchestrator will pass in
    test_parsed_jd = {
        "role": "Senior AI Product Manager",
        "company": "Google DeepMind",
        "seniority": "senior",
        "required_skills": ["machine learning", "MLOps", "LLMs", "model monitoring"],
        "keywords": ["AI product manager", "agentic AI", "responsible AI", "roadmap"]
    }

    print("Building retrieval query from JD...")
    query = build_query_from_jd(test_parsed_jd)
    print(f"Query: {query}\n")

    print("Retrieving relevant resume chunks...")
    chunks = retrieve_relevant_chunks(query)

    print(f"Retrieved {len(chunks)} chunks:\n")
    for i, chunk in enumerate(chunks):
        print(f"--- Chunk {i+1} ---")
        print(chunk[:200])
        print()
