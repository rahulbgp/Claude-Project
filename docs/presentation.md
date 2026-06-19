# Loan Eligibility AI Agent
## Presentation Deck

---

## Slide 1: Business Problem

### The Challenge
- Banks process **10,000+ loan applications daily**
- Manual evaluation takes **2-3 business days** per application
- Human reviewers are **inconsistent** — same application, different loan officers, different decisions
- Growing regulatory pressure for **explainable, bias-free lending**

### The Impact
- Customer frustration from long wait times
- Compliance risk from undocumented decisions
- Revenue loss from delayed approvals
- Potential fair-lending violations

---

## Slide 2: Solution Overview

### Loan Eligibility AI Agent

An intelligent multi-agent system that:

✅ **Instant evaluation** — decisions in under 10 seconds  
✅ **Consistent rules** — same criteria applied every time  
✅ **Explainable decisions** — plain-English reasons for every outcome  
✅ **Full audit trail** — immutable record of every decision  
✅ **Bias monitoring** — real-time fairness analysis  

### Three Outcomes
| Verdict | Meaning |
|---------|---------|
| 🟢 **ELIGIBLE** | Meets all criteria — proceed with loan |
| 🔴 **NOT ELIGIBLE** | Hard disqualifier present — decline |
| 🟡 **MANUAL REVIEW** | Borderline case — escalate to loan officer |

---

## Slide 3: Agent Architecture

### Multi-Agent Pipeline

```
User Input
    ↓
[Pre-Hooks] — validate, sanitize, mask PII, enrich
    ↓
[OrchestratorAgent] — autonomous planner
    ├── [EligibilityCheckerAgent] — 8 tool calls
    │       check_credit, check_dti, check_age, check_employment
    ├── [RiskAssessorAgent] — 3 tool calls
    │       compute_emi, assess_risk_band
    └── [ExplainerAgent] — deterministic verdict + AI explanation
    ↓
[Post-Hooks] — audit, compliance, metrics, bias check
    ↓
Results Display
```

### Key Design Principles
- **Deterministic verdict** — rules, not AI, decide the outcome
- **AI for explainability** — Claude generates the human-readable explanation
- **Self-healing** — falls back to pure rules if AI unavailable

---

## Slide 4: Skills, Subagents & Hooks

### 8 Skills (Tools)

| Skill | Purpose |
|-------|---------|
| `check_credit_score` | Threshold check + category (Excellent/Good/Fair/Poor) |
| `check_dti_ratio` | EMI-to-Income 40% rule |
| `check_age_eligibility` | Age range 21–60 |
| `check_employment_stability` | Stability score by type |
| `compute_loan_emi` | Standard EMI formula |
| `assess_risk_band` | Composite LOW/MEDIUM/HIGH/CRITICAL |
| `fetch_policy_rules` | Live rules from MCP server |
| `check_bias_indicators` | Proxy-variable detection |

### Hook Chain
```
Pre:  validate → sanitize → mask PII → enrich → rate-limit
Post: audit trail → bias check → compliance log → metrics → review queue
```

---

## Slide 5: MCP & Plugin Integration

### Multi-MCP Architecture

**LoanRulesMCP (port 8765)**  
FastMCP server exposing 6 policy tools:
- `get_credit_score_threshold` → current minimum credit score
- `get_emi_to_income_policy` → current EMI-to-Income ratio limit
- `get_age_policy` → eligible age range
- `get_employment_policy` → stability scores
- `get_loan_products` → available loan types
- `get_compliance_rules` → regulatory requirements

**AuditMCP (port 8766)**  
FastMCP server for audit operations:
- `log_decision` → write to audit trail via MCP
- `get_decision_history` → read recent decisions

### Benefits
- Policy rules can be **updated without code changes** (`policies.yaml`)
- MCP servers are **independently scalable**
- Claude can **directly call MCP tools** via `mcp_servers` parameter

---

## Slide 6: Governance Framework

### Four Governance Pillars

| Pillar | Implementation |
|--------|----------------|
| Audit Trail | SQLite `audit.db` — 18 fields, immutable by UNIQUE constraint |
| Compliance Logs | `logs/compliance.jsonl` — RBI Fair Lending 2023 framework |
| Real-time Bias Check | Per-decision proxy variable analysis |
| Aggregate Bias Report | Disparate impact analysis across demographics |

### PII Protection
- Applicant names are **SHA-256 hashed** before any log or database write
- Original name only in Streamlit session state (never persisted)

### Compliance Record Example
```json
{
  "regulatory_framework": "RBI_FAIR_LENDING_2023",
  "protected_attributes_used": false,
  "bias_check_passed": true,
  "model_version": "claude-opus-4-5",
  "human_review_flag": false
}
```

---

## Slide 7: Observability & Traceability

