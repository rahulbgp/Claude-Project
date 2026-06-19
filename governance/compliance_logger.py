"""
Structured JSON compliance logging for regulatory requirements.
Each loan decision is logged as a JSONL record with regulatory framework details.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Optional

from config import COMPLIANCE_LOG_FILE, LOG_DIR, REGULATORY_FRAMEWORK

logger = logging.getLogger(__name__)
_file_lock = threading.Lock()


def _ensure_log_dir() -> None:
    """Ensure the logs directory exists."""
    os.makedirs(LOG_DIR, exist_ok=True)


def write_compliance_record(
    trace_id: str,
    applicant_hash: str,
    verdict: str,
    reasons: list,
    non_discriminatory_reasons: list,
    employment_type: str,
    age_group: str,
    model_version: str,
    bias_check_passed: bool,
    human_review_flag: bool,
    dti_ratio: float,
    bias_flags: Optional[list] = None,
) -> None:
    """
    Write a structured compliance record to the JSONL compliance log.
    This log satisfies regulatory fair-lending audit requirements.
    """
    _ensure_log_dir()

    if bias_flags is None:
        bias_flags = []

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "regulatory_framework": REGULATORY_FRAMEWORK,
        "applicant_hash": applicant_hash,
        "decision": verdict,
        "reasons": reasons,
        "non_discriminatory_reasons": non_discriminatory_reasons,
        "financial_metrics": {
            "dti_ratio": round(dti_ratio, 4),
        },
        "protected_attributes_used": False,
        "employment_type_category": employment_type,
        "age_group": age_group,
        "bias_check_passed": bias_check_passed,
        "bias_flags": bias_flags,
        "model_version": model_version,
        "human_review_flag": human_review_flag,
        "compliance_status": "COMPLIANT" if bias_check_passed else "NEEDS_REVIEW",
    }

    with _file_lock:
        try:
            with open(COMPLIANCE_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            logger.info(
                "Compliance record written",
                extra={"trace_id": trace_id, "compliance_status": record["compliance_status"]},
            )
        except Exception as e:
            logger.error(
                "Failed to write compliance record",
                extra={"trace_id": trace_id, "error": str(e)},
            )


def get_age_group(age: int) -> str:
    """Categorize age into a group for compliance reporting."""
    if age < 25:
        return "21-24"
    elif age < 35:
        return "25-34"
    elif age < 45:
        return "35-44"
    elif age < 55:
        return "45-54"
    else:
        return "55-60"
