# Triage Agent (P3)

Classify bugs and route them to the correct agent. Review and report.

## Agent Pipeline Reference
CustomerAgent → KnowledgeAgent → EligibilityCheckerAgent → RiskAssessorAgent
→ ExplainerAgent → ComplianceAgent → AuditAgent

## Routing Table
| Symptom | Layer | Route To |
|---------|-------|----------|
| UI / display issue | frontend/ | Frontend Agent |
| Wrong verdict | agents/orchestrator.py | Backend Agent |
| Wrong risk band | agents/risk_assessor.py | Backend Agent |
| MCP timeout / error | mcp/ | Backend Agent |
| Compliance flag not raised | agents/compliance_agent.py | Backend Agent |
| Audit record missing fields | agents/audit_agent.py | Backend Agent |
| Customer segment wrong | agents/customer_agent.py | Backend Agent |
| RAG returning wrong docs | rag/retriever.py | Backend Agent |
| Token spike | observability/metrics.py | Backend Agent |
| Test failure | tests/ | Backend Agent |
| OTel spans missing | observability/otel_tracer.py | Backend Agent |

## Triage Steps
1. Read error + stack trace
2. Check `logs/loan_agent.jsonl` for the trace_id
3. Identify which agent/layer originated the error
4. Assign to the correct specialist agent with a one-line root cause description
