"""
Loan eligibility tools (Skills) used by AI agents.
These are plain Python functions registered as Claude tools.
Each function receives structured input and returns a JSON string.
"""

import json
import logging
import math
from typing import Any

import requests

from config import (
    EXCELLENT_CREDIT_SCORE,
    EMPLOYMENT_STABILITY_SCORES,
    MAX_DTI_RATIO,
    MAX_LOAN_TO_INCOME_RATIO,
    MIN_AGE,
    MAX_AGE,
    MIN_CREDIT_SCORE,
    MCP_LOAN_RULES_URL,
)

logger = logging.getLogger(__name__)

# ─── Tool Schema Definitions ───────────────────────────────────────────────────
# These dicts are passed to Claude as the "tools" parameter.
# Claude reads the description to decide when and how to call each tool.

TOOL_SCHEMAS = [
    {
        "name": "check_credit_score",
        "description": "Check if an applicant's credit score meets the minimum threshold for loan eligibility. Returns pass/fail status and a score category.",
        "input_schema": {
            "type": "object",
            "properties": {
                "credit_score": {
                    "type": "integer",
                    "description": "The applicant's credit score (typically 300-900)",
                }
            },
            "required": ["credit_score"],
        },
    },
    {
        "name": "check_dti_ratio",
        "description": "Check if the applicant's EMI-to-Income ratio is within the acceptable limit. Total EMI (existing + new loan EMI) should not exceed 40% of monthly income.",
        "input_schema": {
            "type": "object",
            "properties": {
                "monthly_income": {
                    "type": "number",
                    "description": "Applicant's monthly income in rupees",
                },
                "existing_emi": {
                    "type": "number",
                    "description": "Sum of all existing monthly EMI payments",
                },
                "loan_emi_estimate": {
                    "type": "number",
                    "description": "Estimated EMI for the new loan being requested",
                },
            },
            "required": ["monthly_income", "existing_emi", "loan_emi_estimate"],
        },
    },
    {
        "name": "check_age_eligibility",
        "description": "Verify that the applicant's age falls within the eligible range (21-60 years).",
        "input_schema": {
            "type": "object",
            "properties": {
                "age": {"type": "integer", "description": "Applicant's age in years"}
            },
            "required": ["age"],
        },
    },
    {
        "name": "check_employment_stability",
        "description": "Assess the stability of the applicant's employment type. Salaried employees get the highest score; unemployed applicants are not eligible.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employment_type": {
                    "type": "string",
                    "description": "Employment type: Salaried, Self-Employed, Contract, or Unemployed",
                    "enum": ["Salaried", "Self-Employed", "Contract", "Unemployed"],
                }
            },
            "required": ["employment_type"],
        },
    },
    {
        "name": "compute_loan_emi",
        "description": "Calculate the estimated monthly EMI for the requested loan amount using the standard EMI formula.",
        "input_schema": {
            "type": "object",
            "properties": {
                "loan_amount": {
                    "type": "number",
                    "description": "Total loan amount requested in rupees",
                },
                "annual_rate": {
                    "type": "number",
                    "description": "Annual interest rate as a decimal (e.g., 0.10 for 10%)",
                    "default": 0.10,
                },
                "tenure_months": {
                    "type": "integer",
                    "description": "Loan tenure in months (default 60 months = 5 years)",
                    "default": 60,
                },
            },
            "required": ["loan_amount"],
        },
    },
    {
        "name": "assess_risk_band",
        "description": "Assess the overall risk band for the loan application based on credit score, EMI-to-Income ratio, and employment stability score.",
        "input_schema": {
            "type": "object",
            "properties": {
                "credit_score": {"type": "integer"},
                "dti_ratio": {
                    "type": "number",
                    "description": "EMI-to-Income ratio as a decimal (e.g., 0.35 for 35%)",
                },
                "employment_score": {
                    "type": "number",
                    "description": "Employment stability score from 0.0 (unemployed) to 1.0 (salaried)",
                },
            },
            "required": ["credit_score", "dti_ratio", "employment_score"],
        },
    },
    {
        "name": "fetch_policy_rules",
        "description": "Fetch the current loan policy rules from the bank's policy server. Use this to get up-to-date thresholds before making eligibility decisions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "rule_category": {
                    "type": "string",
                    "description": "Category of rules to fetch: credit_score, dti, age, employment, or compliance",
                    "enum": ["credit_score", "dti", "age", "employment", "compliance"],
                }
            },
            "required": ["rule_category"],
        },
    },
    {
        "name": "check_bias_indicators",
        "description": "Check if the applicant profile has any attributes that could be proxy variables for protected characteristics. Used for fairness monitoring.",
        "input_schema": {
            "type": "object",
            "properties": {
                "age": {"type": "integer"},
                "employment_type": {"type": "string"},
                "verdict": {
                    "type": "string",
                    "description": "The preliminary verdict (ELIGIBLE, NOT_ELIGIBLE, or MANUAL_REVIEW)",
                },
            },
            "required": ["age", "employment_type", "verdict"],
        },
    },
]


