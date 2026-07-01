import os
import json
from datetime import datetime

HISTORY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "history.json")


def _load() -> list:
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save(entries: list) -> None:
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
        json.dump(entries, f, indent=2)


def save_entry(parsed_jd: dict, eval_result: dict, resume_output: str, jd_text: str) -> str:
    """
    Saves a completed job prep run to history. Returns the new entry's id.
    """
    entry_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    entry = {
        "id": entry_id,
        "date_created": datetime.now().isoformat(timespec="seconds"),
        "company": parsed_jd.get("company", "Unknown"),
        "role": parsed_jd.get("role", "Unknown"),
        "location": parsed_jd.get("location", ""),
        "salary_range": parsed_jd.get("salary_range", ""),
        "relevance_score": eval_result.get("overall_score", 0),
        "applied": False,
        "resume_output": resume_output,
        "jd_text": jd_text,
    }
    entries = _load()
    entries.insert(0, entry)  # newest first
    _save(entries)
    return entry_id


def load_history() -> list:
    return _load()


def set_applied(entry_id: str, applied: bool) -> None:
    entries = _load()
    for e in entries:
        if e["id"] == entry_id:
            e["applied"] = applied
            break
    _save(entries)


def delete_entry(entry_id: str) -> None:
    entries = [e for e in _load() if e["id"] != entry_id]
    _save(entries)
