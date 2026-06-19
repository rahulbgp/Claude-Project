# check_bias_indicators

Check if the applicant profile contains attributes that could be proxy variables for protected characteristics. Used for fairness monitoring.

**Implementation:** `tools/loan_tools.py::check_bias_indicators(age, employment_type, verdict)`

## Input
| Parameter | Type | Description |
|-----------|------|-------------|
| `age` | int | Applicant's age |
| `employment_type` | string | Salaried \| Self-Employed \| Contract \| Unemployed |
| `verdict` | string | ELIGIBLE \| NOT_ELIGIBLE \| MANUAL_REVIEW |

## Bias checks
| Condition | Flag type | Severity |
|-----------|-----------|----------|
| Age 21–24 and NOT_ELIGIBLE | age_proxy | medium |
| Age 55–60 and NOT_ELIGIBLE | age_proxy | low |
| Contract or Self-Employed and NOT_ELIGIBLE | employment_proxy | low |

## Output (JSON)
```json
{
  "age": 23,
  "employment_type": "Salaried",
  "verdict": "NOT_ELIGIBLE",
  "bias_flags": [
    {
      "type": "age_proxy",
      "severity": "medium",
      "note": "Young applicant rejected — verify rejection is based on financial metrics only"
    }
  ],
  "bias_risk": "MEDIUM",
  "bias_check_passed": false
}
```

This tool is called by the `check_decision_bias` post-hook (via `tools/bias_checker.py::aggregate_bias_check()`). Results are recorded in the compliance log and surfaced as warnings if any flags are found.
