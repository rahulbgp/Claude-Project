"""
Pre-processing hooks for the Loan Eligibility AI Agent.
Run BEFORE the orchestrator processes the applicant data.

Hook chain:
1. validate_input     — type checks and range validation
2. sanitize_input     — normalize strings, clamp values
3. mask_pii           — replace name with a hash in logs
4. enrich_input       — add derived fields (loan-to-income ratio, age group)
5. check_rate_limit   — simple per-session rate limiting
"""

import hashlib
import logging
import time
from collections import defaultdict
from typing import Optional

from config import (
    MAX_AGE,
    MAX_REQUESTS_PER_MINUTE,
    MIN_AGE,
)

logger = logging.getLogger(__name__)

# In-memory rate limit store: {session_id: [(timestamp, ...), ...]}
_rate_limit_store: dict = defaultdict(list)


# ─── Individual Hook Functions ─────────────────────────────────────────────────


def validate_input(context: dict) -> dict:
    """
    Validate all input fields for correct types and acceptable ranges.
    Raises ValueError with a clear message if validation fails.
    """
    data = context["data"]
    errors = []

    # Name validation
    name = data.get("name", "")
    if not isinstance(name, str) or len(name.strip()) == 0:
        errors.append("Name must be a non-empty string")

    # Age validation
    age = data.get("age")
    if not isinstance(age, (int, float)) or not (18 <= age <= 80):
        errors.append("Age must be a number between 18 and 80")

    # Income validation
    income = data.get("monthly_income")
    if not isinstance(income, (int, float)) or income <= 0:
        errors.append("Monthly income must be a positive number")

    # Existing EMI validation
    emi = data.get("existing_emi")
    if not isinstance(emi, (int, float)) or emi < 0:
        errors.append("Existing EMI must be zero or a positive number")

    # Credit score validation
    credit = data.get("credit_score")
    if not isinstance(credit, (int, float)) or not (300 <= credit <= 900):
        errors.append("Credit score must be between 300 and 900")

    # Employment type validation
    valid_employment = {"Salaried", "Self-Employed", "Contract", "Unemployed"}
    employment = data.get("employment_type", "")
    if employment not in valid_employment:
        errors.append(f"Employment type must be one of: {', '.join(sorted(valid_employment))}")

    # Loan amount validation
    loan_amount = data.get("loan_amount")
    if not isinstance(loan_amount, (int, float)) or loan_amount <= 0:
        errors.append("Loan amount must be a positive number")

    if errors:
        raise ValueError(f"Validation failed: {'; '.join(errors)}")

    return context


def sanitize_input(context: dict) -> dict:
    """
    Sanitize and normalize input values.
    - Strip whitespace from strings
    - Convert numeric types to standard floats/ints
    - Clamp values to safe ranges
    """
    data = context["data"]

    sanitized = {
        "name": str(data["name"]).strip()[:100],  # cap name length
        "age": int(data["age"]),
        "monthly_income": round(float(data["monthly_income"]), 2),
        "existing_emi": round(float(data["existing_emi"]), 2),
        "credit_score": int(data["credit_score"]),
        "employment_type": str(data["employment_type"]).strip(),
        "loan_amount": round(float(data["loan_amount"]), 2),
        # Loan terms — preserve so agents compute EMI-to-Income ratio correctly
        "loan_tenure_months": int(data.get("loan_tenure_months", 60)),
        "annual_interest_rate": float(data.get("annual_interest_rate", 0.10)),
        "estimated_new_emi": round(float(data.get("estimated_new_emi", 0)), 2),
    }

    context["data"] = sanitized
    return context


def mask_pii(context: dict) -> dict:
    """
    Replace the applicant's name with a one-way hash in the context used for logging.
    The original name is preserved in context["original_name"] for display to the user.

    This ensures PII never appears in log files or audit records.
    """
    data = context["data"]
    original_name = data["name"]

    # SHA-256 hash of the name (one-way, non-reversible)
    name_hash = hashlib.sha256(original_name.encode()).hexdigest()[:12]
    applicant_hash = f"APPLICANT_{name_hash.upper()}"

    # Save the hash for audit records
    context["applicant_hash"] = applicant_hash
    context["original_name"] = original_name

    # Do NOT replace the name in data — it's shown to the user in the UI
    # Only the audit trail uses the hash
    logger.info(
        "PII masked for audit logging",
        extra={
            "trace_id": context.get("trace_id"),
            "applicant_hash": applicant_hash,
        },
    )

    return context


def enrich_input(context: dict) -> dict:
    """
    Add derived fields to the input data that are useful for agents and display.
    """
    data = context["data"]

    monthly_income = data["monthly_income"]
    existing_emi = data["existing_emi"]
    loan_amount = data["loan_amount"]
    age = data["age"]

    # Annual income
    annual_income = monthly_income * 12

    # Loan-to-income ratio
    lti_ratio = round(loan_amount / annual_income, 4) if annual_income > 0 else float("inf")

    # Existing EMI-to-income ratio (before new loan)
    existing_emi_ratio = round(existing_emi / monthly_income, 4) if monthly_income > 0 else 1.0

    # Age group (for compliance categorization)
    if age < 25:
        age_group = "21-24"
    elif age < 35:
        age_group = "25-34"
    elif age < 45:
        age_group = "35-44"
    elif age < 55:
        age_group = "45-54"
    else:
        age_group = "55-60"

    context["derived"] = {
        "annual_income": annual_income,
        "loan_to_income_ratio": lti_ratio,
        "existing_emi_to_income_ratio": existing_emi_ratio,
        "age_group": age_group,
    }

    return context


def check_rate_limit(context: dict) -> dict:
    """
    Simple in-memory rate limiting: max 10 requests per minute per session.
    Raises RuntimeError if the limit is exceeded.
    """
    session_id = context.get("session_id", "default")
    now = time.time()
    window = 60  # seconds

    # Remove timestamps older than the window
    _rate_limit_store[session_id] = [
        t for t in _rate_limit_store[session_id] if now - t < window
    ]

    if len(_rate_limit_store[session_id]) >= MAX_REQUESTS_PER_MINUTE:
        raise RuntimeError(
            f"Rate limit exceeded: maximum {MAX_REQUESTS_PER_MINUTE} requests per minute. "
            "Please wait a moment before trying again."
        )

    _rate_limit_store[session_id].append(now)
    return context


# ─── Hook Chain Runner ─────────────────────────────────────────────────────────

PRE_HOOKS = [validate_input, sanitize_input, mask_pii, enrich_input, check_rate_limit]


def run_pre_hooks(applicant_data: dict, trace_id: str, session_id: str = "default") -> dict:
    """
    Run all pre-processing hooks in order.
    Returns the enriched context dict with 'data', 'applicant_hash', 'derived'.
    """
    context = {
        "data": applicant_data.copy(),
        "trace_id": trace_id,
        "session_id": session_id,
    }

    for hook in PRE_HOOKS:
        try:
            context = hook(context)
        except (ValueError, RuntimeError):
            # These are user-facing errors — re-raise
            raise
        except Exception as e:
            logger.error(
                f"Pre-hook {hook.__name__} failed",
                extra={"trace_id": trace_id, "error": str(e)},
            )
            raise

    return context
