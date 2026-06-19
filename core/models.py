from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    MANUAL_REVIEW = "MANUAL_REVIEW"


@dataclass
class EligibilityResult:
    age_ok: bool
    credit_score_ok: bool
    dti_ok: bool
    employment_ok: bool
    credit_score: int
    dti_ratio: float
    employment_score: float
    raw_tool_results: dict = field(default_factory=dict)


@dataclass
class LoanDecision:
    verdict: Verdict
    reasons: list
    recommendations: list
    emi_to_income_ratio: float
    dti_ratio: float
    risk_band: str
    explanation: str
    model_used: str
    tool_calls_count: int
