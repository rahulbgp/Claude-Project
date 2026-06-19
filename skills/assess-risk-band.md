# assess_risk_band

Compute a composite risk band for the loan application based on credit score, EMI-to-income ratio, and employment stability.

**Implementation:** `tools/loan_tools.py::assess_risk_band(credit_score, dti_ratio, employment_score)`

## Input
| Parameter | Type | Description |
|-----------|------|-------------|
| `credit_score` | int | Applicant's CIBIL score |
| `dti_ratio` | float | Total EMI / monthly income (e.g. 0.35 for 35%) |
| `employment_score` | float | Stability score from `check_employment_stability` (0.0–1.0) |

## Composite score formula
```
credit_factor    = clamp((credit_score − 500) / 300, 0, 1)   — weight 45%
dti_factor       = max(1 − dti_ratio / 0.40, 0)              — weight 35%
employment_factor = employment_score                          — weight 20%

composite = credit_factor×0.45 + dti_factor×0.35 + employment_factor×0.20
```

## Risk bands
| Composite | Band | Meaning |
|-----------|------|---------|
| ≥ 0.75 | LOW | Strong profile |
| 0.50–0.74 | MEDIUM | Acceptable with minor concerns |
| 0.25–0.49 | HIGH | Significant concerns, manual review |
| < 0.25 | CRITICAL | Not recommended for approval |

## Output (JSON)
```json
{
  "credit_score": 720,
  "dti_ratio": 0.275,
  "employment_score": 1.0,
  "credit_factor": 0.733,
  "dti_factor": 0.313,
  "employment_factor": 1.0,
  "composite_score": 0.641,
  "risk_band": "MEDIUM",
  "description": "Medium risk - acceptable profile with minor concerns"
}
```