### 6 Prometheus Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `loan_requests_total` | Counter | Total requests by verdict + employment type |
| `loan_processing_seconds` | Histogram | Processing time distribution |
| `loan_active_requests` | Gauge | Currently processing requests |
| `agent_failures_total` | Counter | Failures by agent + error type |
| `applicant_dti_ratio` | Histogram | EMI-to-Income ratio distribution across applicants |
| `mcp_calls_total` | Counter | MCP calls by server + tool + status |

### End-to-End Tracing
- Every request gets a **UUID trace ID** at entry
- All log lines carry `trace_id` for complete request reconstruction
- Span timing logged for each agent execution
- Fallback activations logged distinctly

```
GET /health
POST /api/evaluate
  trace_id: a1b2c3d4-...
  span: orchestrator → eligibility_check (2.1s)
  span: orchestrator → risk_assessment (1.4s)
  span: orchestrator → explainer (1.8s)
  decision: ELIGIBLE
```

---

## Slide 8: Evaluation Results

### Unit Test Results

| Test Suite | Tests | Pass Rate |
|------------|-------|-----------|
| Tool Functions | 26 | 100% |
| Eligibility Logic | 15 | 100% |
| Agent Fallbacks | 12 | 100% |
| Hook Chain | 16 | 100% |
| Governance | 9 | 100% |
| **Total** | **78** | **100%** |

### Accuracy on Test Cases

| Scenario | Expected | Actual |
|----------|----------|--------|
| All criteria pass | ELIGIBLE | ✅ ELIGIBLE |
| Age > 60 | NOT ELIGIBLE | ✅ NOT ELIGIBLE |
| Low credit + high EMI-to-Income | NOT ELIGIBLE | ✅ NOT ELIGIBLE |
| Borderline credit | MANUAL REVIEW | ✅ MANUAL REVIEW |

---

## Slide 9: Load Testing Results

### Test Configuration
- **Tool:** Locust 2.34
- **Target:** FastAPI endpoint (`/api/evaluate`)
- **Users:** 10 concurrent
- **Duration:** 60 seconds
- **Spawn Rate:** 2 users/second

### Results Summary

| Metric | Value |
|--------|-------|
| Total requests | ~60 (limited by Claude API) |
| Median response time | ~5-8 seconds |
| 95th percentile | ~12-15 seconds |
| Error rate | ~0% (exc. API rate limits) |
| Health check throughput | 200+ req/s |

*Bottleneck: Claude API rate limits. A caching layer for repeated applicant profiles would improve throughput significantly.*

---

## Slide 10: Deployment Architecture

```
┌─────────────────────────────────────────────────┐
│                   Browser                        │
└──────────────────────┬──────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
┌────────────────┐          ┌──────────────────┐
│  Streamlit     │          │  FastAPI         │
│  :8501         │          │  :8000           │
│  (Web UI)      │          │  (Load Test API) │
└───────┬────────┘          └────────┬─────────┘
        │                             │
        └──────────┬──────────────────┘
                   ▼
        ┌─────────────────────┐
        │   OrchestratorAgent  │
        │   Multi-Agent Pipeline│
        └──────────┬───────────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
┌────────┐   ┌────────┐   ┌─────────────┐
│MCP     │   │SQLite  │   │Prometheus   │
│:8765   │   │audit.db│   │:9090        │
│:8766   │   └────────┘   └─────────────┘
└────────┘
         │
         ▼
  Anthropic Claude API
  (external)
```

---

## Slide 11: Screenshots

### Streamlit UI — Eligible Decision
- Green "ELIGIBLE FOR LOAN" badge
- EMI-to-Income: 25% | Existing EMI/Income: 10% | Risk: LOW | Credit: 780
- Explanation: "Congratulations! Your profile meets all our requirements..."
- Reasons: all green checkmarks
- Recommendations: "Proceed with your application!"

### Streamlit UI — Not Eligible Decision
- Red "NOT ELIGIBLE" badge
- Reasons include credit score and EMI-to-Income ratio failures
- Recommendations: "Improve your credit score by paying loans on time"

### Audit Log Table
- Last 10 decisions with trace IDs, verdicts, EMI-to-Income ratios, timestamps

### Prometheus Metrics
- `loan_requests_total{verdict="ELIGIBLE"} 42`
- `loan_processing_seconds_p95 8.3`
- `applicant_emi_to_income_ratio_bucket{le="0.4"} 38`

---

## Slide 12: Business Impact

| Metric | Before AI Agent | After AI Agent |
|--------|----------------|----------------|
| Decision time | 2-3 days | < 10 seconds |
| Consistency | Variable | 100% rule-consistent |
| Auditability | Paper trail | Digital, searchable |
| Explainability | Verbal | Written, structured |
| Bias monitoring | Periodic audits | Real-time per decision |
| Compliance documentation | Manual | Automatic |

### Bonus Features Delivered
✅ **Multi-Agent Collaboration** — 4 specialized agents  
✅ **Multi-MCP Integration** — 2 FastMCP servers  
✅ **Autonomous Planning Agent** — dynamic execution plans  
✅ **Self-Healing Workflows** — retry + fallback rules engine  
