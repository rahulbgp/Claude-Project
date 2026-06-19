# EMI-to-Income Ratio Policy

**Tags:** #policy #eligibility #dti

## Rule

| Metric | Limit |
|--------|-------|
| Max DTI (Total EMI ÷ Income) | ≤ 40% |
| Preferred DTI | ≤ 30% |
| Above 40% | → **NOT ELIGIBLE** |

DTI = (Existing EMI + New Loan EMI) ÷ Monthly Income

## Implementation

Checked by [[agents/eligibility-checker]] using `check_dti_ratio` tool.

New loan EMI is computed with the standard annuity formula before this check:

```
EMI = P × r × (1+r)^n / ((1+r)^n − 1)
```

where `r = annual_rate / 12`, `n = tenure_months`.

## Related

- [[policies/risk-band-policy]] — DTI contributes **35%** to composite risk
- [[policies/credit-score-policy]] — primary gate
