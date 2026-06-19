"""
ExplainerAgent: Produces the final loan decision verdict and human-readable explanation.

The verdict is determined by hard rules (no AI needed for the outcome).
Claude is used to generate the friendly explanation and recommendations.
"""

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import anthropic

from config import MAX_TOKENS, MIN_CREDIT_SCORE, MAX_DTI_RATIO, MODEL
from observability.tracer import tracer
from observability.metrics import record_token_usage

logger = logging.getLogger(__name__)


class Verdict(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    MANUAL_REVIEW = "MANUAL_REVIEW"


@dataclass
class EligibilityResult:
    """Structured output from EligibilityCheckerAgent."""
    age_ok: bool
    credit_score_ok: bool
    dti_ok: bool
    employment_ok: bool
    credit_score: int
    dti_ratio: float
    employment_score: float
    raw_tool_results: dict


@dataclass
class LoanDecision:
    """Final output of the entire agent pipeline."""
    verdict: Verdict
    reasons: list
    recommendations: list
    emi_to_income_ratio: float
    dti_ratio: float
    risk_band: str
    explanation: str
    model_used: str
    tool_calls_count: int


class ExplainerAgent:
    """
    Determines the final verdict using rule-based logic, then uses Claude
    to generate a clear, friendly explanation of the decision.
    """

    def __init__(self, client: anthropic.Anthropic):
        self.client = client

    def run(
        self,
        eligibility: EligibilityResult,
        risk_band: str,
        applicant_data: dict,
        trace_id: str,
    ) -> LoanDecision:
        with tracer.trace_span(trace_id, "explainer", "ExplainerAgent"):
            verdict = self._determine_verdict(eligibility, risk_band)
            reasons = self._collect_reasons(eligibility, risk_band, applicant_data)
            explanation = self._generate_explanation(
                verdict, reasons, eligibility, risk_band, applicant_data, trace_id
            )
            recommendations = self._generate_recommendations(verdict, eligibility, applicant_data)

            # EMI-to-income ratio for display
            monthly_income = applicant_data.get("monthly_income", 1)
            existing_emi = applicant_data.get("existing_emi", 0)
            emi_to_income_ratio = existing_emi / monthly_income if monthly_income > 0 else 0.0

            tracer.log_decision(trace_id, verdict.value, eligibility.dti_ratio)

            return LoanDecision(
                verdict=verdict,
                reasons=reasons,
                recommendations=recommendations,
                emi_to_income_ratio=round(emi_to_income_ratio, 4),
                dti_ratio=round(eligibility.dti_ratio, 4),
                risk_band=risk_band,
                explanation=explanation,
                model_used=MODEL,
                tool_calls_count=len(eligibility.raw_tool_results),
            )

    def _determine_verdict(self, eligibility: EligibilityResult, risk_band: str) -> Verdict:
        """
        Rule-based verdict logic — deterministic, no AI involved.

        Rules:
        1. Age or employment failures → NOT_ELIGIBLE (hard disqualifiers)
        2. Credit + EMI-to-Income both pass + low/medium risk → ELIGIBLE
        3. Critical risk → NOT_ELIGIBLE
        4. Everything else → MANUAL_REVIEW
        """
        # Hard disqualifiers
        if not eligibility.age_ok:
            return Verdict.NOT_ELIGIBLE
        if not eligibility.employment_ok:
            return Verdict.NOT_ELIGIBLE

        # Critical risk is an automatic rejection
        if risk_band == "CRITICAL":
            return Verdict.NOT_ELIGIBLE

        # Clear approval
        if (eligibility.credit_score_ok
                and eligibility.dti_ok
                and risk_band in ("LOW", "MEDIUM")):
            return Verdict.ELIGIBLE

        # High risk → manual review
        if risk_band == "HIGH":
            return Verdict.MANUAL_REVIEW

        # Partial pass → manual review
        if eligibility.credit_score_ok or eligibility.dti_ok:
            return Verdict.MANUAL_REVIEW

        # Neither credit nor DTI passes → reject
        return Verdict.NOT_ELIGIBLE

    def _collect_reasons(
        self, eligibility: EligibilityResult, risk_band: str, applicant_data: dict
    ) -> list:
        """Build a list of specific reasons for the decision."""
        reasons = []
        credit_score = applicant_data.get("credit_score", 0)
        age = applicant_data.get("age", 0)
        employment_type = applicant_data.get("employment_type", "")
        loan_amount = applicant_data.get("loan_amount", 0)
        monthly_income = applicant_data.get("monthly_income", 1)

        # Credit score reason
        if eligibility.credit_score_ok:
            reasons.append(f"Credit score {credit_score} meets the minimum requirement of {MIN_CREDIT_SCORE}")
        else:
            reasons.append(f"Credit score {credit_score} is below the minimum requirement of {MIN_CREDIT_SCORE}")

        # EMI-to-income (DTI) reason — break down the numbers so the user understands
        dti_pct = round(eligibility.dti_ratio * 100, 1)
        existing_emi = applicant_data.get("existing_emi", 0)
        new_emi = applicant_data.get("estimated_new_emi", 0)
        tenure = applicant_data.get("loan_tenure_months", 60)
        rate_pct = round(applicant_data.get("annual_interest_rate", 0.10) * 100, 1)
        if eligibility.dti_ok:
            reasons.append(
                f"EMI-to-income ratio {dti_pct}% is within the 40% limit "
                f"(Existing EMI ₹{existing_emi:,.0f} + New EMI ₹{new_emi:,.0f} "
                f"over {tenure} months @ {rate_pct}%)"
            )
        else:
            reasons.append(
                f"EMI-to-income ratio {dti_pct}% exceeds the 40% limit "
                f"(Existing EMI ₹{existing_emi:,.0f} + New EMI ₹{new_emi:,.0f} "
                f"over {tenure} months @ {rate_pct}%)"
            )

        # Age reason
        if eligibility.age_ok:
            reasons.append(f"Age {age} is within the eligible range of 21–60 years")
        else:
            reasons.append(f"Age {age} is outside the eligible range of 21–60 years")

        # Employment reason
        if eligibility.employment_ok:
            reasons.append(f"Employment type '{employment_type}' meets stability requirements")
        else:
            reasons.append(f"Employment type '{employment_type}' does not meet eligibility criteria")

        # Loan-to-income reason
        annual_income = monthly_income * 12
        lti_ratio = loan_amount / annual_income if annual_income > 0 else float("inf")
        if lti_ratio <= 10:
            reasons.append(f"Loan amount to annual income ratio ({round(lti_ratio, 1)}x) is acceptable")
        else:
            reasons.append(f"Loan amount to annual income ratio ({round(lti_ratio, 1)}x) is very high")

        # Risk band reason
        reasons.append(f"Overall risk assessment: {risk_band}")

        return reasons

    def _generate_explanation(
        self,
        verdict: Verdict,
        reasons: list,
        eligibility: EligibilityResult,
        risk_band: str,
        applicant_data: dict,
        trace_id: str,
    ) -> str:
        """Use Claude to generate a friendly, plain-English explanation."""
        prompt = f"""You are a friendly loan officer explaining a loan decision to a customer.

Applicant Profile:
- Age: {applicant_data.get('age')}
- Monthly Income: ₹{applicant_data.get('monthly_income'):,}
- Existing EMI: ₹{applicant_data.get('existing_emi'):,}
- Credit Score: {applicant_data.get('credit_score')}
- Employment: {applicant_data.get('employment_type')}
- Loan Requested: ₹{applicant_data.get('loan_amount'):,}

Decision: {verdict.value}
Risk Level: {risk_band}

Key Reasons:
{chr(10).join(f'- {r}' for r in reasons)}

Write a 3-4 sentence explanation in simple, friendly language that a customer can understand.
Do NOT use jargon. Be empathetic but clear. If not eligible, suggest what they can improve."""

        try:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            record_token_usage("ExplainerAgent",
                               getattr(response.usage, "input_tokens", 0),
                               getattr(response.usage, "output_tokens", 0))
            return response.content[0].text.strip()
        except Exception as e:
            logger.error(f"ExplainerAgent API call failed: {e}", extra={"trace_id": trace_id})
            # Fallback explanation
            if verdict == Verdict.ELIGIBLE:
                return "Congratulations! Based on your financial profile, you are eligible for the loan. Your credit score and debt levels meet our requirements."
            elif verdict == Verdict.NOT_ELIGIBLE:
                return "We were unable to approve your loan application at this time. Please review the reasons listed above and consider re-applying after improvements."
            else:
                return "Your application requires additional review by our loan officers. You will be contacted within 2-3 business days."

    def _generate_recommendations(
        self, verdict: Verdict, eligibility: EligibilityResult, applicant_data: dict
    ) -> list:
        """Generate actionable recommendations based on the decision."""
        recs = []

        if verdict == Verdict.ELIGIBLE:
            recs.append("Proceed with your loan application — you qualify!")
            recs.append("Consider a shorter tenure to reduce total interest paid")
        else:
            if not eligibility.credit_score_ok:
                recs.append("Improve your credit score by paying existing loans on time")
                recs.append("Reduce credit card utilization below 30% to boost your score")
            if not eligibility.dti_ok:
                recs.append("Pay off existing EMIs to reduce your EMI-to-income ratio")
                recs.append("Request a smaller loan amount or longer tenure to lower EMI")
            if not eligibility.age_ok:
                recs.append("Age eligibility is a hard requirement — please contact our branch")
            if not eligibility.employment_ok:
                recs.append("Stable employment significantly improves loan eligibility")

        return recs
