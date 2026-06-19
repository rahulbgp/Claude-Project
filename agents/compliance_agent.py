"""
ComplianceAgent: Validates that a loan decision meets regulatory requirements.
Checks RBI Fair Lending compliance, data classification, PII handling,
access control markers, and bias risk before the decision is finalised.
"""

import json
import logging

import anthropic

from config import MODEL, MAX_TOKENS, REGULATORY_FRAMEWORK
from observability.tracer import tracer
from observability.metrics import record_agent_failure

logger = logging.getLogger(__name__)

COMPLIANCE_TOOLS = [
    {
        "name": "check_regulatory_compliance",
        "description": "Verify the decision meets RBI Fair Lending Guidelines 2023.",
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["ELIGIBLE", "NOT_ELIGIBLE", "MANUAL_REVIEW"]},
                "reasons": {"type": "array", "items": {"type": "string"}},
                "age": {"type": "integer"},
                "employment_type": {"type": "string"},
            },
            "required": ["verdict", "reasons", "age", "employment_type"],
        },
    },
    {
        "name": "classify_data_sensitivity",
        "description": "Classify the sensitivity level of each data field in the application.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fields": {"type": "array", "items": {"type": "string"},
                           "description": "List of field names to classify"},
            },
            "required": ["fields"],
        },
    },
    {
        "name": "validate_decision_explainability",
        "description": "Check that the decision has sufficient explanation for regulatory purposes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string"},
                "reasons_count": {"type": "integer"},
                "has_explanation": {"type": "boolean"},
                "has_recommendations": {"type": "boolean"},
            },
            "required": ["verdict", "reasons_count", "has_explanation", "has_recommendations"],
        },
    },
    {
        "name": "check_human_oversight_required",
        "description": "Determine if the decision requires mandatory human review under compliance rules.",
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string"},
                "risk_band": {"type": "string"},
                "bias_flags_count": {"type": "integer"},
            },
            "required": ["verdict", "risk_band", "bias_flags_count"],
        },
    },
]

DATA_CLASSIFICATION = {
    "name": "PII_HIGH",
    "age": "PII_MEDIUM",
    "monthly_income": "FINANCIAL_SENSITIVE",
    "existing_emi": "FINANCIAL_SENSITIVE",
    "credit_score": "FINANCIAL_SENSITIVE",
    "employment_type": "PII_LOW",
    "loan_amount": "FINANCIAL_SENSITIVE",
}


def _execute_compliance_tool(name: str, inputs: dict) -> str:
    if name == "check_regulatory_compliance":
        verdict = inputs.get("verdict", "")
        reasons = inputs.get("reasons", [])
        age = inputs.get("age", 35)
        employment_type = inputs.get("employment_type", "Salaried")
        issues = []
        # Check: rejection must have financial reasons, not demographic
        if verdict == "NOT_ELIGIBLE":
            demographic_terms = ["gender", "race", "religion", "caste", "region"]
            demographic_reasons = [r for r in reasons if any(t in r.lower() for t in demographic_terms)]
            if demographic_reasons:
                issues.append(f"Rejection contains potentially discriminatory reasons: {demographic_reasons}")
        # Check: age-based rejection must be documented as eligibility criterion
        if verdict == "NOT_ELIGIBLE" and (age < 21 or age > 60):
            age_documented = any("age" in r.lower() for r in reasons)
            if not age_documented:
                issues.append("Age-based rejection not documented in reasons")
        compliant = len(issues) == 0
        return json.dumps({
            "compliant": compliant,
            "framework": REGULATORY_FRAMEWORK,
            "issues": issues,
            "verdict": verdict,
        })

    if name == "classify_data_sensitivity":
        fields = inputs.get("fields", [])
        classification = {f: DATA_CLASSIFICATION.get(f, "INTERNAL") for f in fields}
        pii_fields = [f for f, c in classification.items() if "PII" in c]
        return json.dumps({
            "classification": classification,
            "pii_fields": pii_fields,
            "has_high_pii": any("HIGH" in c for c in classification.values()),
        })

    if name == "validate_decision_explainability":
        verdict = inputs.get("verdict", "")
        reasons_count = inputs.get("reasons_count", 0)
        has_explanation = inputs.get("has_explanation", False)
        has_recommendations = inputs.get("has_recommendations", False)
        issues = []
        if reasons_count < 2:
            issues.append("Insufficient reasons for regulatory explainability")
        if not has_explanation:
            issues.append("Missing plain-language explanation")
        if verdict == "NOT_ELIGIBLE" and not has_recommendations:
            issues.append("Rejection must include improvement recommendations")
        return json.dumps({
            "explainable": len(issues) == 0,
            "issues": issues,
            "reasons_count": reasons_count,
        })

    if name == "check_human_oversight_required":
        verdict = inputs.get("verdict", "")
        risk_band = inputs.get("risk_band", "LOW")
        bias_count = inputs.get("bias_flags_count", 0)
        required = (verdict == "MANUAL_REVIEW" or risk_band == "HIGH" or bias_count > 0)
        reasons = []
        if verdict == "MANUAL_REVIEW":
            reasons.append("Verdict requires manual review")
        if risk_band == "HIGH":
            reasons.append("High risk band requires human oversight")
        if bias_count > 0:
            reasons.append(f"{bias_count} bias flag(s) detected")
        return json.dumps({
            "human_oversight_required": required,
            "reasons": reasons,
        })

    return json.dumps({"error": f"Unknown tool: {name}"})


