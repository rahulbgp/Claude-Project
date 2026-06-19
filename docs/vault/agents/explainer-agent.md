# ExplainerAgent

**Tags:** #agent #explanation

## Role

Generates a human-readable narrative explanation for the loan decision. Produces `reasons[]` and `recommendations[]`.

## Code

`pipeline/explainer.py` — `ExplainerAgent.explain(applicant_data, eligibility_result, risk_result)`

Returns a `LoanDecision` dataclass with:
- `verdict: Verdict` — ELIGIBLE / NOT_ELIGIBLE / MANUAL_REVIEW
- `reasons: list[str]`
- `recommendations: list[str]`
- `explanation: str`

## Related

- [[agents/risk-assessor]] — runs before this agent
- [[agents/orchestrator-agent]] — receives the final `LoanDecision`
