# check_employment_stability

Assess the stability of the applicant's employment type.

**Implementation:** `tools/loan_tools.py::check_employment_stability(employment_type)`

## Input
| Parameter | Type | Allowed values |
|-----------|------|----------------|
| `employment_type` | string | Salaried \| Self-Employed \| Contract \| Unemployed |

## Stability scores
| Employment Type | Score | Level |
|----------------|-------|-------|
| Salaried | 1.0 | High |
| Self-Employed | 0.75 | Medium-High |
| Contract | 0.60 | Medium |
| Unemployed | 0.0 | None — not eligible |

`passed = score > 0.0`

Employment is a **hard disqualifier** — Unemployed applicants are immediately NOT_ELIGIBLE.

## Output (JSON)
```json
{
  "employment_type": "Salaried",
  "stability_score": 1.0,
  "stability_level": "High - Salaried employment provides stable income",
  "passed": true,
  "message": "Employment type 'Salaried' has a stability score of 1.0. Eligible to proceed."
}
```
