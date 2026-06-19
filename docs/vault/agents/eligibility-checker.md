# EligibilityCheckerAgent

**Tags:** #agent #eligibility

## Role

Evaluates 4 hard eligibility rules. Returns pass/fail per rule and an aggregate flag.

## Rules Checked

| Tool | Policy |
|------|--------|
| `check_credit_score` | [[policies/credit-score-policy]] |
| `check_dti_ratio` | [[policies/dti-ratio-policy]] |
| `check_age_eligibility` | [[policies/age-policy]] |
| `check_employment_stability` | [[policies/employment-policy]] |

## Code

`pipeline/eligibility_checker.py` — `EligibilityCheckerAgent.check(applicant_data)`

## Related

- [[agents/orchestrator-agent]] — calls this agent first
- [[agents/risk-assessor]] — runs after eligibility check
