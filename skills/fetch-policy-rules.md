# fetch_policy_rules

Fetch the current loan policy rules from the LoanRulesMCP server (port 8765).

**Implementation:** `tools/loan_tools.py::fetch_policy_rules(rule_category)`

## Input
| Parameter | Type | Allowed values |
|-----------|------|----------------|
| `rule_category` | string | credit_score \| dti \| age \| employment \| compliance |

## MCP tool mapping
| rule_category | MCP tool called |
|--------------|----------------|
| credit_score | `get_credit_score_threshold` |
| dti | `get_dti_policy` |
| age | `get_age_policy` |
| employment | `get_employment_policy` |
| compliance | `get_compliance_rules` |

MCP server: `http://localhost:8765/mcp` (LoanRulesMCP via FastMCP + uvicorn).

## Fallback
If the MCP server is unreachable, returns hard-coded defaults from `config.py`:
- `credit_score`: `{"min_credit_score": 700, "excellent_threshold": 750}`
- `dti`: `{"max_dti_ratio": 0.40, "preferred_dti": 0.30}`
- `age`: `{"min_age": 21, "max_age": 60}`
- `employment`: stability score map
- `compliance`: `{"kyc_required": true, "max_loan_income_ratio": 10}`

Always call this tool **first** in the eligibility check loop to ensure up-to-date thresholds.
