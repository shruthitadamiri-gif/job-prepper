"""
Opportunity store — single source of record for the job funnel.

Each opportunity moves through stages:
  discovered → screened_in / screened_out → tailored → applied
  → responded → interviewing → offer / rejected / ghosted / withdrawn
"""

import os
import uuid
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
TABLE = "opportunities"


def _client():
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dedup_key(title: str, company: str, url: str = "") -> str:
    if url:
        return url.strip()
    return f"{(title or '').strip().lower()}|{(company or '').strip().lower()}"


# ---------------------------------------------------------------
# WRITE OPERATIONS
# ---------------------------------------------------------------

def create_opportunity(
    title: str = "",
    company: str = "",
    location: str = "",
    url: str = "",
    searched_title: str = "",
    jd_snapshot: str = "",
    source: str = "manual",
    stage: str = "discovered",
    eval_result: dict | None = None,
    ats_result: dict | None = None,
    notes: str = "",
) -> str:
    opp_id = uuid.uuid4().hex
    now = _now()
    row = {
        "id": opp_id,
        "created_at": now,
        "stage_updated_at": now,
        "source": source,
        "url": url or None,
        "title": title or None,
        "company": company or None,
        "location": location or None,
        "searched_title": searched_title or None,
        "jd_snapshot": jd_snapshot or None,
        "stage": stage,
        "date_applied": None,
        "fit_score": None,
        "fit_verdict": None,
        "dealbreakers": None,
        "visa_status": None,
        "resume_version": None,
        "eval_result": eval_result,
        "ats_result": ats_result,
        "notes": notes,
    }
    _client().table(TABLE).insert(row).execute()
    return opp_id


def get_opportunity(opp_id: str) -> dict | None:
    resp = _client().table(TABLE).select("*").eq("id", opp_id).execute()
    rows = resp.data or []
    return rows[0] if rows else None


def update_stage(opp_id: str, new_stage: str) -> None:
    now = _now()
    fields = {"stage": new_stage, "stage_updated_at": now}
    if new_stage == "applied":
        fields["date_applied"] = now
    _client().table(TABLE).update(fields).eq("id", opp_id).execute()


def update_fields(opp_id: str, fields: dict) -> None:
    _client().table(TABLE).update(fields).eq("id", opp_id).execute()


def delete_opportunity(opp_id: str) -> None:
    _client().table(TABLE).delete().eq("id", opp_id).execute()


# ---------------------------------------------------------------
# READ OPERATIONS
# ---------------------------------------------------------------

def list_opportunities(stage: str | None = None) -> list[dict]:
    q = _client().table(TABLE).select("*")
    if stage:
        q = q.eq("stage", stage)
    resp = q.order("stage_updated_at", desc=True).execute()
    return resp.data or []


def title_performance_context() -> str:
    """
    Build a human-readable summary of per-searched-title funnel performance.
    Used by discover_titles() to drop low-yield titles and propose replacements.
    Returns empty string if no data exists yet.
    """
    opps = list_opportunities()
    if not opps:
        return ""

    stats: dict[str, dict] = {}
    for o in opps:
        t = o.get("searched_title") or "manual"
        if t == "manual":
            continue
        if t not in stats:
            stats[t] = {"found": 0, "screened_in": 0, "applied": 0}
        stats[t]["found"] += 1
        if o.get("stage") in ("screened_in", "tailored", "applied", "responded", "interviewing", "offer"):
            stats[t]["screened_in"] += 1
        if o.get("stage") in ("applied", "responded", "interviewing", "offer"):
            stats[t]["applied"] += 1

    if not stats:
        return ""

    lines = []
    for t, s in sorted(stats.items(), key=lambda x: -x[1]["found"]):
        scr_rate = round(s["screened_in"] / s["found"] * 100) if s["found"] else 0
        lines.append(
            f"  - {t}: {s['found']} found, {s['screened_in']} screened in ({scr_rate}%), {s['applied']} applied"
        )

    return "\n".join(lines)


def seen_keys() -> set[str]:
    """
    Dedup keys for every opportunity ever created.
    Used by discovery to skip jobs already in the funnel.
    """
    resp = _client().table(TABLE).select("url,title,company").execute()
    keys = set()
    for row in (resp.data or []):
        keys.add(_dedup_key(row.get("title", ""), row.get("company", ""), row.get("url", "")))
    return keys
