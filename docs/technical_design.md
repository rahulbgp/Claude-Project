# Technical Design Document

## Loan Eligibility AI Agent

**Version:** 1.0  
**Date:** 2026-06-19  
**Framework:** Claude SDK (Anthropic), Python 3.14, Streamlit  

---

## 1. Problem Statement

Banks process thousands of loan applications daily. Manual evaluation is slow, inconsistent, and prone to bias. An AI agent can apply consistent, auditable rules instantly while providing human-readable explanations.

**Goal:** Build a multi-agent loan eligibility system that:
- Accepts 7 applicant fields via a Streamlit UI
- Applies rules-based + AI-powered eligibility checks
- Returns one of three verdicts (Eligible / Not Eligible / Needs Manual Review)
- Explains the reasoning in plain English
- Maintains a complete governance and audit trail

---

## 2. System Components

### 2.1 Streamlit UI (`app.py`)
- Single-page application with a 3-column form layout
- Color-coded verdict badges (green/red/yellow)
- Displays EMI-to-income ratio, risk band, credit score as metrics
- Shows the last 10 audit decisions in a scrollable table
- Links to Prometheus metrics endpoint

### 2.2 Multi-Agent Pipeline

| Agent | Role | API Usage |
|-------|------|-----------|
| OrchestratorAgent | Plans and coordinates; retries; self-heals | No direct API (orchestrates others) |
| EligibilityCheckerAgent | Checks all 4 eligibility criteria | Claude with tools (5-8 tool calls) |
| RiskAssessorAgent | Computes composite risk band | Claude with tools (2-3 tool calls) |
| ExplainerAgent | Produces verdict + explanation | Claude generate (no tools) |

### 2.3 Tools (Skills)

8 tool functions in `tools/loan_tools.py`:

| Tool | Purpose |
|------|---------|
| `check_credit_score` | Threshold check with category classification |
| `check_dti_ratio` | EMI-to-Income ratio with 40% limit |
| `check_age_eligibility` | Age range 21–60 |
| `check_employment_stability` | Stability score by employment type |
| `compute_loan_emi` | Standard EMI formula: P·r·(1+r)^n / ((1+r)^n - 1) |
| `assess_risk_band` | Composite score: credit 45% + EMI-to-Income ratio 35% + employment 20% |
| `fetch_policy_rules` | HTTP call to LoanRulesMCP :8765 |
| `check_bias_indicators` | Proxy-variable bias detection |

### 2.4 MCP Servers

Two FastMCP servers started as daemon threads on app startup:

**LoanRulesMCP (port 8765)**
- `get_credit_score_threshold` — returns `{min: 700, excellent: 750}`
- `get_emi_to_income_policy` — returns `{max: 0.40, preferred: 0.30}`
- `get_age_policy` — returns `{min: 21, max: 60}`
- `get_employment_policy` — returns stability scores per type
- `get_loan_products` — returns product catalog
- `get_compliance_rules` — returns regulatory requirements

**AuditMCP (port 8766)**
- `log_decision` — write a decision to the audit trail
- `get_decision_history` — read recent decisions

### 2.5 Hooks Layer

**Pre-hooks** (chain-of-responsibility, each transforms context dict):
1. `validate_input` — type checks, range validation
2. `sanitize_input` — normalize strings/numbers
3. `mask_pii` — SHA-256 hash of name for audit logs
4. `enrich_input` — add derived fields
5. `check_rate_limit` — 10 req/min/session in-memory

**Post-hooks:**
1. `record_audit_trail` — SQLite append
2. `check_decision_bias` — run bias analysis first to get flags
3. `emit_compliance_log` — JSONL with bias flags included
4. `update_prometheus_metrics` — Prometheus counters/histograms
5. `notify_manual_review` — write to review queue if MANUAL_REVIEW

### 2.6 Governance

- **Audit Trail:** SQLite database (`audit.db`) with 18-column `audit_log` table. `UNIQUE` constraint on `trace_id` makes it append-only (no accidental overwrites).
- **Compliance Log:** JSONL file (`logs/compliance.jsonl`) with regulatory framework label `RBI_FAIR_LENDING_2023`.
- **Bias Report:** `governance/bias_report.py` computes approval rates by age group and employment type and flags disparate impact (< 80% of max approval rate).

