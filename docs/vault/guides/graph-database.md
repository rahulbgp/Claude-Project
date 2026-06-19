# Graph Database Guide

**Tags:** #guide #neo4j #graph

## Purpose

Loan decisions form a natural graph. Neo4j stores **relational nodes** that let you query:
- Which applicants share a risk profile?
- Which policy rules caused the most rejections?
- How do agent steps chain together for a given trace?

## Schema

```
(Applicant)-[:APPLIED_FOR]->(LoanApplication)
(LoanApplication)-[:EVALUATED_BY]->(Decision)
(Decision)-[:TRIGGERED_BY]->(PolicyRule)
(Decision)-[:ASSESSED_AS]->(RiskBand)
(Decision)-[:PROCESSED_BY]->(AgentStep)
(AgentStep)-[:NEXT]->(AgentStep)
```

## Node Types

| Label | Key Properties |
|-------|---------------|
| Applicant | applicant_hash, employment_type, age_group |
| LoanApplication | trace_id, loan_amount, credit_score, dti_ratio |
| Decision | verdict, risk_band, processing_time_ms |
| PolicyRule | rule_name, threshold, passed |
| RiskBand | band (LOW/MEDIUM/HIGH/CRITICAL), score |
| AgentStep | agent_name, duration_ms, status |

## Code

`graph/node_builder.py` — `build_decision_graph(decision, pre_context, trace_id)`

Called from `middleware/post_hooks.py` as an optional post-hook.

## Starting Neo4j

```bash
docker-compose up -d neo4j
```

Then open http://localhost:7474 — login neo4j / neo4jpassword.

## Example Cypher Queries

```cypher
-- Most common rejection reasons
MATCH (d:Decision)-[:TRIGGERED_BY]->(r:PolicyRule {passed: false})
RETURN r.rule_name, count(*) AS rejections
ORDER BY rejections DESC

-- Full trace for a specific application
MATCH path = (a:Applicant)-[:APPLIED_FOR]->(app)-[:EVALUATED_BY]->(d)-[:PROCESSED_BY]->(s)
WHERE app.trace_id = 'abc123'
RETURN path
```

## Related

- [[guides/architecture]]
- [[policies/risk-band-policy]]
