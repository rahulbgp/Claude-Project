"""
SQLite-backed immutable audit trail for loan decisions.
Every loan decision is recorded here for compliance and governance.
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Optional

from config import AUDIT_DB_PATH

logger = logging.getLogger(__name__)

# Thread-local storage for SQLite connections (SQLite connections are not thread-safe)
_local = threading.local()
_db_lock = threading.Lock()


def _get_connection() -> sqlite3.Connection:
    """Get a thread-local SQLite connection, creating if needed."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(AUDIT_DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
    return _local.conn


def initialize_db() -> None:
    """Create the audit_log table if it doesn't exist."""
    with _db_lock:
        conn = sqlite3.connect(AUDIT_DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id            TEXT    UNIQUE NOT NULL,
                timestamp           TEXT    NOT NULL,
                applicant_hash      TEXT    NOT NULL,
                credit_score        INTEGER,
                monthly_income      REAL,
                existing_emi        REAL,
                loan_amount         REAL,
                age                 INTEGER,
                employment_type     TEXT,
                verdict             TEXT    NOT NULL,
                dti_ratio           REAL,
                risk_band           TEXT,
                reasons             TEXT,
                model_used          TEXT,
                tool_calls_count    INTEGER DEFAULT 0,
                processing_time_ms  INTEGER DEFAULT 0,
                bias_flags          TEXT    DEFAULT '[]',
                compliance_status   TEXT    DEFAULT 'PENDING'
            )
        """)
        conn.commit()
        conn.close()


def write_decision(
    trace_id: str,
    applicant_hash: str,
    credit_score: int,
    monthly_income: float,
    existing_emi: float,
    loan_amount: float,
    age: int,
    employment_type: str,
    verdict: str,
    dti_ratio: float,
    risk_band: str,
    reasons: list,
    model_used: str,
    tool_calls_count: int = 0,
    processing_time_ms: int = 0,
    bias_flags: Optional[list] = None,
    compliance_status: str = "COMPLIANT",
) -> None:
    """Write a loan decision to the immutable audit log."""
    if bias_flags is None:
        bias_flags = []

    timestamp = datetime.now(timezone.utc).isoformat()

    with _db_lock:
        conn = sqlite3.connect(AUDIT_DB_PATH)
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO audit_log (
                    trace_id, timestamp, applicant_hash, credit_score,
                    monthly_income, existing_emi, loan_amount, age, employment_type,
                    verdict, dti_ratio, risk_band, reasons, model_used,
                    tool_calls_count, processing_time_ms, bias_flags, compliance_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    timestamp,
                    applicant_hash,
                    credit_score,
                    monthly_income,
                    existing_emi,
                    loan_amount,
                    age,
                    employment_type,
                    verdict,
                    round(dti_ratio, 4),
                    risk_band,
                    json.dumps(reasons),
                    model_used,
                    tool_calls_count,
                    processing_time_ms,
                    json.dumps(bias_flags),
                    compliance_status,
                ),
            )
            conn.commit()
            logger.info("Audit record written", extra={"trace_id": trace_id, "verdict": verdict})
        except Exception as e:
            logger.error("Failed to write audit record", extra={"trace_id": trace_id, "error": str(e)})
        finally:
            conn.close()


def get_recent_decisions(limit: int = 10) -> list:
    """Retrieve the most recent loan decisions for display in the UI."""
    with _db_lock:
        conn = sqlite3.connect(AUDIT_DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT trace_id, timestamp, applicant_hash, age, employment_type,
                       credit_score, verdict, dti_ratio, risk_band, processing_time_ms
                FROM audit_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


def get_stats() -> dict:
    """Get aggregate statistics from the audit log (for governance report)."""
    with _db_lock:
        conn = sqlite3.connect(AUDIT_DB_PATH)
        try:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN verdict='ELIGIBLE' THEN 1 ELSE 0 END) as eligible,
                    SUM(CASE WHEN verdict='NOT_ELIGIBLE' THEN 1 ELSE 0 END) as not_eligible,
                    SUM(CASE WHEN verdict='MANUAL_REVIEW' THEN 1 ELSE 0 END) as manual_review,
                    AVG(dti_ratio) as avg_dti_ratio,
                    AVG(processing_time_ms) as avg_processing_time_ms
                FROM audit_log
            """).fetchone()

            stats = {
                "total": row[0] or 0,
                "eligible": row[1] or 0,
                "not_eligible": row[2] or 0,
                "manual_review": row[3] or 0,
                "avg_dti_ratio": round(row[4] or 0, 4),
                "avg_processing_time_ms": round(row[5] or 0, 1),
            }
            return stats
        finally:
            conn.close()
