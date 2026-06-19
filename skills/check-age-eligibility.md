# check_age_eligibility

Verify that the applicant's age falls within the eligible range.

**Implementation:** `tools/loan_tools.py::check_age_eligibility(age)`

## Input
| Parameter | Type | Description |
|-----------|------|-------------|
| `age` | int | Applicant's age in years |

## Logic
`passed = 21 <= age <= 60`

Age is a **hard disqualifier** — if `passed = False`, the orchestrator fast-paths to NOT_ELIGIBLE without calling other agents.

## Output (JSON)
```json
{
  "age": 35,
  "min_age": 21,
  "max_age": 60,
  "passed": true,
  "message": "Age 35 is within the eligible range of 21-60 years."
}
```
