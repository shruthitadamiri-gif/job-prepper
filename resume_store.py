import os
import chromadb
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------
# YOUR RESUME — edit resume.txt whenever your resume changes,
# then re-run: python3 resume_store.py
# The vector database will rebuild automatically.
# ---------------------------------------------------------------
RESUME_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resume.txt")

def load_resume_text() -> str:
    with open(RESUME_PATH, "r") as f:
        return f.read()

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
    chunks = chunk_resume(load_resume_text())
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