# ─── Tool Implementation Functions ─────────────────────────────────────────────


def check_credit_score(credit_score: int) -> str:
    """Check if the credit score meets the minimum eligibility threshold."""
    if credit_score >= EXCELLENT_CREDIT_SCORE:
        category = "Excellent"
        passed = True
    elif credit_score >= MIN_CREDIT_SCORE:
        category = "Good"
        passed = True
    elif credit_score >= 650:
        category = "Fair"
        passed = False  # Below minimum but may warrant manual review
    else:
        category = "Poor"
        passed = False

    return json.dumps({
        "credit_score": credit_score,
        "category": category,
        "passed": passed,
        "minimum_required": MIN_CREDIT_SCORE,
        "message": f"Credit score {credit_score} is {category}. {'Meets' if passed else 'Does not meet'} the minimum requirement of {MIN_CREDIT_SCORE}.",
    })


def check_dti_ratio(
    monthly_income: float, existing_emi: float, loan_emi_estimate: float
) -> str:
    """Check if the EMI-to-Income ratio is within the acceptable limit."""
    if monthly_income <= 0:
        return json.dumps({"error": "Monthly income must be greater than zero.", "passed": False})

    total_emi = existing_emi + loan_emi_estimate
    dti_ratio = total_emi / monthly_income

    passed = dti_ratio <= MAX_DTI_RATIO
    ratio_percent = round(dti_ratio * 100, 1)

    return json.dumps({
        "monthly_income": monthly_income,
        "existing_emi": existing_emi,
        "loan_emi_estimate": loan_emi_estimate,
        "total_emi": total_emi,
        "dti_ratio": round(dti_ratio, 4),
        "dti_ratio_percent": ratio_percent,
        "max_allowed_percent": MAX_DTI_RATIO * 100,
        "passed": passed,
        "message": f"EMI-to-Income ratio is {ratio_percent}%. {'Acceptable' if passed else 'Exceeds the'} maximum limit of {MAX_DTI_RATIO * 100}%.",
    })


def check_age_eligibility(age: int) -> str:
    """Verify the applicant's age falls within the eligible range."""
    passed = MIN_AGE <= age <= MAX_AGE

    return json.dumps({
        "age": age,
        "min_age": MIN_AGE,
        "max_age": MAX_AGE,
        "passed": passed,
        "message": f"Age {age} is {'within' if passed else 'outside'} the eligible range of {MIN_AGE}-{MAX_AGE} years.",
    })


def check_employment_stability(employment_type: str) -> str:
    """Assess the stability score of the applicant's employment type."""
    score = EMPLOYMENT_STABILITY_SCORES.get(employment_type, 0.0)
    passed = score > 0.0

    if score == 1.0:
        level = "High - Salaried employment provides stable income"
    elif score >= 0.75:
        level = "Medium-High - Self-employment income can vary"
    elif score >= 0.60:
        level = "Medium - Contract employment has income uncertainty"
    else:
        level = "None - Unemployed applicants are not eligible"

    return json.dumps({
        "employment_type": employment_type,
        "stability_score": score,
        "stability_level": level,
        "passed": passed,
        "message": f"Employment type '{employment_type}' has a stability score of {score}. {'Eligible' if passed else 'Not eligible'} to proceed.",
    })


def compute_loan_emi(
    loan_amount: float, annual_rate: float = 0.10, tenure_months: int = 60
) -> str:
    """Calculate the estimated monthly EMI using the standard EMI formula."""
    if loan_amount <= 0:
        return json.dumps({"error": "Loan amount must be positive.", "emi": 0})

    # Standard EMI formula: P * r * (1+r)^n / ((1+r)^n - 1)
    monthly_rate = annual_rate / 12
    if monthly_rate == 0:
        emi = loan_amount / tenure_months
    else:
        emi = (
            loan_amount
            * monthly_rate
            * math.pow(1 + monthly_rate, tenure_months)
            / (math.pow(1 + monthly_rate, tenure_months) - 1)
        )

    return json.dumps({
        "loan_amount": loan_amount,
        "annual_rate_percent": annual_rate * 100,
        "tenure_months": tenure_months,
        "monthly_emi": round(emi, 2),
        "total_payment": round(emi * tenure_months, 2),
        "total_interest": round(emi * tenure_months - loan_amount, 2),
    })


