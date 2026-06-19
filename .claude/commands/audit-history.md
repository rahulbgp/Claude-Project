---
description: Query the audit trail and compliance logs for recent loan decisions
---

Retrieve and display recent loan decisions from the audit trail.

## SQLite audit trail
```python
import sqlite3, json
conn = sqlite3.connect("audit.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT trace_id, timestamp, applicant_hash, verdict, dti_ratio, risk_band,
           reasons, model_used, processing_time_ms
    FROM audit_log
    ORDER BY id DESC
    LIMIT 20
""").fetchall()
conn.close()
for r in rows:
    print(dict(r))
```

## JSONL compliance log
```bash
tail -20 logs/compliance.jsonl | python -m json.tool
```

## Manual review queue
```bash
cat logs/manual_review_queue.jsonl
```

## Via AuditMCP tool (if MCP server is running)
```python
# Uses the get_decision_history MCP tool
import httpx
resp = httpx.post("http://localhost:8766/mcp",
    json={"method": "tools/call", "params": {"name": "get_decision_history", "arguments": {"limit": 10}}})
print(resp.json())
```

If $ARGUMENTS specifies a trace_id or verdict filter, apply it to the query above.
