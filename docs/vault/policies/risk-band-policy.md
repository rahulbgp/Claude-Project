# Risk Band Policy

**Tags:** #policy #risk

## Composite Score Formula

```
risk_score = (credit_component × 0.45)
           + (dti_component    × 0.35)
           + (employment_score × 0.20)
```

## Band Thresholds

| Band | Score |
|------|-------|
| LOW | ≥ 0.75 |
| MEDIUM | ≥ 0.50 |
| HIGH | ≥ 0.25 |
| CRITICAL | < 0.25 |

## Implementation

Assessed by [[agents/risk-assessor]] using `assess_risk_band` tool.

## Related

- [[policies/credit-score-policy]] — 45% weight
- [[policies/dti-ratio-policy]] — 35% weight
- [[policies/employment-policy]] — 20% weight
- [[guides/graph-database]] — risk bands are stored as Neo4j nodes
