"""
Post-processing hooks for the Loan Eligibility AI Agent.
Run AFTER the orchestrator returns a decision.

Hook chain:
1. record_audit_trail     — write to SQLite audit log
2. emit_compliance_log    — write structured JSONL compliance record
3. update_metrics         — update Prometheus counters and histograms
4. check_decision_bias    — run bias analysis on the decision
5. notify_manual_review   — write to the manual review queue if needed
"""

import json
import logging
import os
import time
from typing import Optional

from pipeline.explainer import LoanDecision, Verdict
from config import LOG_DIR, MODEL, REVIEW_QUEUE_FILE
from governance import audit_trail, compliance_logger
from governance.bias_report import generate_bias_report
from tools.bias_checker import aggregate_bias_check
from observability import metrics
from graph.node_builder import build_decision_graph

logger = logging.getLogger(__name__)


def record_audit_trail(
    decision: LoanDecision,
    pre_context: dict,
    trace_id: str,
    processing_time_ms: int,
) -> list:
    """Write the loan decision to the immutable SQLite audit trail."""
    data = pre_context["data"]
    applicant_hash = pre_context.get("applicant_hash", "UNKNOWN")

    audit_trail.write_decision(
        trace_id=trace_id,
        applicant_hash=applicant_hash,
        credit_score=data.get("credit_score", 0),
        monthly_income=data.get("monthly_income", 0),
        existing_emi=data.get("existing_emi", 0),
        loan_amount=data.get("loan_amount", 0),
        age=data.get("age", 0),
        employment_type=data.get("employment_type", "Unknown"),
        verdict=decision.verdict.value,
        dti_ratio=decision.dti_ratio,
        risk_band=decision.risk_band,
        reasons=decision.reasons,
        model_used=decision.model_used,
        tool_calls_count=decision.tool_calls_count,
        processing_time_ms=processing_time_ms,
        bias_flags=[],
        compliance_status="COMPLIANT",
    )

    return []  # Returns bias_flags (filled in step 4)


def emit_compliance_log(
    decision: LoanDecision,
    pre_context: dict,
    trace_id: str,
    bias_flags: list,
) -> None:
    """Write a structured compliance record to the JSONL compliance log."""
    data = pre_context["data"]
    applicant_hash = pre_context.get("applicant_hash", "UNKNOWN")
    derived = pre_context.get("derived", {})
    age_group = derived.get("age_group", "unknown")

    # Non-discriminatory reasons: filter to financial-metric-based reasons
    financial_keywords = ["credit", "dti", "income", "emi", "ratio", "debt", "score", "age", "employ"]
    non_discriminatory_reasons = [
        r for r in decision.reasons
        if any(kw in r.lower() for kw in financial_keywords)
    ]

    bias_check_passed = all(f.get("risk", "LOW") != "HIGH" for f in bias_flags)

    compliance_logger.write_compliance_record(
        trace_id=trace_id,
        applicant_hash=applicant_hash,
        verdict=decision.verdict.value,
        reasons=decision.reasons,
        non_discriminatory_reasons=non_discriminatory_reasons,
        employment_type=data.get("employment_type", "Unknown"),
        age_group=age_group,
        model_version=decision.model_used,
        bias_check_passed=bias_check_passed,
        human_review_flag=(decision.verdict == Verdict.MANUAL_REVIEW),
        dti_ratio=decision.dti_ratio,
        bias_flags=bias_flags,
    )


def update_prometheus_metrics(
    decision: LoanDecision,
    pre_context: dict,
    processing_time_seconds: float,
) -> None:
    """Update Prometheus metrics for this loan decision."""
    data = pre_context["data"]

    metrics.record_request(
        verdict=decision.verdict.value,
        employment_type=data.get("employment_type", "Unknown"),
        duration_seconds=processing_time_seconds,
        dti_ratio=decision.dti_ratio,
    )