class ComplianceAgent:
    """
    Validates regulatory compliance of a loan decision.
    Returns a ComplianceResult dict with compliant flag, issues, and data classification.
    """

    def __init__(self, client: anthropic.Anthropic):
        self.client = client

    def run(self, decision, applicant_data: dict, bias_flags: list, trace_id: str) -> dict:
        """
        Validates the decision against compliance rules.
        Returns dict: compliant, issues, data_classification, human_oversight_required.
        """
        with tracer.trace_span(trace_id, "compliance_validation", "ComplianceAgent"):
            try:
                return self._run_agent_loop(decision, applicant_data, bias_flags, trace_id)
            except Exception as e:
                logger.error(f"ComplianceAgent failed, using fallback: {e}",
                             extra={"trace_id": trace_id})
                record_agent_failure("ComplianceAgent", type(e).__name__)
                return self._fallback_compliance(decision, applicant_data, bias_flags)

    def _run_agent_loop(self, decision, applicant_data: dict, bias_flags: list, trace_id: str) -> dict:
        verdict = decision.verdict.value if hasattr(decision.verdict, "value") else str(decision.verdict)
        messages = [{
            "role": "user",
            "content": (
                f"Validate compliance for this loan decision:\n"
                f"Verdict: {verdict}, Risk Band: {decision.risk_band}\n"
                f"Age: {applicant_data.get('age')}, Employment: {applicant_data.get('employment_type')}\n"
                f"Reasons ({len(decision.reasons)}): {decision.reasons[:3]}\n"
                f"Bias flags: {len(bias_flags)}\n\n"
                f"Run all 4 compliance checks and return a JSON with: "
                f"compliant (bool), issues (list), human_oversight_required (bool)."
            ),
        }]

        raw_results = {}
        for _ in range(5):
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=600,
                tools=COMPLIANCE_TOOLS,
                messages=messages,
            )
            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            if not tool_blocks:
                return self._parse_compliance_response(response, raw_results, decision, applicant_data, bias_flags)

            results = []
            for block in tool_blocks:
                result = _execute_compliance_tool(block.name, block.input)
                raw_results[block.name] = json.loads(result)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": results})

        return self._fallback_compliance(decision, applicant_data, bias_flags)

    def _parse_compliance_response(self, response, raw_results, decision, applicant_data, bias_flags) -> dict:
        for block in response.content:
            if hasattr(block, "text"):
                text = block.text.strip()
                s, e = text.find("{"), text.rfind("}") + 1
                if s >= 0 and e > s:
                    try:
                        data = json.loads(text[s:e])
                        return {
                            "compliant": data.get("compliant", True),
                            "issues": data.get("issues", []),
                            "human_oversight_required": data.get("human_oversight_required", False),
                            "data_classification": DATA_CLASSIFICATION,
                            "framework": REGULATORY_FRAMEWORK,
                        }
                    except json.JSONDecodeError:
                        pass
        return self._fallback_compliance(decision, applicant_data, bias_flags)

    def _fallback_compliance(self, decision, applicant_data: dict, bias_flags: list) -> dict:
        verdict = decision.verdict.value if hasattr(decision.verdict, "value") else str(decision.verdict)
        issues = []
        if len(decision.reasons) < 2:
            issues.append("Insufficient decision reasons")
        human_oversight = (verdict == "MANUAL_REVIEW" or decision.risk_band == "HIGH" or len(bias_flags) > 0)
        return {
            "compliant": len(issues) == 0,
            "issues": issues,
            "human_oversight_required": human_oversight,
            "data_classification": DATA_CLASSIFICATION,
            "framework": REGULATORY_FRAMEWORK,
        }
