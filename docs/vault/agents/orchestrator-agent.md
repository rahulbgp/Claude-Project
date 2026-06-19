# OrchestratorAgent

**Tags:** #agent #orchestration

## Role

Top-level coordinator. Receives raw applicant data, runs the 3-agent pipeline, and returns a `LoanDecision`.

## Pipeline

```
applicant_data
    │
    ▼
[[agents/eligibility-checker]]  ──▶  eligibility flags
    │
    ▼
[[agents/risk-assessor]]         ──▶  risk band + score
    │
    ▼
[[agents/explainer-agent]]       ──▶  narrative explanation
    │
    ▼
LoanDecision (verdict, reasons, recommendations, explanation)
```

## Code

`pipeline/orchestrator.py` — `OrchestratorAgent.run(applicant_data, trace_id)`

## MCP Connections

Uses tools from `LoanRulesMCP` (port 8765) and `AuditMCP` (port 8766) via `.mcp.json`.

## Related

- [[policies/compliance-policy]] — post-hooks run after orchestrator returns
- [[guides/architecture]]
