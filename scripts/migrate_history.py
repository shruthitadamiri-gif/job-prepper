"""
One-off migration: copy rows from 'history' → 'opportunities'.

Idempotent: rows whose dedup key already exists in opportunities are skipped.
Run from the project root:
    python3 scripts/migrate_history.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from tools.opportunity_store import _client, _dedup_key, _now, TABLE


def migrate():
    client = _client()

    print("Loading history rows...")
    history = client.table("history").select("*").execute().data or []
    print(f"  Found {len(history)} rows in history.")

    print("Loading existing opportunity keys...")
    existing_keys = set()
    for row in (client.table(TABLE).select("url,title,company").execute().data or []):
        existing_keys.add(_dedup_key(row.get("title", ""), row.get("company", ""), row.get("url", "")))
    print(f"  Found {len(existing_keys)} existing opportunities.")

    inserted = 0
    skipped = 0

    for row in history:
        title = row.get("role", "")
        company = row.get("company", "")
        key = _dedup_key(title, company, "")

        if key in existing_keys:
            skipped += 1
            continue

        stage = "applied" if row.get("applied") else "tailored"
        now = _now()
        opp = {
            "id": row["id"],
            "created_at": row.get("date_created", now),
            "stage_updated_at": row.get("date_created", now),
            "source": "manual",
            "url": None,
            "title": title or None,
            "company": company or None,
            "location": row.get("location") or None,
            "searched_title": None,
            "jd_snapshot": row.get("jd_text") or None,
            "stage": stage,
            "date_applied": row.get("date_created") if stage == "applied" else None,
            "fit_score": None,
            "fit_verdict": None,
            "dealbreakers": None,
            "visa_status": None,
            "resume_version": row.get("resume_output") or None,
            "eval_result": {"overall_score": row.get("relevance_score")} if row.get("relevance_score") is not None else None,
            "ats_result": None,
            "notes": "",
        }

        try:
            client.table(TABLE).insert(opp).execute()
            inserted += 1
            existing_keys.add(key)
        except Exception as e:
            print(f"  WARN: failed to insert {company} — {title}: {e}")
            skipped += 1

    print(f"\nMigration complete: {inserted} inserted, {skipped} skipped.")


if __name__ == "__main__":
    migrate()
