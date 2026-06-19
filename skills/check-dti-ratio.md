# check_dti_ratio

Check if the applicant's EMI-to-Income ratio is within the acceptable limit.
Total EMI (existing + new loan EMI) must not exceed **40%** of monthly income.

**Implementation:** `tools/loan_tools.py::check_dti_ratio(monthly_income, existing_emi, loan_emi_estimate)`

## Input
| Parameter | Type | Description |
|-----------|------|-------------|
| `monthly_income` | float | Net monthly income in ₹ |
| `existing_emi` | float | Sum of all current monthly EMI payments in ₹ |
| `loan_emi_estimate` | float | Estimated EMI for the new loan being requested in ₹ |

Use the **pre-computed `estimated_new_emi`** from applicant data as `loan_emi_estimate` — do not recompute unless missing.

## Logic
`dti_ratio = (existing_emi + loan_emi_estimate) / monthly_income`
`passed = dti_ratio <= 0.40`

## Output (JSON)
```json
{
  "monthly_income": 80000,
  "existing_emi": 10000,
  "loan_emi_estimate": 12000,
  "total_emi": 22000,
  "dti_ratio": 0.275,
  "dti_ratio_percent": 27.5,
  "max_allowed_percent": 40.0,
  "passed": true,
  "message": "EMI-to-Income ratio is 27.5%. Acceptable maximum limit of 40.0%."
}
```
