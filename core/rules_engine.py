import math
from config.settings import (
    MIN_AGE, MAX_AGE, MIN_CREDIT_SCORE, MAX_DTI_RATIO,
    EMPLOYMENT_STABILITY_SCORES, DEFAULT_ANNUAL_INTEREST_RATE,
    DEFAULT_LOAN_TENURE_MONTHS,
)
from core.models import EligibilityResult, Verdict


class RulesEngine:
    @staticmethod
    def compute_emi(loan_amount: float, annual_rate: float, tenure_months: int) -> float:
        monthly_rate = annual_rate / 12
        if monthly_rate == 0:
            return loan_amount / tenure_months
        n = tenure_months
        return loan_amount * monthly_rate * math.pow(1 + monthly_rate, n) / (math.pow(1 + monthly_rate, n) - 1)

    @staticmethod
    def evaluate(applicant_data: dict) -> EligibilityResult:
        age = applicant_data.get("age", 0)
        credit_score = applicant_data.get("credit_score", 0)
        monthly_income = applicant_data.get("monthly_income", 1)
        existing_emi = applicant_data.get("existing_emi", 0)
        employment_type = applicant_data.get("employment_type", "Unemployed")
        loan_amount = applicant_data.get("loan_amount", 0)
        annual_rate = applicant_data.get("annual_interest_rate", DEFAULT_ANNUAL_INTEREST_RATE)
        tenure = applicant_data.get("loan_tenure_months", DEFAULT_LOAN_TENURE_MONTHS)

        loan_emi = applicant_data.get("estimated_new_emi") or RulesEngine.compute_emi(loan_amount, annual_rate, tenure)
        dti_ratio = (existing_emi + loan_emi) / monthly_income if monthly_income > 0 else 1.0
        employment_score = EMPLOYMENT_STABILITY_SCORES.get(employment_type, 0.0)

        return EligibilityResult(
            age_ok=MIN_AGE <= age <= MAX_AGE,
            credit_score_ok=credit_score >= MIN_CREDIT_SCORE,
            dti_ok=dti_ratio <= MAX_DTI_RATIO,
            employment_ok=employment_score > 0.0,
            credit_score=credit_score,
            dti_ratio=dti_ratio,
            employment_score=employment_score,
            raw_tool_results={"source": "rules_engine"},
        )

    @staticmethod
    def determine_verdict(eligibility: EligibilityResult, risk_band: str) -> Verdict:
        if not eligibility.age_ok or not eligibility.employment_ok:
            return Verdict.NOT_ELIGIBLE
        if risk_band == "CRITICAL":
            return Verdict.NOT_ELIGIBLE
        if eligibility.credit_score_ok and eligibility.dti_ok and risk_band in ("LOW", "MEDIUM"):
            return Verdict.ELIGIBLE
        if risk_band == "HIGH":
            return Verdict.MANUAL_REVIEW
        if eligibility.credit_score_ok or eligibility.dti_ok:
            return Verdict.MANUAL_REVIEW
        return Verdict.NOT_ELIGIBLE
