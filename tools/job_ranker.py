import os
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

RESUME_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resume.txt")

_model = None


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _load_resume() -> str:
    with open(RESUME_PATH, "r") as f:
        return f.read()


def rank_jobs(jobs: list[dict]) -> list[dict]:
    """
    Adds a 'relevance_score' (0-100) to each job based on cosine similarity
    between the job description snippet and the resume. Returns sorted list.
    """
    if not jobs:
        return jobs

    model = _get_model()
    resume_text = _load_resume()
    resume_embedding = model.encode([resume_text])

    snippets = [j.get("description_snippet", j.get("title", "")) for j in jobs]
    job_embeddings = model.encode(snippets)

    scores = cosine_similarity(resume_embedding, job_embeddings)[0]

    for job, score in zip(jobs, scores):
        job["relevance_score"] = round(float(score) * 100, 1)

    return sorted(jobs, key=lambda j: j["relevance_score"], reverse=True)
