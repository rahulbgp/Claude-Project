# compute_loan_emi

Calculate the estimated monthly EMI for a loan using the standard EMI formula.

**Implementation:** `tools/loan_tools.py::compute_loan_emi(loan_amount, annual_rate, tenure_months)`

## Input
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `loan_amount` | float | required | Total loan amount in ₹ |
| `annual_rate` | float | 0.10 | Annual interest rate as a decimal (e.g. 0.10 = 10%) |
| `tenure_months` | int | 60 | Loan tenure in months |

## Formula
`EMI = P × r × (1+r)^n / ((1+r)^n − 1)`
where `r = annual_rate / 12` (monthly rate), `n = tenure_months`

If `annual_rate = 0`, falls back to `EMI = loan_amount / tenure_months`.

## Output (JSON)
```json
{
  "loan_amount": 500000,
  "annual_rate_percent": 10.0,
  "tenure_months": 60,
  "monthly_emi": 10623.57,
  "total_payment": 637414.2,
  "total_interest": 137414.2
}
```

**Note:** `app.py` pre-computes the EMI and passes it as `estimated_new_emi`. Agents should use that value directly and only call this tool when `estimated_new_emi` is absent.