### 2.7 Observability

- **Prometheus** (port 9090): 6 metrics covering request counts, processing time, active requests, agent failures, EMI-to-Income ratio distribution, and MCP calls.
- **Structured Logging:** `python-json-logger` writes JSONL to `logs/loan_agent.jsonl`. Every log line carries `trace_id`.
- **Tracer:** `observability/tracer.py` generates UUIDs and provides `trace_span` context managers for timing each agent.

---

## 3. Key Design Decisions

### 3.1 Deterministic Verdict, AI Explanation
The final verdict (ELIGIBLE / NOT_ELIGIBLE / MANUAL_REVIEW) is determined by hard rules in `ExplainerAgent._determine_verdict()` — no AI involvement in the outcome. Claude is only used to generate the human-readable explanation text. This ensures the verdict is always reproducible and auditable.

### 3.2 Autonomous Planning
`OrchestratorAgent._create_plan()` generates a dynamic execution plan based on the applicant's profile. For obvious hard rejections (unemployed, out-of-age-range), the plan short-circuits to skip expensive API calls. This is logged as a structured JSON plan.

### 3.3 Self-Healing
Every agent call is wrapped in a retry loop with exponential backoff (`RETRY_BASE_DELAY * 2^attempt` seconds). After `MAX_RETRIES=2` failures, a pure-Python fallback activates that produces a decision without any API calls.

### 3.4 Multi-MCP Integration
Two separate MCP servers serve different concerns: one for policy rules (read-heavy, cacheable) and one for audit operations (write-heavy, stateful). This separation of concerns enables independent scaling.

---

## 4. Eligibility Decision Logic

```
Verdict Rules (evaluated in order):
1. age NOT in [21,60]  → NOT_ELIGIBLE (hard)
2. employment = Unemployed → NOT_ELIGIBLE (hard)
3. risk_band = CRITICAL → NOT_ELIGIBLE
4. credit_ok AND dti_ok AND risk in (LOW, MEDIUM) → ELIGIBLE
5. risk_band = HIGH → MANUAL_REVIEW
6. credit_ok OR emi_ratio_ok → MANUAL_REVIEW
7. neither credit nor EMI-to-Income ratio passes → NOT_ELIGIBLE
```

**EMI-to-Income Ratio Calculation:**
```
Total EMI = existing_emi + compute_loan_emi(loan_amount, annual_rate, tenure_months)
EMI-to-Income Ratio = Total EMI / monthly_income
Pass if EMI-to-Income Ratio ≤ 0.40
```

**Risk Band Calculation:**
```
credit_factor = clamp((credit_score - 500) / 300, 0, 1)
emi_factor = max(1 - emi_to_income_ratio / 0.40, 0)
employment_factor = stability_score

composite = credit_factor * 0.45 + emi_factor * 0.35 + employment_factor * 0.20

composite ≥ 0.75 → LOW
composite ≥ 0.50 → MEDIUM
composite ≥ 0.25 → HIGH
else → CRITICAL
```

---

## 5. Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| UI Framework | Streamlit | ≥1.45 |
| AI SDK | Anthropic Python SDK | 0.97.0 |
| AI Model | claude-opus-4-5 | latest |
| MCP Protocol | mcp[cli] | ≥1.9.0 |
| REST Framework | FastAPI | ≥0.115 |
| ASGI Server | Uvicorn | ≥0.34 |
| Monitoring | Prometheus Client | 0.25.0 |
| Structured Logging | python-json-logger | 4.1.0 |
| Data Validation | Pydantic | 2.13.3 |
| Database | SQLite3 (stdlib) | — |
| Testing | pytest + pytest-mock | ≥8.0 |
| Load Testing | Locust | ≥2.34 |
| Runtime | Python | 3.14 |

---

## 6. Security Considerations

- **PII Protection:** Applicant names are SHA-256 hashed before being written to any log or database. The original name only exists in the Streamlit session state.
- **Input Validation:** All 7 fields are validated for type, range, and allowed values before reaching the agent pipeline.
- **Rate Limiting:** 10 requests per minute per session (in-memory).
- **API Key:** `ANTHROPIC_API_KEY` loaded from `.env` file, never hardcoded.
- **Immutable Audit:** `UNIQUE` constraint on `trace_id` prevents audit record modification.
