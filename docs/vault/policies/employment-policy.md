# Employment Stability Policy

**Tags:** #policy #eligibility #employment

## Stability Scores

| Employment Type | Score |
|----------------|-------|
| Salaried | 1.00 |
| Self-Employed | 0.75 |
| Contract | 0.60 |
| Unemployed | 0.00 → **NOT ELIGIBLE** |

A score of **0.0** (Unemployed) is a hard disqualifier.

## Implementation

Checked by [[agents/eligibility-checker]] via `check_employment_stability` tool.

## Related

- [[policies/risk-band-policy]] — employment contributes **20%** to composite risk
- [[policies/compliance-policy]] — employment type must not be used as a discriminatory proxy
