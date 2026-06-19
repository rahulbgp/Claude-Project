"""
EligibilityCheckerAgent: Uses Claude with tools to evaluate all loan eligibility criteria.

Runs an agentic tool-use loop calling:
  check_credit_score, check_dti_ratio, check_age_eligibility,
  check_employment_stability, compute_loan_emi, fetch_policy_rules

Returns an EligibilityResult dataclass.
"""

import json
import logging
from typing import Optional

import anthropic

from agents.explainer import EligibilityResult
from config import (
    DEFAULT_ANNUAL_INTEREST_RATE,
    DEFAULT_LOAN_TENURE_MONTHS,
    EMPLOYMENT_STABILITY_SCORES,
    MAX_DTI_RATIO,
    MAX_TOKENS,
    MIN_AGE,
    MAX_AGE,
    MIN_CREDIT_SCORE,
    MODEL,
)
from tools.loan_tools import TOOL_SCHEMAS, execute_tool
from observability.tracer import tracer

logger = logging.getLogger(__name__)

# Tools used by this agent
ELIGIBILITY_TOOL_NAMES = {
    "check_credit_score",
    "check_dti_ratio",
    "check_age_eligibility",
    "check_employment_stability",
    "compute_loan_emi",
    "fetch_policy_rules",
}
ELIGIBILITY_TOOLS = [t for t in TOOL_SCHEMAS if t["name"] in ELIGIBILITY_TOOL_NAMES]


