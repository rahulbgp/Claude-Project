---
description: Start the LoanRulesMCP (port 8765) and AuditMCP (port 8766) servers
---

Start both MCP servers for the loan eligibility system.

## What this does
Calls `mcp/server.py::start_mcp_servers()` to launch:
- **LoanRulesMCP** on port 8765 — exposes loan policy rules (credit thresholds, DTI limits, age policy, employment scores, loan products, compliance rules)
- **AuditMCP** on port 8766 — exposes audit trail (log decisions, retrieve decision history)

Both servers run as daemon threads using FastMCP + uvicorn.

## Run
```bash
python -c "
from mcp.server import start_mcp_servers
import time
start_mcp_servers()
print('MCP servers starting on ports 8765 and 8766...')
time.sleep(2)
print('Ready.')
"
```

## Verify
```bash
curl http://localhost:8765/mcp
curl http://localhost:8766/mcp
```

These servers are also auto-started when `app.py` (Streamlit UI) launches. Only start them manually when running tests or the FastAPI endpoint without the Streamlit UI.
