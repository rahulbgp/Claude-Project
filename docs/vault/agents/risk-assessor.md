# RiskAssessorAgent

**Tags:** #agent #risk

## Role

Computes a composite risk score (0.0–1.0) and assigns a risk band (LOW / MEDIUM / HIGH / CRITICAL).

## Composite Formula

See [[policies/risk-band-policy]] for the full formula.

## Code

`pipeline/risk_assessor.py` — `RiskAssessorAgent.assess(applicant_data, eligibility_result)`

## Related

- [[agents/eligibility-checker]] — runs before this agent
- [[agents/explainer-agent]] — consumes risk band result
- [[guides/graph-database]] — risk decisions stored as Neo4j `Decision` nodes