def assess_risk_band(
    credit_score: int, dti_ratio: float, employment_score: float
) -> str:
    """
    Compute a composite risk band based on credit score, EMI-to-Income ratio, and employment score.
    Risk bands: LOW, MEDIUM, HIGH, CRITICAL
    """
    # Score each dimension (0.0 = worst, 1.0 = best)
    credit_factor = min(max((credit_score - 500) / 300, 0), 1.0)
    dti_factor = max(1.0 - dti_ratio / MAX_DTI_RATIO, 0)
    employment_factor = employment_score

    # Weighted composite score
    composite = (credit_factor * 0.45) + (dti_factor * 0.35) + (employment_factor * 0.20)

    if composite >= 0.75:
        band = "LOW"
        description = "Low risk - strong financial profile"
    elif composite >= 0.50:
        band = "MEDIUM"
        description = "Medium risk - acceptable profile with minor concerns"
    elif composite >= 0.25:
        band = "HIGH"
        description = "High risk - significant concerns, requires manual review"
    else:
        band = "CRITICAL"
        description = "Critical risk - not recommended for approval"

    return json.dumps({
        "credit_score": credit_score,
        "dti_ratio": round(dti_ratio, 4),
        "employment_score": employment_score,
        "credit_factor": round(credit_factor, 3),
        "dti_factor": round(dti_factor, 3),
        "employment_factor": employment_factor,
        "composite_score": round(composite, 3),
        "risk_band": band,
        "description": description,
    })


def fetch_policy_rules(rule_category: str) -> str:
    """Fetch current policy rules from the LoanRulesMCP server."""
    from observability.metrics import record_mcp_call

    # Map of tool names to call on the MCP server
    category_to_tool = {
        "credit_score": "get_credit_score_threshold",
        "dti": "get_dti_policy",
        "age": "get_age_policy",
        "employment": "get_employment_policy",
        "compliance": "get_compliance_rules",
    }

    tool_name = category_to_tool.get(rule_category, "get_credit_score_threshold")

    try:
        # Call the MCP server via its REST endpoint
        response = requests.post(
            MCP_LOAN_RULES_URL,
            json={"method": "tools/call", "params": {"name": tool_name, "arguments": {}}},
            timeout=3,
        )
        response.raise_for_status()
        record_mcp_call("loan-rules", tool_name, True)
        return response.text
    except Exception as e:
        # Fallback to hard-coded defaults if MCP server is not available
        record_mcp_call("loan-rules", tool_name, False)
        logger.warning(f"MCP server unavailable, using defaults: {e}")

        defaults = {
            "credit_score": {"min_credit_score": 700, "excellent_threshold": 750},
            "dti": {"max_dti_ratio": 0.40, "preferred_dti": 0.30},
            "age": {"min_age": 21, "max_age": 60},
            "employment": {"Salaried": 1.0, "Self-Employed": 0.75, "Contract": 0.60, "Unemployed": 0.0},
            "compliance": {"kyc_required": True, "max_loan_income_ratio": 10},
        }
        return json.dumps(defaults.get(rule_category, {}))


def check_bias_indicators(age: int, employment_type: str, verdict: str) -> str:
    """Check for proxy variable bias indicators in the decision."""
    flags = []

    # Flag if young adults (21-24) are rejected without clear financial reasons
    if age in range(21, 25) and verdict == "NOT_ELIGIBLE":
        flags.append({
            "type": "age_proxy",
            "severity": "medium",
            "note": "Young applicant rejected — verify rejection is based on financial metrics only",
        })

    # Flag if near-retirement age (55-60) is rejected
    if age in range(55, 61) and verdict == "NOT_ELIGIBLE":
        flags.append({
            "type": "age_proxy",
            "severity": "low",
            "note": "Near-retirement applicant — ensure age is not a factor in rejection",
        })

    # Flag if contract/self-employed are rejected at higher rates
    if employment_type in ("Contract", "Self-Employed") and verdict == "NOT_ELIGIBLE":
        flags.append({
            "type": "employment_proxy",
            "severity": "low",
            "note": f"{employment_type} workers face higher rejection rates — verify financial basis",
        })

    bias_risk = "HIGH" if any(f["severity"] == "high" for f in flags) else \
                "MEDIUM" if any(f["severity"] == "medium" for f in flags) else \
                "LOW"

    return json.dumps({
        "age": age,
        "employment_type": employment_type,
        "verdict": verdict,
        "bias_flags": flags,
        "bias_risk": bias_risk,
        "bias_check_passed": len(flags) == 0,
    })


# ─── Tool Dispatcher ───────────────────────────────────────────────────────────

TOOL_FUNCTIONS: dict[str, Any] = {
    "check_credit_score": check_credit_score,
    "check_dti_ratio": check_dti_ratio,
    "check_age_eligibility": check_age_eligibility,
    "check_employment_stability": check_employment_stability,
    "compute_loan_emi": compute_loan_emi,
    "assess_risk_band": assess_risk_band,
    "fetch_policy_rules": fetch_policy_rules,
    "check_bias_indicators": check_bias_indicators,
}


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Dispatch a tool call from the Claude API to the appropriate Python function."""
    fn = TOOL_FUNCTIONS.get(tool_name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    try:
        return fn(**tool_input)
    except TypeError as e:
        return json.dumps({"error": f"Invalid tool arguments: {str(e)}"})
    except Exception as e:
        logger.error(f"Tool {tool_name} failed: {e}")
        return json.dumps({"error": f"Tool execution failed: {str(e)}"})
