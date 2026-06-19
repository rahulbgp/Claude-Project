# System Architecture

**Tags:** #guide #architecture

## Layer Diagram

```
User → Streamlit (app.py) / FastAPI (api.py)
          │
          ▼
    Pre-Hooks (middleware/pre_hooks.py)
    [validate → sanitize → mask PII → enrich → rate-limit]
          │
          ▼
    OrchestratorAgent (pipeline/orchestrator.py)
       ├── EligibilityCheckerAgent
       ├── RiskAssessorAgent
       └── ExplainerAgent
          │
          ▼
    Post-Hooks (middleware/post_hooks.py)
    [audit trail → compliance log → Prometheus → bias check → review queue]
          │
          ├── MCP Servers (services/)
          │     ├── LoanRulesMCP :8765
          │     ├── AuditMCP     :8766
          │     └── OrchestrationMCP :8767  ← generic reusable
          │
          ├── Observability (observability/)
          │     ├── Prometheus metrics :9090
          │     ├── Grafana :3000
          │     └── OTel → OTLP endpoint
          │
          └── Graph DB (graph/)
                └── Neo4j :7687
```

## Key Files

| Layer | File |
|-------|------|
| Streamlit UI | `app.py` |
| REST API | `api.py` |
| Orchestrator | `pipeline/orchestrator.py` |
| Tools | `tools/loan_tools.py` |
| MCP Servers | `services/server.py`, `services/orchestration_mcp.py` |
| Metrics | `observability/metrics.py` |
| OTel Tracing | `observability/otel_tracer.py` |
| Graph DB | `graph/node_builder.py` |

## Related

- [[agents/orchestrator-agent]]
- [[guides/observability]]
- [[guides/graph-database]]