def check_decision_bias(
    decision: LoanDecision,
    pre_context: dict,
    trace_id: str,
) -> list:
    """Run bias analysis on the decision and return any bias flags found."""
    data = pre_context["data"]

    bias_result = aggregate_bias_check(
        age=data.get("age", 35),
        employment_type=data.get("employment_type", "Salaried"),
        verdict=decision.verdict.value,
        reasons=decision.reasons,
    )

    bias_flags = bias_result.get("bias_flags", [])

    if bias_flags:
        logger.warning(
            "Bias indicators detected",
            extra={
                "trace_id": trace_id,
                "bias_risk": bias_result.get("overall_bias_risk"),
                "flag_count": len(bias_flags),
            },
        )

    return bias_flags


def notify_manual_review(
    decision: LoanDecision,
    pre_context: dict,
    trace_id: str,
) -> None:
    """Write to the manual review queue if the verdict requires human review."""
    if decision.verdict != Verdict.MANUAL_REVIEW:
        return

    os.makedirs(LOG_DIR, exist_ok=True)
    data = pre_context["data"]
    applicant_hash = pre_context.get("applicant_hash", "UNKNOWN")

    review_record = {
        "trace_id": trace_id,
        "applicant_hash": applicant_hash,
        "credit_score": data.get("credit_score"),
        "employment_type": data.get("employment_type"),
        "dti_ratio": decision.dti_ratio,
        "risk_band": decision.risk_band,
        "reasons": decision.reasons,
        "status": "PENDING_REVIEW",
    }

    try:
        with open(REVIEW_QUEUE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(review_record) + "\n")
        logger.info(
            "Added to manual review queue",
            extra={"trace_id": trace_id},
        )
    except Exception as e:
        logger.error(
            "Failed to write to review queue",
            extra={"trace_id": trace_id, "error": str(e)},
        )


# ─── Post-Hook Chain Runner ────────────────────────────────────────────────────


def run_post_hooks(
    decision: LoanDecision,
    pre_context: dict,
    trace_id: str,
    start_time: float,
) -> list:
    """
    Run all post-processing hooks in order.
    Returns the list of bias flags found.

    Args:
        decision: The LoanDecision from the orchestrator
        pre_context: The context dict from the pre-hooks (includes 'data', 'applicant_hash', 'derived')
        trace_id: The request trace ID
        start_time: time.time() at the start of the request (for computing duration)
    """
    end_time = time.time()
    processing_time_seconds = end_time - start_time
    processing_time_ms = int(processing_time_seconds * 1000)

    bias_flags = []

    # Hook 1: Audit trail
    try:
        record_audit_trail(decision, pre_context, trace_id, processing_time_ms)
    except Exception as e:
        logger.error("Audit trail hook failed", extra={"trace_id": trace_id, "error": str(e)})

    # Hook 2: Bias check (run before compliance log to get flags)
    try:
        bias_flags = check_decision_bias(decision, pre_context, trace_id)
    except Exception as e:
        logger.error("Bias check hook failed", extra={"trace_id": trace_id, "error": str(e)})

    # Hook 3: Compliance log
    try:
        emit_compliance_log(decision, pre_context, trace_id, bias_flags)
    except Exception as e:
        logger.error("Compliance log hook failed", extra={"trace_id": trace_id, "error": str(e)})

    # Hook 4: Prometheus metrics
    try:
        update_prometheus_metrics(decision, pre_context, processing_time_seconds)
    except Exception as e:
        logger.error("Metrics hook failed", extra={"trace_id": trace_id, "error": str(e)})

    # Hook 5: Manual review queue
    try:
        notify_manual_review(decision, pre_context, trace_id)
    except Exception as e:
        logger.error("Manual review hook failed", extra={"trace_id": trace_id, "error": str(e)})

    # Hook 6: Neo4j graph nodes (best-effort — non-blocking)
    try:
        build_decision_graph(decision, pre_context, trace_id)
    except Exception as e:
        logger.debug("Graph write skipped: %s", e)

    return bias_flags
