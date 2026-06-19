# Loan Eligibility AI Agent

A multi-agent banking application that uses Claude AI to evaluate loan eligibility with full governance, observability, and compliance support.

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set your Anthropic API key

```bash
cp .env.example .env
# Edit .env and add: ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 3. Run the application

```bash
streamlit run app.py
```

Open http://localhost:8501 in your browser.

---

## What It Does

Fill in the loan application form with:

| Field | Description |
|-------|-------------|
| **Name** | Applicant full name |
| **Age** | Must be 21–60 years |
| **Monthly Income** | Net monthly take-home (₹) |
| **Existing EMI** | Current monthly loan payments (₹) |
| **Credit Score** | CIBIL score (300–900) |
| **Employment Type** | Salaried / Self-Employed / Contract / Unemployed |
| **Loan Amount Required** | Requested loan amount (₹) |

The AI agent will return one of three verdicts:

- 🟢 **ELIGIBLE** — Approved based on all criteria
- 🔴 **NOT ELIGIBLE** — One or more hard rules failed
- 🟡 **NEEDS MANUAL REVIEW** — Borderline case requires human review

Along with:
- Plain-English explanation
- EMI-to-income ratio
- Specific reasons for the decision
- Actionable recommendations

---

## Eligibility Rules

| Rule | Threshold |
|------|-----------|
| Credit Score | **≥ 700** required (≥ 750 = Excellent) |
| EMI-to-Income Ratio | Total EMI must be **≤ 40%** of monthly income |
| Age | Must be between **21 and 60** years |
| Employment | Salaried > Self-Employed > Contract > Unemployed |

---

## Architecture

This project uses a **multi-agent system** built on the Anthropic SDK:

```
Pre-Hooks → OrchestratorAgent → EligibilityCheckerAgent
                              → RiskAssessorAgent
                              → ExplainerAgent
          → Post-Hooks
```

- **8 Skills** (`tools/loan_tools.py`) — tool functions Claude calls
- **2 MCP Servers** (`mcp/server.py`) — FastMCP for loan rules and audit
- **5 Pre-Hooks** — validate, sanitize, mask PII, enrich, rate-limit
- **5 Post-Hooks** — audit trail, compliance log, metrics, bias check, review queue
- **Autonomous Planning** — orchestrator creates dynamic execution plans
- **Self-Healing** — retries with backoff; falls back to rule engine if API fails

---

## Services

| Service | Port | Description |
|---------|------|-------------|
| Streamlit UI | 8501 | Web interface |
| FastAPI (load test) | 8000 | REST API endpoint |
| LoanRulesMCP | 8765 | Policy rules MCP server |
| AuditMCP | 8766 | Audit log MCP server |
| Prometheus | 9090 | Metrics endpoint |

---

## Running Tests

```bash
# Unit tests
pytest tests/ -v

# Load tests (start api.py first)
uvicorn api:app --port 8000 &
locust -f tests/locustfile.py --host=http://localhost:8000 \
       --users=10 --spawn-rate=2 --run-time=60s --headless
```

---

## Files

```
├── app.py               # Streamlit UI
├── api.py               # FastAPI REST endpoint
├── config.py            # Configuration constants
├── requirements.txt     # Dependencies
├── .env.example         # API key template
├── agents/              # Multi-agent system
│   ├── orchestrator.py  # Central coordinator
│   ├── eligibility_checker.py
│   ├── risk_assessor.py
│   └── explainer.py
├── tools/               # Tool functions (Skills)
│   └── loan_tools.py    # 8 @tool functions
├── mcp/                 # MCP servers
│   └── server.py        # LoanRulesMCP + AuditMCP
├── hooks/               # Pre/post hooks
├── governance/          # Audit trail + compliance
├── observability/       # Metrics + logging
├── tests/               # Unit + load tests
└── docs/                # Architecture + design docs
```

---

## Logs and Audit

After running, find:

- `logs/loan_agent.jsonl` — structured request logs
- `logs/compliance.jsonl` — compliance records
- `logs/manual_review_queue.jsonl` — cases needing human review
- `audit.db` — full decision audit trail (SQLite)

---

## Documentation

| Document | Location |
|----------|----------|
| Architecture Diagram | `docs/architecture.md` |
| Technical Design | `docs/technical_design.md` |
| Governance Report | `docs/governance_report.md` |
| Testing Report | `docs/testing_report.md` |
| Deployment Guide | `docs/deployment_guide.md` |
| Presentation Deck | `docs/presentation.md` |
