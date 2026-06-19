"""
KnowledgeAgent: Retrieves relevant policy knowledge before eligibility evaluation.
Uses the RAG engine (TF-IDF over policy documents) and MCP policy server to
build a grounded policy context for the pipeline.
"""

import json
import logging

import anthropic

from config import MODEL, MAX_TOKENS, MCP_LOAN_RULES_URL
from rag.retriever import KnowledgeRetriever
from observability.tracer import tracer
from observability.metrics import record_agent_failure, record_mcp_call

logger = logging.getLogger(__name__)

_retriever = KnowledgeRetriever()

KNOWLEDGE_TOOLS = [
    {
        "name": "retrieve_policy_context",
        "description": "Retrieve relevant loan policy documents from the RAG knowledge base based on applicant profile.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query describing the applicant's profile"},
                "top_k": {"type": "integer", "description": "Number of documents to retrieve", "default": 3},
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_regulatory_rules",
        "description": "Fetch the current regulatory compliance rules from the policy server.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["credit_score", "dti", "age", "employment", "compliance"],
                },
            },
            "required": ["category"],
        },
    },
    {
        "name": "summarize_applicable_rules",
        "description": "Summarize which policy rules are most relevant to this applicant.",
        "input_schema": {
            "type": "object",
            "properties": {
                "credit_score": {"type": "integer"},
                "employment_type": {"type": "string"},
                "age": {"type": "integer"},
                "dti_ratio_estimate": {"type": "number"},
            },
            "required": ["credit_score", "employment_type", "age"],
        },
    },
]


def _execute_knowledge_tool(name: str, inputs: dict) -> str:
    if name == "retrieve_policy_context":
        query = inputs.get("query", "loan eligibility")
        top_k = inputs.get("top_k", 3)
        docs = _retriever.retrieve(query, top_k=top_k)
        return json.dumps({"documents": docs, "count": len(docs)})

    if name == "fetch_regulatory_rules":
        import requests
        category = inputs.get("category", "compliance")
        category_to_tool = {
            "credit_score": "get_credit_score_threshold",
            "dti": "get_dti_policy",
            "age": "get_age_policy",
            "employment": "get_employment_policy",
            "compliance": "get_compliance_rules",
        }
        tool_name = category_to_tool.get(category, "get_compliance_rules")
        try:
            response = requests.post(
                MCP_LOAN_RULES_URL,
                json={"method": "tools/call", "params": {"name": tool_name, "arguments": {}}},
                timeout=3,
            )
            record_mcp_call("loan-rules", tool_name, True)
            return response.text
        except Exception as e:
            record_mcp_call("loan-rules", tool_name, False)
            defaults = {
                "credit_score": {"min_credit_score": 700, "excellent_threshold": 750},
                "dti": {"max_dti_ratio": 0.40},
                "age": {"min_age": 21, "max_age": 60},
                "employment": {"Salaried": 1.0, "Self-Employed": 0.75, "Contract": 0.60, "Unemployed": 0.0},
                "compliance": {"framework": "RBI_FAIR_LENDING_2023", "kyc_required": True},
            }
            return json.dumps(defaults.get(category, {}))

    if name == "summarize_applicable_rules":
        credit_score = inputs.get("credit_score", 700)
        employment_type = inputs.get("employment_type", "Salaried")
        age = inputs.get("age", 35)
        dti = inputs.get("dti_ratio_estimate", 0.30)
        applicable = []
        if credit_score < 700:
            applicable.append("Credit score below minimum — check credit_score policy")
        if dti > 0.35:
            applicable.append("High DTI — check dti policy carefully")
        if age < 25 or age > 55:
            applicable.append("Edge age — check age policy")
        if employment_type in ("Contract", "Self-Employed"):
            applicable.append("Non-standard employment — check employment stability policy")
        applicable.append("Compliance: RBI Fair Lending 2023 applies")
        return json.dumps({"applicable_rules": applicable, "count": len(applicable)})

    return json.dumps({"error": f"Unknown tool: {name}"})


class KnowledgeAgent:
    """
    Retrieves and synthesizes policy knowledge relevant to a specific applicant.
    Outputs a policy_context string used by downstream agents.
    """

    def __init__(self, client: anthropic.Anthropic):
        self.client = client

    def run(self, applicant_data: dict, trace_id: str) -> str:
        """Returns a policy context string for the applicant."""
        with tracer.trace_span(trace_id, "knowledge_retrieval", "KnowledgeAgent"):
            try:
                return self._run_agent_loop(applicant_data, trace_id)
            except Exception as e:
                logger.error(f"KnowledgeAgent failed, using fallback: {e}",
                             extra={"trace_id": trace_id})
                record_agent_failure("KnowledgeAgent", type(e).__name__)
                return self._fallback_policy_context(applicant_data)

    def _run_agent_loop(self, applicant_data: dict, trace_id: str) -> str:
        credit_score = applicant_data.get("credit_score", 700)
        employment_type = applicant_data.get("employment_type", "Salaried")
        age = applicant_data.get("age", 35)

        messages = [{
            "role": "user",
            "content": (
                f"Retrieve relevant policy knowledge for this loan applicant:\n"
                f"Credit Score: {credit_score}, Employment: {employment_type}, Age: {age}\n\n"
                f"1. Retrieve policy context from the RAG knowledge base\n"
                f"2. Fetch regulatory rules for credit_score and compliance categories\n"
                f"3. Summarize which rules are most applicable\n"
                f"Return a concise policy summary (2-3 sentences) the eligibility agent should know."
            ),
        }]

        collected_context = []
        for _ in range(4):
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=600,
                tools=KNOWLEDGE_TOOLS,
                messages=messages,
            )
            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            if not tool_blocks:
                for block in response.content:
                    if hasattr(block, "text") and block.text.strip():
                        return block.text.strip()
                break

            results = []
            for block in tool_blocks:
                result = _execute_knowledge_tool(block.name, block.input)
                collected_context.append(f"[{block.name}]: {result[:200]}")
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": results})

        return self._fallback_policy_context(applicant_data)

    def _fallback_policy_context(self, applicant_data: dict) -> str:
        return _retriever.get_context_for_applicant(applicant_data)
