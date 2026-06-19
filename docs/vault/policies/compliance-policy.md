# RBI Fair Lending Compliance Policy

**Tags:** #policy #compliance #rbi

## Requirements

1. Every decision must be logged with a unique **trace ID**
2. No discrimination by gender, religion, or caste
3. Reasons must be **financial-metric-based** only
4. Bias check runs for **every** decision
5. MANUAL_REVIEW cases are queued for human reviewer

## Framework

**RBI Fair Lending Guidelines 2023** — `REGULATORY_FRAMEWORK = "RBI_FAIR_LENDING_2023"` in `config.py`.

## Implementation

- Audit trail: `governance/audit_trail.py` → `audit.db` (SQLite)
- Compliance log: `governance/compliance_logger.py` → `logs/compliance.jsonl`
- Bias monitor: `tools/bias_checker.py` + `governance/bias_report.py`

Orchestrated by [[agents/orchestrator-agent]] via `run_post_hooks()` in `middleware/post_hooks.py`.

## Related

- [[agents/orchestrator-agent]]
- [[policies/age-policy]]
- [[guides/observability]] — compliance metrics in Grafana
