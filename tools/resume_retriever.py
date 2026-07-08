"""
Career corpus retriever.

Single source of truth for embedding model, retrieval, and JD query building.
resume_store.py imports _get_model from here to share the cached singleton.
"""

import os
import sys
import chromadb
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_PATH = os.path.join(PROJECT_ROOT, "chroma_db")
COLLECTION_NAME = "career_corpus"

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Cached model singleton — loaded once, reused across all calls."""
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _ensure_index() -> None:
    """Trigger a rebuild if the corpus has changed since last index."""
    sys.path.insert(0, PROJECT_ROOT)
    from resume_store import needs_rebuild, build_corpus_store  # lazy to avoid circular import
    if needs_rebuild():
        print("Corpus changed or index missing — rebuilding...")
        build_corpus_store()


def retrieve_relevant_chunks(query: str, top_k: int = 8) -> list[dict]:
    """
    Return the top_k most relevant chunks from the career corpus.

    Each element: {"text": str, "source": str}
    where source is the repo-relative path of the file the chunk came from
    (e.g. "career_corpus/projects/mmo_platform.md").

    Auto-rebuilds the index if any corpus file has changed.
    """
    _ensure_index()

    model = _get_model()
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    try:
        collection = client.get_collection(COLLECTION_NAME)
    except Exception:
        from resume_store import build_corpus_store
        build_corpus_store()
        collection = client.get_collection(COLLECTION_NAME)

    count = collection.count()
    if count == 0:
        return []

    query_embedding = model.encode([query]).tolist()
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=min(top_k, count),
        include=["documents", "metadatas"],
    )

    return [
        {"text": text, "source": meta.get("source", "unknown")}
        for text, meta in zip(results["documents"][0], results["metadatas"][0])
    ]


def build_query_from_jd(parsed_jd: dict) -> str:
    """Build a retrieval query from the structured JD output."""
    parts = [
        parsed_jd.get("role", ""),
        parsed_jd.get("seniority", ""),
        " ".join(parsed_jd.get("required_skills", [])),
        " ".join(parsed_jd.get("keywords", [])),
    ]
    return " ".join(p for p in parts if p)


if __name__ == "__main__":
    test_parsed_jd = {
        "role": "Senior AI Product Manager",
        "seniority": "senior",
        "required_skills": ["LLMs", "agentic AI", "MLOps", "model monitoring"],
        "keywords": ["AI product", "agentic decisioning", "responsible AI"],
    }

    query = build_query_from_jd(test_parsed_jd)
    print(f"Query: {query}\n")

    chunks = retrieve_relevant_chunks(query, top_k=4)
    print(f"Retrieved {len(chunks)} chunks:")
    for i, c in enumerate(chunks, 1):
        print(f"\n[{i}] Source: {c['source']}")
        print(c["text"][:200])