class EligibilityCheckerAgent:
    """
    Runs an agentic tool-use loop to evaluate all eligibility criteria.
    Claude decides which tools to call and in what order.
    """

    def __init__(self, client: anthropic.Anthropic):
        self.client = client

    def run(self, applicant_data: dict, trace_id: str) -> EligibilityResult:
        """
        Run the eligibility check.
        Falls back to rule-based checks if the API call fails.
        """
        with tracer.trace_span(trace_id, "eligibility_check", "EligibilityCheckerAgent"):
            try:
                return self._run_agent_loop(applicant_data, trace_id)
            except Exception as e:
                logger.error(
                    f"EligibilityCheckerAgent failed, using fallback: {e}",
                    extra={"trace_id": trace_id},
                )
                return self._fallback_eligibility(applicant_data)

    def _run_agent_loop(self, applicant_data: dict, trace_id: str) -> EligibilityResult:
        """Run the Claude tool-use loop for eligibility checking."""
        estimated_new_emi = applicant_data.get("estimated_new_emi", 0)
        tenure = applicant_data.get("loan_tenure_months", 60)
        rate_pct = round(applicant_data.get("annual_interest_rate", 0.10) * 100, 1)

        messages = [
            {
                "role": "user",
                "content": (
                    f"Check the loan eligibility for this applicant:\n"
                    f"- Name: {applicant_data.get('name', 'Applicant')}\n"
                    f"- Age: {applicant_data.get('age')}\n"
                    f"- Monthly Income: ₹{applicant_data.get('monthly_income'):,}\n"
                    f"- Existing EMI: ₹{applicant_data.get('existing_emi'):,}\n"
                    f"- Credit Score: {applicant_data.get('credit_score')}\n"
                    f"- Employment Type: {applicant_data.get('employment_type')}\n"
                    f"- Loan Amount Requested: ₹{applicant_data.get('loan_amount'):,}\n"
                    f"- Loan Tenure: {tenure} months\n"
                    f"- Annual Interest Rate: {rate_pct}%\n"
                    f"- Pre-computed New Loan EMI: ₹{estimated_new_emi:,.0f}/month "
                    f"(already calculated using the above tenure and rate — use this value directly)\n\n"
                    f"Please check ALL of the following using the available tools:\n"
                    f"1. Fetch the current policy rules (credit_score category)\n"
                    f"2. Check age eligibility\n"
                    f"3. Check employment stability\n"
                    f"4. Check the credit score\n"
                    f"5. Check the EMI-to-Income ratio using check_dti_ratio with "
                    f"loan_emi_estimate=₹{estimated_new_emi:,.0f} (the pre-computed EMI above)\n\n"
                    f"After checking all criteria, provide a JSON summary with these fields:\n"
                    f"age_ok, credit_score_ok, dti_ok, employment_ok, dti_ratio, employment_score"
                ),
            }
        ]

        raw_tool_results = {}
        tool_calls_count = 0

        # Agentic loop
        for _ in range(8):  # Max 8 tool-use rounds
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                tools=ELIGIBILITY_TOOLS,
                messages=messages,
            )

            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            if not tool_use_blocks:
                # Claude is done calling tools — parse the final response
                return self._parse_final_response(response, applicant_data, raw_tool_results)

            # Execute tools and collect results
            tool_results = []
            for block in tool_use_blocks:
                tool_calls_count += 1
                result = execute_tool(block.name, block.input)
                raw_tool_results[block.name] = json.loads(result) if result else {}
                logger.debug(
                    f"Tool called: {block.name}",
                    extra={"trace_id": trace_id, "tool": block.name},
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        # Max rounds reached — fall back
        return self._fallback_eligibility(applicant_data)

    def _parse_final_response(
        self, response, applicant_data: dict, raw_tool_results: dict
    ) -> EligibilityResult:
        """Parse Claude's final text response to extract the EligibilityResult."""
        # Try to find a JSON block in the response
        for block in response.content:
            if hasattr(block, "text"):
                text = block.text.strip()
                # Look for JSON in the response
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    try:
                        data = json.loads(text[start:end])
                        # Always recompute dti_ratio from the pre-computed EMI so that
                        # changing tenure / interest rate is reflected correctly.
                        monthly_income = applicant_data.get("monthly_income", 1)
                        existing_emi = applicant_data.get("existing_emi", 0)
                        loan_emi = applicant_data.get("estimated_new_emi", 0)
                        dti_ratio = (existing_emi + loan_emi) / monthly_income if monthly_income > 0 else 1.0
                        return EligibilityResult(
                            age_ok=bool(data.get("age_ok", False)),
                            credit_score_ok=bool(data.get("credit_score_ok", False)),
                            dti_ok=dti_ratio <= MAX_DTI_RATIO,
                            employment_ok=bool(data.get("employment_ok", False)),
                            credit_score=applicant_data.get("credit_score", 0),
                            dti_ratio=dti_ratio,
                            employment_score=float(data.get("employment_score", 0.0)),
                            raw_tool_results=raw_tool_results,
                        )
                    except json.JSONDecodeError:
                        pass

        # If JSON parsing fails, reconstruct from raw tool results
        return self._build_result_from_tools(raw_tool_results, applicant_data)

    def _build_result_from_tools(
        self, raw_tool_results: dict, applicant_data: dict
    ) -> EligibilityResult:
        """Reconstruct EligibilityResult from raw tool call outputs."""
        credit_result = raw_tool_results.get("check_credit_score", {})
        dti_result = raw_tool_results.get("check_dti_ratio", {})
        age_result = raw_tool_results.get("check_age_eligibility", {})
        emp_result = raw_tool_results.get("check_employment_stability", {})
        emi_result = raw_tool_results.get("compute_loan_emi", {})

        # Always use the pre-computed EMI from app.py so tenure/rate changes
        # are reflected. Fall back to tool result only if app.py didn't provide it.
        monthly_income = applicant_data.get("monthly_income", 1)
        existing_emi = applicant_data.get("existing_emi", 0)
        loan_emi = (applicant_data.get("estimated_new_emi")
                    or emi_result.get("monthly_emi", 0))
        dti_ratio = (existing_emi + loan_emi) / monthly_income if monthly_income > 0 else 1.0

        return EligibilityResult(
            age_ok=age_result.get("passed", False),
            credit_score_ok=credit_result.get("passed", False),
            dti_ok=dti_ratio <= MAX_DTI_RATIO,
            employment_ok=emp_result.get("passed", False),
            credit_score=applicant_data.get("credit_score", 0),
            dti_ratio=dti_ratio,
            employment_score=emp_result.get("stability_score", 0.0),
            raw_tool_results=raw_tool_results,
        )

    def _fallback_eligibility(self, applicant_data: dict) -> EligibilityResult:
        """Pure rule-based fallback when the API is unavailable (self-healing)."""
        age = applicant_data.get("age", 0)
        credit_score = applicant_data.get("credit_score", 0)
        monthly_income = applicant_data.get("monthly_income", 1)
        existing_emi = applicant_data.get("existing_emi", 0)
        employment_type = applicant_data.get("employment_type", "Unemployed")
        loan_amount = applicant_data.get("loan_amount", 0)

        # Use user-supplied loan terms if available, else fall back to config defaults
        annual_rate = applicant_data.get("annual_interest_rate", DEFAULT_ANNUAL_INTEREST_RATE)
        n = applicant_data.get("loan_tenure_months", DEFAULT_LOAN_TENURE_MONTHS)

        # If the app already computed the EMI, reuse it directly (avoids rounding drift)
        if "estimated_new_emi" in applicant_data:
            loan_emi = applicant_data["estimated_new_emi"]
        else:
            import math
            monthly_rate = annual_rate / 12
            if monthly_rate > 0:
                loan_emi = (loan_amount * monthly_rate * math.pow(1 + monthly_rate, n)
                            / (math.pow(1 + monthly_rate, n) - 1))
            else:
                loan_emi = loan_amount / n

        total_emi = existing_emi + loan_emi
        dti_ratio = total_emi / monthly_income if monthly_income > 0 else 1.0
        employment_score = EMPLOYMENT_STABILITY_SCORES.get(employment_type, 0.0)

        return EligibilityResult(
            age_ok=MIN_AGE <= age <= MAX_AGE,
            credit_score_ok=credit_score >= MIN_CREDIT_SCORE,
            dti_ok=dti_ratio <= MAX_DTI_RATIO,
            employment_ok=employment_score > 0.0,
            credit_score=credit_score,
            dti_ratio=dti_ratio,
            employment_score=employment_score,
            raw_tool_results={"fallback": True},
        )
