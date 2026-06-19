# Loan Eligibility AI Agent — Claude Onboarding

## What This Project Does
A multi-agent banking system that evaluates loan eligibility using the Anthropic Claude API.
A Streamlit UI collects applicant data, passes it through a 3-agent pipeline
(EligibilityChecker → RiskAssessor → Explainer), and returns a verdict with explanation.

## Architecture
```
frontend/app.py          ← Streamlit UI (entry point: streamlit run frontend/app.py)
orchestrator/            ← SDK delegation hub
agents/                  ← EligibilityCheckerAgent, RiskAssessorAgent, ExplainerAgent
core/                    ← Domain models, rules engine, context manager
tools/                   ← Claude tool schemas + implementations
mcp/                     ← HTTP MCP servers (LoanRulesMCP :8765, AuditMCP :8766)
rag/                     ← TF-IDF knowledge retrieval
observability/           ← JSON logging, Prometheus metrics, tracing
governance/              ← Audit trail (SQLite), compliance logger, bias report
hooks/                   ← Pre/post processing hooks
config/                  ← All settings, thresholds, env vars
```

## Quick Start
```bash
cp .env.example .env          # Add your ANTHROPIC_API_KEY
bash setup.sh                 # Install dependencies
streamlit run frontend/app.py # Launch UI
```

## Key Rules (see .claude/rules/ for full details)
- All thresholds live in `config/settings.py` — never hardcode values in agent code
- Every agent must have a `_fallback_*` rule-based path (self-healing)
- All decisions must be logged via `governance/audit_trail.py` with a trace ID
- Verdicts are determined by hard rules in `core/rules_engine.py`, not by Claude

## Running Tests
```bash
pytest tests/ -v
locust -f load_tests/locustfile.py --host=http://localhost:8000 --headless \
       --users 5 --spawn-rate 1 --run-time 30s
```

## Environment Variables
See `.env.example` for all required variables. Key ones:
- `ANTHROPIC_API_KEY` — required
- `ANTHROPIC_MODEL` — default: `claude-sonnet-4-6`
- `MCP_LOAN_RULES_PORT` — default: `8765`
- `MCP_AUDIT_PORT` — default: `8766`
- `PROMETHEUS_PORT` — default: `9090`
