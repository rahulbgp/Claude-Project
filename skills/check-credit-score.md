# check_credit_score

Check if an applicant's credit score meets the minimum threshold for loan eligibility.

**Implementation:** `tools/loan_tools.py::check_credit_score(credit_score)`

## Input
| Parameter | Type | Description |
|-----------|------|-------------|
| `credit_score` | int | Applicant's CIBIL score (300–900) |

## Logic
| Score | Category | Passed |
|-------|----------|--------|
| ≥ 750 | Excellent | Yes |
| 700–749 | Good | Yes |
| 650–699 | Fair | No (may warrant manual review) |
| < 650 | Poor | No |

Minimum required: **700** (`MIN_CREDIT_SCORE` from config)

## Output (JSON)
```json
{
  "credit_score": 720,
  "category": "Good",
  "passed": true,
  "minimum_required": 700,
  "message": "Credit score 720 is Good. Meets the minimum requirement of 700."
}
```
