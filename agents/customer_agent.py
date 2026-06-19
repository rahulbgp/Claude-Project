"""
CustomerAgent: Handles customer-facing interactions.
Validates customer identity context, fetches customer profile from the MCP customer
information server, and prepares a customer context dict for downstream agents.
"""

import json
import logging
from typing import Optional

import anthropic

from config import MODEL, MAX_TOKENS
from observability.tracer import tracer
from observability.metrics import record_agent_failure

logger = logging.getLogger(__name__)

CUSTOMER_TOOLS = [
    {
        "name": "validate_customer_identity",
        "description": "Validate that the customer-provided details are internally consistent (age, name format, employment type).",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "employment_type": {"type": "string"},
            },
            "required": ["name", "age", "employment_type"],
        },
    },
    {
        "name": "classify_customer_segment",
        "description": "Classify the customer into a segment based on income and employment profile.",
        "input_schema": {
            "type": "object",
            "properties": {
                "monthly_income": {"type": "number"},
                "employment_type": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["monthly_income", "employment_type", "age"],
        },
    },
    {
        "name": "assess_data_completeness",
        "description": "Check that all mandatory fields are present and flag any missing optional fields.",
        "input_schema": {
            "type": "object",
            "properties": {
                "applicant_data": {
                    "type": "object",
                    "description": "The full applicant data dict",
                },
            },
            "required": ["applicant_data"],
        },
    },
]


def _execute_customer_tool(name: str, inputs: dict) -> str:
    if name == "validate_customer_identity":
        age = inputs.get("age", 0)
        employment_type = inputs.get("employment_type", "")
        name_val = inputs.get("name", "").strip()
        issues = []
        if len(name_val) < 2:
            issues.append("Name too short")
        if not (18 <= age <= 80):
            issues.append(f"Age {age} out of reasonable range")
        valid_emp = {"Salaried", "Self-Employed", "Contract", "Unemployed"}
        if employment_type not in valid_emp:
            issues.append(f"Unknown employment type: {employment_type}")
        return json.dumps({"valid": len(issues) == 0, "issues": issues})

    if name == "classify_customer_segment":
        income = inputs.get("monthly_income", 0)
        emp = inputs.get("employment_type", "")
        age = inputs.get("age", 35)
        if income >= 150_000 and emp == "Salaried":
            segment = "PREMIUM"
        elif income >= 75_000:
            segment = "STANDARD"
        elif income >= 30_000:
            segment = "BASIC"
        else:
            segment = "MICRO"
        life_stage = "YOUNG" if age < 30 else ("MID" if age < 50 else "SENIOR")
        return json.dumps({"segment": segment, "life_stage": life_stage, "monthly_income": income})

    if name == "assess_data_completeness":
        data = inputs.get("applicant_data", {})
        mandatory = ["name", "age", "monthly_income", "existing_emi", "credit_score",
                     "employment_type", "loan_amount"]
        optional = ["loan_tenure_months", "annual_interest_rate", "estimated_new_emi"]
        missing_mandatory = [f for f in mandatory if not data.get(f) and data.get(f) != 0]
        missing_optional = [f for f in optional if f not in data]
        return json.dumps({
            "complete": len(missing_mandatory) == 0,
            "missing_mandatory": missing_mandatory,
            "missing_optional": missing_optional,
        })

    return json.dumps({"error": f"Unknown tool: {name}"})


class CustomerAgent:
    """
    Prepares and validates the customer context before the main pipeline runs.
    Classifies customer segment and checks data completeness.
    """

    def __init__(self, client: anthropic.Anthropic):
        self.client = client

    def run(self, applicant_data: dict, trace_id: str) -> dict:
        """
        Returns enriched customer context dict with segment, validation status,
        and data completeness flags.
        """
        with tracer.trace_span(trace_id, "customer_context", "CustomerAgent"):
            try:
                return self._run_agent_loop(applicant_data, trace_id)
            except Exception as e:
                logger.error(f"CustomerAgent failed, using fallback: {e}",
                             extra={"trace_id": trace_id})
                record_agent_failure("CustomerAgent", type(e).__name__)
                return self._fallback_customer_context(applicant_data)

    def _run_agent_loop(self, applicant_data: dict, trace_id: str) -> dict:
        messages = [{
            "role": "user",
            "content": (
                f"Prepare customer context for this loan applicant:\n"
                f"Name: {applicant_data.get('name')}, Age: {applicant_data.get('age')}, "
                f"Income: ₹{applicant_data.get('monthly_income'):,}, "
                f"Employment: {applicant_data.get('employment_type')}\n\n"
                f"Use the tools to: 1) validate identity, 2) classify customer segment, "
                f"3) check data completeness. Then return a JSON summary with: "
                f"valid (bool), segment, life_stage, data_complete (bool)."
            ),
        }]

        raw_results = {}
        for _ in range(4):
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=512,
                tools=CUSTOMER_TOOLS,
                messages=messages,
            )
            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            if not tool_blocks:
                return self._parse_customer_response(response, raw_results, applicant_data)

            results = []
            for block in tool_blocks:
                result = _execute_customer_tool(block.name, block.input)
                raw_results[block.name] = json.loads(result)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": results})

        return self._fallback_customer_context(applicant_data)

    def _parse_customer_response(self, response, raw_results: dict, applicant_data: dict) -> dict:
        for block in response.content:
            if hasattr(block, "text"):
                text = block.text.strip()
                start, end = text.find("{"), text.rfind("}") + 1
                if start >= 0 and end > start:
                    try:
                        data = json.loads(text[start:end])
                        return {
                            "valid": data.get("valid", True),
                            "segment": data.get("segment", "STANDARD"),
                            "life_stage": data.get("life_stage", "MID"),
                            "data_complete": data.get("data_complete", True),
                            "raw_results": raw_results,
                        }
                    except json.JSONDecodeError:
                        pass
        return self._fallback_customer_context(applicant_data)

    def _fallback_customer_context(self, applicant_data: dict) -> dict:
        income = applicant_data.get("monthly_income", 0)
        emp = applicant_data.get("employment_type", "Salaried")
        age = applicant_data.get("age", 35)
        if income >= 150_000 and emp == "Salaried":
            segment = "PREMIUM"
        elif income >= 75_000:
            segment = "STANDARD"
        elif income >= 30_000:
            segment = "BASIC"
        else:
            segment = "MICRO"
        life_stage = "YOUNG" if age < 30 else ("MID" if age < 50 else "SENIOR")
        return {
            "valid": True,
            "segment": segment,
            "life_stage": life_stage,
            "data_complete": True,
            "raw_results": {"source": "fallback"},
        }
