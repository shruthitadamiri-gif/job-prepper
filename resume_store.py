"""
Career corpus indexer.

Indexes every .md and .txt file in career_corpus/ plus resume.txt into
ChromaDB, with per-chunk source metadata so retrieval can report which
files contributed evidence.

Hash-based auto-rebuild: if any corpus file is added, edited, or deleted
the next retrieval call triggers a full rebuild automatically.

Run directly to force a rebuild:
    python3 resume_store.py
"""

import os
import glob
import hashlib
import chromadb

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CORPUS_DIR = os.path.join(PROJECT_ROOT, "career_corpus")
RESUME_PATH = os.path.join(PROJECT_ROOT, "resume.txt")
CHROMA_PATH = os.path.join(PROJECT_ROOT, "chroma_db")
HASH_PATH = os.path.join(CHROMA_PATH, "corpus_hash.txt")
COLLECTION_NAME = "career_corpus"


def all_corpus_files() -> list[str]:
    """All .md and .txt files in career_corpus/ plus resume.txt, sorted for stability."""
    files = glob.glob(os.path.join(CORPUS_DIR, "**", "*.md"), recursive=True)
    files += glob.glob(os.path.join(CORPUS_DIR, "**", "*.txt"), recursive=True)
    files.append(RESUME_PATH)
    return sorted(files)


def corpus_hash() -> str:
    """MD5 over all corpus file paths + contents. Any change triggers a rebuild."""
    h = hashlib.md5()
    for path in all_corpus_files():
        h.update(path.encode())
        try:
            with open(path, "rb") as f:
                h.update(f.read())
        except FileNotFoundError:
            pass
    return h.hexdigest()


def stored_hash() -> str:
    try:
        with open(HASH_PATH) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def needs_rebuild() -> bool:
    return stored_hash() != corpus_hash()


def _chunk_text(text: str, chunk_size: int = 300, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks = []
    for i in range(0, max(1, len(words)), chunk_size - overlap):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def _rel_source(path: str) -> str:
    return os.path.relpath(path, PROJECT_ROOT)


def build_corpus_store() -> None:
    """
    Index all corpus files into ChromaDB. Stores source filename as metadata
    on every chunk so retrieval can report which files contributed evidence.
    """
    # Import here to avoid circular dependency (resume_retriever imports us)
    from tools.resume_retriever import _get_model

    print("Building career corpus index...")
    model = _get_model()

    os.makedirs(CHROMA_PATH, exist_ok=True)
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(COLLECTION_NAME)

    texts, metadatas, ids = [], [], []
    chunk_idx = 0

    for path in all_corpus_files():
        try:
            with open(path) as f:
                content = f.read()
        except Exception as e:
            print(f"  Skipping {_rel_source(path)}: {e}")
            continue

        source = _rel_source(path)
        chunks = _chunk_text(content)
        print(f"  {source}: {len(chunks)} chunk(s)")

        for chunk in chunks:
            texts.append(chunk)
            metadatas.append({"source": source})
            ids.append(f"chunk_{chunk_idx}")
            chunk_idx += 1

    if texts:
        embeddings = model.encode(texts).tolist()
        collection.add(
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids,
        )

    with open(HASH_PATH, "w") as f:
        f.write(corpus_hash())

    print(f"Done — {chunk_idx} chunks from {len(all_corpus_files())} files.")


if __name__ == "__main__":
    build_corpus_store()
