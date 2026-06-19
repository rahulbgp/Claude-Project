# Credit Score Policy

**Tags:** #policy #eligibility #credit

## Rule

| Threshold | Score |
|-----------|-------|
| Minimum (hard gate) | ≥ 700 |
| Excellent | ≥ 750 |
| Below minimum | < 700 → **NOT ELIGIBLE** |

## Implementation

Checked by [[agents/eligibility-checker]] using the `check_credit_score` tool (`tools/loan_tools.py`).

The threshold is sourced from [[agents/orchestrator-agent]] → [[policies/compliance-policy]] via the `LoanRulesMCP` server at `localhost:8765`.

## Related

- [[policies/risk-band-policy]] — credit score contributes **45%** to composite risk
- [[policies/dti-ratio-policy]] — second biggest gate
- [[guides/observability]] — `applicant_credit_score_bucket` Prometheus metric
