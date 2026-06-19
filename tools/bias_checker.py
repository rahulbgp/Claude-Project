"""
Standalone bias detection utility.
Analyzes loan decisions for potential proxy-variable discrimination.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def check_age_proxy_bias(age: int, verdict: str, financial_reasons: list) -> dict:
    """
    Check if an age-related proxy bias might be present.

    Protected age groups (21-24 and 55-60) that receive rejections
    should have their reasons verified against financial metrics only.
    """
    risk = "LOW"
    flag = None

    financial_keywords = ["credit", "dti", "income", "emi", "ratio", "debt"]

    # Check if the rejection has clear financial justification
    has_financial_reason = any(
        any(kw in reason.lower() for kw in financial_keywords)
        for reason in financial_reasons
    )

    if age in range(21, 25) and verdict == "NOT_ELIGIBLE":
        if not has_financial_reason:
            risk = "HIGH"
            flag = f"Young applicant (age {age}) rejected without clear financial justification"
        else:
            risk = "MEDIUM"
            flag = f"Young applicant (age {age}) rejected — financial reasons present"

    elif age in range(55, 61) and verdict == "NOT_ELIGIBLE":
        if not has_financial_reason:
            risk = "MEDIUM"
            flag = f"Near-retirement applicant (age {age}) rejected without clear financial justification"

    return {"bias_risk": risk, "flag": flag, "has_financial_reason": has_financial_reason}


def check_employment_bias(employment_type: str, verdict: str, financial_reasons: list) -> dict:
    """
    Check if employment type is acting as a proxy variable for discrimination.
    Contract and Self-Employed workers may face higher rejection rates.
    """
    risk = "LOW"
    flag = None

    financial_keywords = ["credit", "dti", "income", "emi", "ratio", "debt", "stable"]
    has_financial_reason = any(
        any(kw in reason.lower() for kw in financial_keywords)
        for reason in financial_reasons
    )

    if employment_type in ("Contract", "Self-Employed") and verdict == "NOT_ELIGIBLE":
        if not has_financial_reason:
            risk = "HIGH"
            flag = f"{employment_type} worker rejected without clear financial justification"
        else:
            risk = "LOW"

    return {"bias_risk": risk, "flag": flag}


def aggregate_bias_check(
    age: int,
    employment_type: str,
    verdict: str,
    reasons: list,
) -> dict:
    """
    Run all bias checks and return an aggregated result.
    Called by the post-hook after every decision.
    """
    age_check = check_age_proxy_bias(age, verdict, reasons)
    emp_check = check_employment_bias(employment_type, verdict, reasons)

    flags = []
    if age_check["flag"]:
        flags.append({"source": "age_check", "risk": age_check["bias_risk"], "message": age_check["flag"]})
    if emp_check["flag"]:
        flags.append({"source": "employment_check", "risk": emp_check["bias_risk"], "message": emp_check["flag"]})

    # Aggregate risk level
    risks = [f["risk"] for f in flags]
    if "HIGH" in risks:
        overall_risk = "HIGH"
    elif "MEDIUM" in risks:
        overall_risk = "MEDIUM"
    else:
        overall_risk = "LOW"

    return {
        "bias_flags": flags,
        "overall_bias_risk": overall_risk,
        "bias_check_passed": overall_risk in ("LOW",),
    }
