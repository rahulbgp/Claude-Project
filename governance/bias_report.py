"""
Bias analysis for the Loan Eligibility AI Agent.
Analyzes the audit trail to detect disparate impact across demographic proxies.
"""

import json
import logging
import sqlite3
from typing import Optional

from config import AUDIT_DB_PATH

logger = logging.getLogger(__name__)


def generate_bias_report() -> dict:
    """
    Analyze the audit trail and generate a bias report.
    Checks for disparate approval rates by age group and employment type.
    Returns a dict with approval rates and any flags.
    """
    try:
        conn = sqlite3.connect(AUDIT_DB_PATH)
        conn.row_factory = sqlite3.Row

        # Approval rates by employment type
        employment_rows = conn.execute("""
            SELECT
                employment_type,
                COUNT(*) as total,
                SUM(CASE WHEN verdict='ELIGIBLE' THEN 1 ELSE 0 END) as approved
            FROM audit_log
            GROUP BY employment_type
        """).fetchall()

        # Approval rates by age group
        age_rows = conn.execute("""
            SELECT
                CASE
                    WHEN age BETWEEN 21 AND 24 THEN '21-24'
                    WHEN age BETWEEN 25 AND 34 THEN '25-34'
                    WHEN age BETWEEN 35 AND 44 THEN '35-44'
                    WHEN age BETWEEN 45 AND 54 THEN '45-54'
                    ELSE '55-60'
                END as age_group,
                COUNT(*) as total,
                SUM(CASE WHEN verdict='ELIGIBLE' THEN 1 ELSE 0 END) as approved
            FROM audit_log
            WHERE age BETWEEN 21 AND 60
            GROUP BY age_group
        """).fetchall()

        conn.close()

        employment_stats = {}
        for row in employment_rows:
            total = row["total"]
            approved = row["approved"] or 0
            rate = round(approved / total, 4) if total > 0 else 0.0
            employment_stats[row["employment_type"]] = {
                "total": total,
                "approved": approved,
                "approval_rate": rate,
            }

        age_stats = {}
        for row in age_rows:
            total = row["total"]
            approved = row["approved"] or 0
            rate = round(approved / total, 4) if total > 0 else 0.0
            age_stats[row["age_group"]] = {
                "total": total,
                "approved": approved,
                "approval_rate": rate,
            }

        # Detect flags: if any group has an approval rate < 80% of the highest-rate group,
        # flag it as potential disparate impact
        flags = []

        max_emp_rate = max((v["approval_rate"] for v in employment_stats.values()), default=0)
        for emp_type, stats in employment_stats.items():
            if max_emp_rate > 0 and stats["approval_rate"] < max_emp_rate * 0.8 and stats["total"] >= 5:
                flags.append({
                    "type": "employment_disparate_impact",
                    "group": emp_type,
                    "approval_rate": stats["approval_rate"],
                    "max_rate": max_emp_rate,
                })

        return {
            "employment_type_stats": employment_stats,
            "age_group_stats": age_stats,
            "disparate_impact_flags": flags,
            "bias_risk": "HIGH" if len(flags) > 2 else "MEDIUM" if flags else "LOW",
        }

    except Exception as e:
        logger.error("Failed to generate bias report", extra={"error": str(e)})
        return {"error": str(e), "bias_risk": "UNKNOWN"}
