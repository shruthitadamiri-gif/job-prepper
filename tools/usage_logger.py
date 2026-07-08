"""
Usage and cost logger — SQLite-backed, never raises.

Call log_usage() after every client.messages.create() call.
Tables are created on first import.
"""

import os
import sqlite3
import time
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "usage.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL,
    agent_name      TEXT    NOT NULL,
    model           TEXT    NOT NULL,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER,
    cost_usd        REAL    NOT NULL DEFAULT 0,
    latency_ms      INTEGER NOT NULL DEFAULT 0,
    status          TEXT    NOT NULL DEFAULT 'ok',
    created_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS pricing (
    model                   TEXT PRIMARY KEY,
    input_cost_per_mtok     REAL NOT NULL,
    output_cost_per_mtok    REAL NOT NULL,
    effective_date          TEXT NOT NULL
);
"""

_SEED_PRICING = [
    ("claude-sonnet-4-6",        3.00,  15.00, "2025-01-01"),
    ("claude-haiku-4-5-20251001", 0.80,   4.00, "2025-01-01"),
]


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_tables() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        for row in _SEED_PRICING:
            conn.execute(
                "INSERT OR IGNORE INTO pricing (model, input_cost_per_mtok, output_cost_per_mtok, effective_date) "
                "VALUES (?, ?, ?, ?)", row
            )


# Initialise on import
try:
    _ensure_tables()
except Exception as e:
    print(f"[usage_logger] init failed (non-fatal): {e}")


def _cost(model: str, input_tokens: int, output_tokens: int, conn: sqlite3.Connection) -> float:
    row = conn.execute(
        "SELECT input_cost_per_mtok, output_cost_per_mtok FROM pricing WHERE model = ?", (model,)
    ).fetchone()
    if not row:
        return 0.0
    return (input_tokens * row["input_cost_per_mtok"] + output_tokens * row["output_cost_per_mtok"]) / 1_000_000


def log_usage(
    session_id: str,
    agent_name: str,
    model: str,
    response,           # anthropic Message object
    latency_ms: int,
    status: str = "ok",
) -> None:
    """
    Log one LLM call. Never raises — a failure here must not break the pipeline.
    """
    try:
        usage = response.usage
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", None)

        with _connect() as conn:
            cost = _cost(model, input_tokens, output_tokens, conn)
            conn.execute(
                "INSERT INTO usage_events "
                "(session_id, agent_name, model, input_tokens, output_tokens, "
                "cache_read_tokens, cost_usd, latency_ms, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id, agent_name, model,
                    input_tokens, output_tokens, cache_read,
                    cost, latency_ms, status,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                )
            )
    except Exception as e:
        print(f"[usage_logger] log_usage failed (non-fatal): {e}")


def query_usage() -> dict:
    """Return aggregated stats for the Usage page."""
    try:
        with _connect() as conn:
            total = conn.execute(
                "SELECT COALESCE(SUM(cost_usd),0) as cost, "
                "COALESCE(SUM(input_tokens+output_tokens),0) as tokens, "
                "COUNT(*) as calls FROM usage_events WHERE status='ok'"
            ).fetchone()

            by_agent = conn.execute(
                "SELECT agent_name, COUNT(*) as calls, "
                "SUM(input_tokens+output_tokens) as tokens, SUM(cost_usd) as cost "
                "FROM usage_events WHERE status='ok' "
                "GROUP BY agent_name ORDER BY cost DESC"
            ).fetchall()

            by_day = conn.execute(
                "SELECT substr(created_at,1,10) as day, SUM(cost_usd) as cost, "
                "COUNT(*) as calls FROM usage_events WHERE status='ok' "
                "AND created_at >= date('now','-30 days') "
                "GROUP BY day ORDER BY day DESC"
            ).fetchall()

            by_session = conn.execute(
                "SELECT session_id, MIN(created_at) as started_at, "
                "COUNT(*) as calls, "
                "SUM(input_tokens+output_tokens) as tokens, "
                "SUM(cost_usd) as cost "
                "FROM usage_events WHERE status='ok' "
                "GROUP BY session_id ORDER BY started_at DESC LIMIT 50"
            ).fetchall()

            avg_latency = conn.execute(
                "SELECT agent_name, ROUND(AVG(latency_ms)) as avg_ms "
                "FROM usage_events WHERE status='ok' "
                "GROUP BY agent_name ORDER BY avg_ms DESC"
            ).fetchall()

        return {
            "total": dict(total),
            "by_agent": [dict(r) for r in by_agent],
            "by_day": [dict(r) for r in by_day],
            "by_session": [dict(r) for r in by_session],
            "avg_latency": [dict(r) for r in avg_latency],
        }
    except Exception as e:
        print(f"[usage_logger] query_usage failed: {e}")
        return {"total": {}, "by_agent": [], "by_day": [], "by_session": [], "avg_latency": []}
