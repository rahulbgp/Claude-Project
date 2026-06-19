"""
RiskAssessorAgent: Uses Claude with tools to compute a composite risk band.

Calls tools: compute_loan_emi, check_dti_ratio, assess_risk_band, check_employment_stability
Returns a RiskBand enum: LOW / MEDIUM / HIGH / CRITICAL
"""

import json
import logging
from typing import Optional

import anthropic

from config import MODEL, MAX_TOKENS, DEFAULT_ANNUAL_INTEREST_RATE, DEFAULT_LOAN_TENURE_MONTHS
from tools.loan_tools import TOOL_SCHEMAS, execute_tool
from observability.tracer import tracer

logger = logging.getLogger(__name__)

# Only the risk-relevant tools for this agent
RISK_TOOL_NAMES = {"compute_loan_emi", "assess_risk_band", "check_employment_stability"}
RISK_TOOLS = [t for t in TOOL_SCHEMAS if t["name"] in RISK_TOOL_NAMES]


class RiskAssessorAgent:
    """
    Assesses overall loan risk using an agentic tool-use loop.
    Claude decides which tools to call to compute the composite risk band.
    """

    def __init__(self, client: anthropic.Anthropic):
        self.client = client

    def run(
        self,
        applicant_data: dict,
        eligibility_dti_ratio: float,
        trace_id: str,
    ) -> str:
        """
        Returns a risk band string: 'LOW', 'MEDIUM', 'HIGH', or 'CRITICAL'.
        Falls back to rule-based assessment if the API call fails.
        """
        with tracer.trace_span(trace_id, "risk_assessment", "RiskAssessorAgent"):
            try:
                return self._run_agent_loop(applicant_data, eligibility_dti_ratio, trace_id)
            except Exception as e:
                logger.error(
                    f"RiskAssessorAgent failed, using fallback: {e}",
                    extra={"trace_id": trace_id},
                )
                return self._fallback_risk_assessment(applicant_data, eligibility_dti_ratio)

    def _run_agent_loop(
        self, applicant_data: dict, dti_ratio: float, trace_id: str
    ) -> str:
        """Run the Claude tool-use loop to assess risk."""
        credit_score = applicant_data.get("credit_score", 600)
        employment_type = applicant_data.get("employment_type", "Unemployed")
        loan_amount = applicant_data.get("loan_amount", 0)

        # Employment score from our lookup table
        from config import EMPLOYMENT_STABILITY_SCORES
        employment_score = EMPLOYMENT_STABILITY_SCORES.get(employment_type, 0.0)

        messages = [
            {
                "role": "user",
                "content": (
                    f"Assess the risk for this loan application:\n"
                    f"- Credit score: {credit_score}\n"
                    f"- EMI-to-Income ratio: {round(dti_ratio * 100, 1)}%\n"
                    f"- Employment type: {employment_type} (stability score: {employment_score})\n"
                    f"- Loan amount: ₹{loan_amount:,}\n\n"
                    f"Use the assess_risk_band tool to determine the risk band. "
                    f"If needed, use compute_loan_emi to get the estimated EMI first. "
                    f"Return the final risk band: LOW, MEDIUM, HIGH, or CRITICAL."
                ),
            }
        ]

        tool_calls_count = 0

        # Agentic loop: Claude calls tools until it has the answer
        for _ in range(5):  # Max 5 tool-use rounds
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=512,
                tools=RISK_TOOLS,
                messages=messages,
            )

            # Collect tool_use blocks
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            if not tool_use_blocks:
                # Claude stopped requesting tools — extract the risk band from text
                return self._extract_risk_band(response)

            # Execute all tool calls and feed results back
            tool_results = []
            for block in tool_use_blocks:
                tool_calls_count += 1
                result = execute_tool(block.name, block.input)
                logger.debug(
                    f"Tool called: {block.name}",
                    extra={"trace_id": trace_id, "tool": block.name},
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

            # Add assistant message and tool results to the conversation
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        # Max rounds reached — fall back
        return self._fallback_risk_assessment(applicant_data, dti_ratio)

    def _extract_risk_band(self, response) -> str:
        """Extract the risk band string from Claude's final text response."""
        for block in response.content:
            if hasattr(block, "text"):
                text = block.text.upper()
                for band in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
                    if band in text:
                        return band

                # Try to extract from tool result if available
                try:
                    data = json.loads(block.text)
                    return data.get("risk_band", "MEDIUM")
                except Exception:
                    pass

        return "MEDIUM"  # Safe default

    def _fallback_risk_assessment(
        self, applicant_data: dict, dti_ratio: float
    ) -> str:
        """Pure rule-based risk assessment used when the API is unavailable."""
        credit_score = applicant_data.get("credit_score", 600)
        employment_type = applicant_data.get("employment_type", "Unemployed")

        from config import EMPLOYMENT_STABILITY_SCORES, EXCELLENT_CREDIT_SCORE, MIN_CREDIT_SCORE
        employment_score = EMPLOYMENT_STABILITY_SCORES.get(employment_type, 0.0)

        if employment_score == 0.0:
            return "CRITICAL"
        if credit_score >= EXCELLENT_CREDIT_SCORE and dti_ratio <= 0.30:
            return "LOW"
        if credit_score >= MIN_CREDIT_SCORE and dti_ratio <= 0.40:
            return "MEDIUM"
        if credit_score >= 650 or dti_ratio <= 0.50:
            return "HIGH"
        return "CRITICAL"
