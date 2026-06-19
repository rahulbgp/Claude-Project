# Loan Eligibility AI Agent — Knowledge Vault

> **Obsidian README Mode** — open this vault in Obsidian Desktop to browse all notes with graph view, backlinks, and live preview.
>
> `File → Open Vault → select docs/vault/`

## Contents

| Section | Notes |
|---------|-------|
| [[policies/credit-score-policy]] | Credit score thresholds and CIBIL rules |
| [[policies/dti-ratio-policy]] | EMI-to-income ratio limits |
| [[policies/age-policy]] | Age eligibility criteria |
| [[policies/employment-policy]] | Employment stability scores |
| [[policies/risk-band-policy]] | Composite risk band calculation |
| [[policies/compliance-policy]] | RBI Fair Lending compliance rules |
| [[agents/orchestrator-agent]] | OrchestratorAgent — top-level coordinator |
| [[agents/eligibility-checker]] | EligibilityCheckerAgent — rule evaluator |
| [[agents/risk-assessor]] | RiskAssessorAgent — band scorer |
| [[agents/explainer-agent]] | ExplainerAgent — narrative generator |
| [[guides/architecture]] | System architecture overview |
| [[guides/running-the-project]] | How to run locally |
| [[guides/observability]] | Prometheus, Grafana, OTel |
| [[guides/load-testing]] | Locust & K6 usage |
| [[guides/graph-database]] | Neo4j relational nodes |

## Quick Start

```bash
# Run the Streamlit UI
streamlit run app.py

# Run the FastAPI endpoint (for load tests)
uvicorn api:app --port 8000

# Start Prometheus + Grafana
docker-compose up -d

# Run K6 load test
k6 run load_tests/k6_script.js

# Open Obsidian
# File → Open Vault → docs/vault/
```

## Graph View

Use **Cmd/Ctrl + G** in Obsidian to open the graph view. Nodes are coloured by section:
- 🔵 **Blue** — policies/
- 🟢 **Green** — agents/
- 🟡 **Yellow** — guides/
