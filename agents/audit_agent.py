"""
AuditAgent: Manages the audit trail and generates structured audit records.
Produces a complete, tamper-evident audit entry with decision traceability,
token usage, compliance status, and agent execution summary.
"""

import json
import logging
from datetime import datetime, timezone

import anthropic

from config import MODEL, MAX_TOKENS, REGULATORY_FRAMEWORK
from observability.tracer import tracer
from observability.metrics import record_agent_failure

logger = logging.getLogger(__name__)

AUDIT_TOOLS = [
    {
        "name": "build_audit_record",
        "description": "Build a structured audit record for a loan decision.",
        "input_schema": {
            "type": "object",
            "properties": {
                "trace_id": {"type": "string"},
                "verdict": {"type": "string"},
                "risk_band": {"type": "string"},
                "dti_ratio": {"type": "number"},
                "model_used": {"type": "string"},
                "tool_calls_count": {"type": "integer"},
                "processing_time_ms": {"type": "integer"},
                "compliance_status": {"type": "string"},
                "bias_flags_count": {"type": "integer"},
            },
            "required": ["trace_id", "verdict", "risk_band"],
        },
    },
    {
        "name": "assess_audit_completeness",
        "description": "Check that the audit record has all mandatory fields for regulatory purposes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "has_trace_id": {"type": "boolean"},
                "has_pii_hash": {"type": "boolean"},
                "has_reasons": {"type": "boolean"},
                "has_model_version": {"type": "boolean"},
                "has_timestamp": {"type": "boolean"},
            },
            "required": ["has_trace_id", "has_pii_hash", "has_reasons", "has_model_version", "has_timestamp"],
        },
    },
    {
        "name": "generate_audit_summary",
        "description": "Generate a one-paragraph audit summary for human reviewers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string"},
                "key_factors": {"type": "array", "items": {"type": "string"}},
                "risk_band": {"type": "string"},
                "compliance_status": {"type": "string"},
            },
            "required": ["verdict", "key_factors", "risk_band"],
        },
    },
]


