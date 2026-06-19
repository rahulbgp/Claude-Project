# Governance Report

## Loan Eligibility AI Agent

**Date:** 2026-06-19  
**Regulatory Framework:** RBI Fair Lending 2023  

---

## 1. Governance Architecture

The governance framework has four pillars:

| Pillar | Component | Description |
|--------|-----------|-------------|
| Audit Trail | `governance/audit_trail.py` | Immutable SQLite log of every decision |
| Compliance Logging | `governance/compliance_logger.py` | Structured JSONL with regulatory fields |
| Bias Detection | `tools/bias_checker.py` | Real-time proxy-variable analysis |
| Bias Reporting | `governance/bias_report.py` | Aggregate disparate impact analysis |

---

## 2. Decision Audit Trail

Every loan decision is recorded to `audit.db` with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `trace_id` | TEXT UNIQUE | UUID for end-to-end request tracing |
| `timestamp` | TEXT | UTC ISO-8601 timestamp |
| `applicant_hash` | TEXT | SHA-256 hash of applicant name (PII-masked) |
| `credit_score` | INTEGER | Credit score at time of decision |
| `monthly_income` | REAL | Monthly income in rupees |
| `existing_emi` | REAL | Existing monthly EMI |
| `loan_amount` | REAL | Loan amount requested |
| `age` | INTEGER | Applicant age |
| `employment_type` | TEXT | Employment category |
| `verdict` | TEXT | ELIGIBLE / NOT_ELIGIBLE / MANUAL_REVIEW |
| `dti_ratio` | REAL | EMI-to-Income ratio at decision time |
| `risk_band` | TEXT | LOW / MEDIUM / HIGH / CRITICAL |
| `reasons` | TEXT (JSON) | Array of decision reasons |
| `model_used` | TEXT | Claude model version |
| `tool_calls_count` | INTEGER | Number of AI tool calls made |
| `processing_time_ms` | INTEGER | Processing duration in milliseconds |
| `bias_flags` | TEXT (JSON) | Array of bias flags detected |
| `compliance_status` | TEXT | COMPLIANT / NEEDS_REVIEW |

**Immutability:** The `UNIQUE` constraint on `trace_id` combined with `INSERT OR IGNORE` prevents any record from being modified after writing. Retention period: 7 years per RBI requirements.

---

## 3. Compliance Logging

Each decision generates a record in `logs/compliance.jsonl`:

```json
{
  "timestamp": "2026-06-19T10:30:00Z",
  "trace_id": "uuid-...",
  "regulatory_framework": "RBI_FAIR_LENDING_2023",
  "applicant_hash": "APPLICANT_ABCDEF123456",
  "decision": "ELIGIBLE",
  "reasons": ["Credit score 750 meets minimum requirement"],
  "non_discriminatory_reasons": ["Credit score 750 meets minimum requirement of 700"],
  "financial_metrics": {"emi_to_income_ratio": 0.25},
  "protected_attributes_used": false,
  "employment_type_category": "Salaried",
  "age_group": "35-44",
  "bias_check_passed": true,
  "bias_flags": [],
  "model_version": "claude-opus-4-5",
  "human_review_flag": false,
  "compliance_status": "COMPLIANT"
}
```

**Key compliance fields:**
- `protected_attributes_used: false` — confirms no protected attributes in decision logic
- `non_discriminatory_reasons` — only financial metric-based reasons
- `regulatory_framework` — identifies governing regulation

---

## 4. Bias Detection

### Real-time Bias Checks (per decision)

Two checks run on every decision via `tools/bias_checker.py`:

1. **Age Proxy Check:** Flags rejections of applicants aged 21–24 or 55–60 without clear financial justification
2. **Employment Proxy Check:** Flags `Contract` or `Self-Employed` rejections without financial basis

Each flag carries a severity level (LOW/MEDIUM/HIGH) and is stored in the audit record.

### Aggregate Bias Analysis

`governance/bias_report.py` analyzes the full audit trail to detect disparate impact:

**Disparate Impact Rule:** If any demographic group's approval rate is less than 80% of the highest-rate group's approval rate, it is flagged.

Example output:
```
Employment Type Approval Rates:
  Salaried:      85% (⸻ baseline)
  Self-Employed: 62% (⸻ within 80% of baseline: OK)
  Contract:      55% (⚠ below 80% of 85% = 68%: FLAGGED)
  Unemployed:    0%  (⸻ hard rule, not discriminatory)
```

---

## 5. PII Protection

| Data | Handling |
|------|---------|
| Applicant Name | Stored only in Streamlit session state; SHA-256 hashed for all logs/DB |
| Age | Stored in audit DB as integer; categorized into 5-year groups for compliance logs |
| Income/EMI | Stored in audit DB; used only for financial ratio calculations |
| Credit Score | Stored in audit DB; used only for threshold comparison |

---

## 6. Model Governance

- **Model Version Tracking:** Every audit record includes the `model_used` field
- **Fallback Documentation:** When the fallback (rule-based) path activates, `model_used` is set to `{model_name} (fallback)` so it's distinguishable in the audit
- **Human Override:** All `MANUAL_REVIEW` decisions are written to `logs/manual_review_queue.jsonl` for human loan officers
- **Decision Explainability:** Every decision includes a list of specific, numbered reasons in plain English

---

## 7. Compliance Checklist

| Requirement | Status | Notes |
|-------------|--------|-------|
| Decision audit trail | ✅ | SQLite, 7-year retention |
| PII masking in logs | ✅ | SHA-256 hash of name |
| Non-discriminatory decisions | ✅ | Only financial metrics used |
| Explainable decisions | ✅ | Reasons list + AI explanation |
| Human review escalation | ✅ | MANUAL_REVIEW queue |
| Bias monitoring | ✅ | Real-time + aggregate |
| Regulatory framework tagging | ✅ | RBI_FAIR_LENDING_2023 |
| Model version tracking | ✅ | Stored in every audit record |
| Input validation | ✅ | Pre-hooks validate all fields |
| Rate limiting | ✅ | 10 req/min/session |
