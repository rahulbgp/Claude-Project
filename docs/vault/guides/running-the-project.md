# Running the Project

**Tags:** #guide #setup

## Prerequisites

- Python 3.11+
- Docker + Docker Compose
- Anthropic API key
- (Optional) K6 binary for load testing
- (Optional) Obsidian Desktop for vault viewing

## Quick Start

```bash
# 1. Clone and install dependencies
pip install -r requirements.txt

# 2. Set your Anthropic API key
echo "ANTHROPIC_API_KEY=sk-..." >> .env

# 3. Start observability stack
docker-compose up -d

# 4. Run the Streamlit UI
streamlit run app.py

# 5. (Optional) Run the REST API for load testing
uvicorn api:app --host 0.0.0.0 --port 8000
```

## Service URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| Streamlit App | http://localhost:8501 | — |
| FastAPI | http://localhost:8000 | — |
| Prometheus metrics | http://localhost:9090/metrics | — |
| Prometheus UI | http://localhost:9091 | — |
| Grafana | http://localhost:3000 | admin / admin |
| LoanRulesMCP | http://localhost:8765/mcp | — |
| AuditMCP | http://localhost:8766/mcp | — |
| OrchestrationMCP | http://localhost:8767/mcp | — |
| Neo4j Browser | http://localhost:7474 | neo4j / neo4jpassword |
| Neo4j Bolt | bolt://localhost:7687 | — |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `""` | OTLP endpoint for traces (optional) |
| `OTEL_SERVICE_NAME` | `loan-eligibility-agent` | OTel service name |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `neo4jpassword` | Neo4j password |
| `PROMETHEUS_PORT` | `9090` | App metrics port |

## Related

- [[guides/architecture]]
- [[guides/observability]]
- [[guides/load-testing]]
