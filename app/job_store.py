import json
import os
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

DB_PATH = os.getenv("MATCHER_JOBS_DB_PATH", "/app/data/matcher_jobs.db")


def _now() -> str:
    return datetime.utcnow().isoformat()


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS matcher_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL UNIQUE,
                idempotency_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'PENDING',
                payload_json TEXT NOT NULL,
                result_json TEXT NULL,
                error_message TEXT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0,
                trace_id TEXT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT NULL,
                finished_at TEXT NULL
            )
            """
        )
        conn.commit()


def get_job_by_idempotency_key(idempotency_key: str) -> Optional[Dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM matcher_jobs WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return dict(row) if row else None


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM matcher_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return dict(row) if row else None


def create_job(idempotency_key: str, payload: Dict[str, Any], trace_id: Optional[str]) -> Dict[str, Any]:
    existing = get_job_by_idempotency_key(idempotency_key)
    if existing:
        return existing

    job_id = f"job_{uuid.uuid4()}"
    now = _now()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO matcher_jobs (
                job_id, idempotency_key, status, payload_json, result_json, error_message,
                progress, attempts, trace_id, created_at, updated_at, started_at, finished_at
            ) VALUES (?, ?, 'PENDING', ?, NULL, NULL, 0, 0, ?, ?, ?, NULL, NULL)
            """,
            (job_id, idempotency_key, json.dumps(payload), trace_id, now, now),
        )
        conn.commit()
    return get_job(job_id)  # type: ignore


def update_job(job_id: str, **kwargs: Any) -> None:
    if not kwargs:
        return
    kwargs["updated_at"] = _now()
    fields = []
    values = []
    for key, value in kwargs.items():
        fields.append(f"{key} = ?")
        if key in ("payload_json", "result_json") and value is not None and not isinstance(value, str):
            values.append(json.dumps(value))
        else:
            values.append(value)
    values.append(job_id)
    query = f"UPDATE matcher_jobs SET {', '.join(fields)} WHERE job_id = ?"
    with _conn() as conn:
        conn.execute(query, tuple(values))
        conn.commit()

