import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
TABLE = "history"


def _client():
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def save_entry(parsed_jd: dict, eval_result: dict, resume_output: str, jd_text: str) -> str:
    entry_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    entry = {
        "id": entry_id,
        "date_created": datetime.now().isoformat(timespec="seconds"),
        "company": parsed_jd.get("company", "Unknown"),
        "role": parsed_jd.get("role", "Unknown"),
        "location": parsed_jd.get("location", ""),
        "salary_range": parsed_jd.get("salary_range", ""),
        "relevance_score": int(eval_result.get("overall_score", 0)),
        "applied": False,
        "resume_output": resume_output,
        "jd_text": jd_text,
    }
    try:
        _client().table(TABLE).insert(entry).execute()
    except Exception as e:
        raise RuntimeError(f"Supabase insert failed: {e}") from e
    return entry_id


def load_history() -> list:
    resp = _client().table(TABLE).select("*").order("date_created", desc=True).execute()
    return resp.data or []


def set_applied(entry_id: str, applied: bool) -> None:
    _client().table(TABLE).update({"applied": applied}).eq("id", entry_id).execute()


def delete_entry(entry_id: str) -> None:
    _client().table(TABLE).delete().eq("id", entry_id).execute()