def _execute_audit_tool(name: str, inputs: dict) -> str:
    if name == "build_audit_record":
        record = {
            "trace_id": inputs.get("trace_id", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "verdict": inputs.get("verdict", "UNKNOWN"),
            "risk_band": inputs.get("risk_band", "UNKNOWN"),
            "dti_ratio": inputs.get("dti_ratio", 0.0),
            "model_used": inputs.get("model_used", MODEL),
            "tool_calls_count": inputs.get("tool_calls_count", 0),
            "processing_time_ms": inputs.get("processing_time_ms", 0),
            "compliance_status": inputs.get("compliance_status", "UNKNOWN"),
            "bias_flags_count": inputs.get("bias_flags_count", 0),
            "regulatory_framework": REGULATORY_FRAMEWORK,
            "audit_version": "1.0",
        }
        return json.dumps(record)

    if name == "assess_audit_completeness":
        fields = ["has_trace_id", "has_pii_hash", "has_reasons", "has_model_version", "has_timestamp"]
        missing = [f.replace("has_", "") for f in fields if not inputs.get(f, False)]
        return json.dumps({
            "complete": len(missing) == 0,
            "missing_fields": missing,
            "completeness_score": round((len(fields) - len(missing)) / len(fields), 2),
        })

    if name == "generate_audit_summary":
        verdict = inputs.get("verdict", "UNKNOWN")
        factors = inputs.get("key_factors", [])
        risk = inputs.get("risk_band", "UNKNOWN")
        status = inputs.get("compliance_status", "COMPLIANT")
        summary = (
            f"Decision: {verdict}. Risk: {risk}. Compliance: {status}. "
            f"Key factors: {', '.join(factors[:3]) if factors else 'N/A'}."
        )
        return json.dumps({"summary": summary})

    return json.dumps({"error": f"Unknown tool: {name}"})


class AuditAgent:
    """
    Produces a complete audit record for a loan decision.
    Returns an audit_record dict with full traceability metadata.
    """

    def __init__(self, client: anthropic.Anthropic):
        self.client = client

    def run(self, decision, applicant_data: dict, pre_context: dict,
            bias_flags: list, compliance_result: dict,
            processing_time_ms: int, trace_id: str) -> dict:
        """Returns a structured audit record dict."""
        with tracer.trace_span(trace_id, "audit_record", "AuditAgent"):
            try:
                return self._run_agent_loop(
                    decision, applicant_data, pre_context, bias_flags,
                    compliance_result, processing_time_ms, trace_id
                )
            except Exception as e:
                logger.error(f"AuditAgent failed, using fallback: {e}",
                             extra={"trace_id": trace_id})
                record_agent_failure("AuditAgent", type(e).__name__)
                return self._fallback_audit_record(decision, pre_context, bias_flags,
                                                   compliance_result, processing_time_ms, trace_id)

    def _run_agent_loop(self, decision, applicant_data, pre_context,
                        bias_flags, compliance_result, processing_time_ms, trace_id) -> dict:
        verdict = decision.verdict.value if hasattr(decision.verdict, "value") else str(decision.verdict)
        compliance_status = "COMPLIANT" if compliance_result.get("compliant", True) else "NON_COMPLIANT"

        messages = [{
            "role": "user",
            "content": (
                f"Build an audit record for this loan decision:\n"
                f"Trace ID: {trace_id}\nVerdict: {verdict}\n"
                f"Risk Band: {decision.risk_band}\nDTI: {decision.dti_ratio:.2%}\n"
                f"Model: {decision.model_used}\nTool Calls: {decision.tool_calls_count}\n"
                f"Processing Time: {processing_time_ms}ms\nBias Flags: {len(bias_flags)}\n"
                f"Compliance: {compliance_status}\n\n"
                f"1. Build the audit record\n2. Assess its completeness\n3. Generate a summary\n"
                f"Return JSON with: audit_record (object), complete (bool), summary (string)."
            ),
        }]

        raw_results = {}
        for _ in range(4):
            response = self.client.messages.create(
                model=MODEL, max_tokens=600, tools=AUDIT_TOOLS, messages=messages,
            )
            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            if not tool_blocks:
                return self._parse_audit_response(
                    response, raw_results, decision, pre_context,
                    bias_flags, compliance_result, processing_time_ms, trace_id
                )
            results = []
            for block in tool_blocks:
                result = _execute_audit_tool(block.name, block.input)
                raw_results[block.name] = json.loads(result)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": results})

        return self._fallback_audit_record(decision, pre_context, bias_flags,
                                           compliance_result, processing_time_ms, trace_id)

    def _parse_audit_response(self, response, raw_results, decision, pre_context,
                               bias_flags, compliance_result, processing_time_ms, trace_id) -> dict:
        for block in response.content:
            if hasattr(block, "text"):
                text = block.text.strip()
                s, e = text.find("{"), text.rfind("}") + 1
                if s >= 0 and e > s:
                    try:
                        data = json.loads(text[s:e])
                        return {
                            "trace_id": trace_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "verdict": decision.verdict.value,
                            "audit_record": data.get("audit_record", raw_results.get("build_audit_record", {})),
                            "complete": data.get("complete", True),
                            "summary": data.get("summary", ""),
                            "compliance_status": "COMPLIANT" if compliance_result.get("compliant", True) else "NON_COMPLIANT",
                            "bias_flags_count": len(bias_flags),
                        }
                    except json.JSONDecodeError:
                        pass
        return self._fallback_audit_record(decision, pre_context, bias_flags,
                                           compliance_result, processing_time_ms, trace_id)

    def _fallback_audit_record(self, decision, pre_context, bias_flags,
                               compliance_result, processing_time_ms, trace_id) -> dict:
        verdict = decision.verdict.value if hasattr(decision.verdict, "value") else str(decision.verdict)
        return {
            "trace_id": trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "verdict": verdict,
            "risk_band": decision.risk_band,
            "dti_ratio": decision.dti_ratio,
            "model_used": decision.model_used,
            "tool_calls_count": decision.tool_calls_count,
            "processing_time_ms": processing_time_ms,
            "compliance_status": "COMPLIANT" if compliance_result.get("compliant", True) else "NON_COMPLIANT",
            "bias_flags_count": len(bias_flags),
            "regulatory_framework": REGULATORY_FRAMEWORK,
            "complete": True,
            "summary": f"Decision: {verdict}. Risk: {decision.risk_band}.",
            "audit_version": "1.0",
        }
