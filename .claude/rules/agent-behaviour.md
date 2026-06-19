# Agent Behaviour Rules

## Orchestrator
- Always generate an execution plan before delegating to sub-agents
- Short-circuit obvious hard rejections (age out of range, unemployed) before API calls
- Retry failed agents with exponential backoff (max 2 retries, base delay 1s)
- Activate rule-based fallback if all retries are exhausted

## EligibilityCheckerAgent
- Must call ALL five tools: `fetch_policy_rules`, `check_age_eligibility`,
  `check_employment_stability`, `check_credit_score`, `check_dti_ratio`
- Use the pre-computed EMI from app.py — do not recompute unless `estimated_new_emi` is absent
- Max 8 tool-use rounds per request

## RiskAssessorAgent
- Must call `assess_risk_band` with credit score, DTI ratio, and employment score
- Risk band is deterministic — do not override with Claude's judgment

## ExplainerAgent
- Verdict is determined by hard rules, not by Claude
- Claude is used only for the human-readable explanation (max 300 tokens)
- Fallback explanations must be empathetic and actionable

## General
- All agent `run()` methods accept `(data: dict, trace_id: str)` signature
- Every agent span must be wrapped in `tracer.trace_span()`
- No agent should make direct DB writes — route through `governance/audit_trail.py`
