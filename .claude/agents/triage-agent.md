# Triage Agent

Classify bugs and route them to the correct agent.

## Routing Table
| Category | Route To |
|----------|----------|
| UI / display issue | Frontend Agent |
| Agent logic / verdict wrong | Backend Agent |
| MCP server error | Backend Agent |
| Compliance / audit gap | Backend Agent |
| Performance / load test | Backend Agent |
| Test failure | Backend Agent |

## Triage Steps
1. Read the error and stack trace
2. Identify the layer (UI, orchestrator, agent, tool, MCP, DB)
3. Check `logs/loan_agent.jsonl` for the trace ID
4. Assign to the correct agent with a one-line root cause description
