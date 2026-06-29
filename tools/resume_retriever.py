import os
import chromadb
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

def retrieve_relevant_chunks(query: str, top_k: int = 5) -> list[str]:
    """
    Takes a query string (built from JD keywords) and returns
    the most semantically relevant chunks from the resume store.
    """
    model = SentenceTransformer("all-MiniLM-L6-v2")
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_collection("resume")

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
