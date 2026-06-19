"""
In-memory loan policy database loaded from policies.yaml.
Provides up-to-date policy rules to the LoanRulesMCP server.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Default policies — used if policies.yaml is not found
DEFAULT_POLICIES: dict[str, Any] = {
    "credit_score": {
        "min_credit_score": 700,
        "excellent_threshold": 750,
        "fair_threshold": 650,
        "description": "Minimum credit score for loan approval is 700. Above 750 is excellent.",
    },
    "dti": {
        "max_dti_ratio": 0.40,
        "preferred_dti": 0.30,
        "description": "Total EMI (existing + new) must not exceed 40% of monthly income.",
    },
    "age": {
        "min_age": 21,
        "max_age": 60,
        "description": "Applicants must be between 21 and 60 years of age.",
    },
    "employment": {
        "Salaried": {"stability_score": 1.0, "description": "Highest stability — regular monthly income"},
        "Self-Employed": {"stability_score": 0.75, "description": "Good stability — income may vary seasonally"},
        "Contract": {"stability_score": 0.60, "description": "Moderate stability — fixed-term employment"},
        "Unemployed": {"stability_score": 0.0, "description": "Not eligible — no stable income source"},
    },
    "loan_products": {
        "personal_loan": {
            "min_amount": 50000,
            "max_amount": 2000000,
            "default_tenure_months": 60,
            "default_annual_rate": 0.10,
        },
        "home_loan": {
            "min_amount": 500000,
            "max_amount": 50000000,
            "default_tenure_months": 240,
            "default_annual_rate": 0.085,
        },
        "auto_loan": {
            "min_amount": 100000,
            "max_amount": 5000000,
            "default_tenure_months": 84,
            "default_annual_rate": 0.095,
        },
    },
    "compliance": {
        "kyc_required": True,
        "max_loan_income_ratio": 10,
        "regulatory_framework": "RBI_FAIR_LENDING_2023",
        "fair_lending_policy": "All decisions based solely on financial merit",
        "audit_retention_years": 7,
    },
}


def load_policies() -> dict[str, Any]:
    """Load policies from YAML file if available, else return defaults."""
    yaml_path = os.path.join(os.path.dirname(__file__), "..", "policies.yaml")
    if os.path.exists(yaml_path):
        try:
            import yaml
            with open(yaml_path, "r") as f:
                custom = yaml.safe_load(f)
            if custom:
                # Merge custom policies over defaults
                merged = {**DEFAULT_POLICIES, **custom}
                logger.info("Loaded custom policies from policies.yaml")
                return merged
        except Exception as e:
            logger.warning(f"Failed to load policies.yaml, using defaults: {e}")

    return DEFAULT_POLICIES


# Module-level singleton — loaded once at import time
POLICIES: dict[str, Any] = load_policies()
