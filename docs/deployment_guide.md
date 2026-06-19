# Deployment Guide

## Loan Eligibility AI Agent

---

## Prerequisites

- Python 3.9+ (tested on 3.14)
- Anthropic API key (get from [console.anthropic.com](https://console.anthropic.com))
- 4GB+ RAM recommended
- Ports 8501, 8000, 8765, 8766, 9090 available

---

## 1. Quick Start (Local Development)

### Step 1: Clone / setup the project

```bash
# Navigate to the project directory
cd "Claude Project"

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate   # Linux/Mac
# venv\Scripts\activate    # Windows

# OR use the existing venv at /home/labuser/venv
source /home/labuser/venv/bin/activate
```

### Step 2: Install dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Configure API key

```bash
cp .env.example .env

# Edit .env and set your API key:
# ANTHROPIC_API_KEY=sk-ant-your-key-here
nano .env
```

### Step 4: Run the Streamlit app

```bash
streamlit run app.py
```

The app opens at **http://localhost:8501**

---

## 2. Running All Services

For the full system with load testing support:

**Terminal 1 — Streamlit UI:**
```bash
streamlit run app.py
# Opens at http://localhost:8501
```

**Terminal 2 — FastAPI REST endpoint (for load testing):**
```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
# Opens at http://localhost:8000
# Docs at http://localhost:8000/docs
```

MCP servers and Prometheus metrics start automatically when either app starts.

---

## 3. Verifying the System

**Check Prometheus metrics:**
```bash
curl http://localhost:9090/metrics
# Should return Prometheus text format with loan_requests_total etc.
```

**Check audit log:**
```bash
tail -f logs/loan_agent.jsonl
# Shows structured JSON log entries
```

**Check compliance log:**
```bash
tail -f logs/compliance.jsonl
# Shows compliance records after each decision
```

**Check audit database:**
```bash
sqlite3 audit.db "SELECT trace_id, verdict, dti_ratio AS emi_to_income_ratio FROM audit_log ORDER BY id DESC LIMIT 5;"
```

---

## 4. Running Tests

```bash
# Run all unit tests
pytest tests/ -v

# Run with coverage
pip install pytest-cov
pytest tests/ --cov=. --cov-report=term-missing

# Run specific test file
pytest tests/test_tools.py -v
pytest tests/test_eligibility.py -v
```

---

## 5. Load Testing

```bash
# Start FastAPI first (Terminal 2 above)

# Run load test headless (60 seconds, 10 users):
locust -f tests/locustfile.py \
       --host=http://localhost:8000 \
       --users=10 \
       --spawn-rate=2 \
       --run-time=60s \
       --headless

# Or with the Locust web UI:
locust -f tests/locustfile.py --host=http://localhost:8000
# Open http://localhost:8089 to configure and start the test
```

---

## 6. Configuration Options

Edit `config.py` or set environment variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | (required) | Your Anthropic API key |
| `ANTHROPIC_MODEL` | `claude-opus-4-5` | Claude model to use |
| `MCP_LOAN_RULES_PORT` | `8765` | LoanRulesMCP server port |
| `MCP_AUDIT_PORT` | `8766` | AuditMCP server port |
| `PROMETHEUS_PORT` | `9090` | Prometheus metrics port |

---

## 7. Customizing Loan Policies

To change loan policy thresholds without modifying code, create a `policies.yaml` file in the project root:

```yaml
credit_score:
  min_credit_score: 650   # Lower minimum
  excellent_threshold: 720

emi_to_income:
  max_ratio: 0.45     # Allow 45% EMI-to-Income ratio
  preferred_ratio: 0.35

age:
  min_age: 18             # Lower minimum age
  max_age: 65
```

The MCP server loads this file at startup and serves the custom values.

---

## 8. Troubleshooting

**Problem:** `ANTHROPIC_API_KEY not set`  
**Solution:** Create a `.env` file with your API key (copy from `.env.example`)

**Problem:** `Address already in use` for MCP server ports  
**Solution:** Kill processes on ports 8765/8766: `fuser -k 8765/tcp 8766/tcp`

**Problem:** Streamlit shows only fallback decisions (no AI explanations)  
**Solution:** The self-healing fallback is working correctly. Check your API key and network connectivity.

**Problem:** Tests fail with `ModuleNotFoundError`  
**Solution:** Make sure you're running from the project root directory and the virtualenv is activated.

**Problem:** Prometheus port 9090 already in use  
**Solution:** Set `PROMETHEUS_PORT=9091` in your `.env` file.

---

## 9. Production Deployment Notes

For production deployment:

1. **Use a process manager** (systemd, supervisor, or Docker) to keep services running
2. **Set up nginx** as a reverse proxy in front of Streamlit (:8501) for SSL termination
3. **Use PostgreSQL** instead of SQLite for the audit trail at scale
4. **Set up Grafana** to visualize Prometheus metrics
5. **Configure log rotation** for the JSONL log files
6. **Use environment-specific `.env` files** (never commit real API keys)
7. **Set up alerting** on `agent_failures_total` metric spikes

---

## 10. File Structure Reference

```
Claude Project/
├── app.py               # streamlit run app.py
├── api.py               # uvicorn api:app --port 8000
├── config.py            # All configuration constants
├── requirements.txt     # pip install -r requirements.txt
├── .env.example         # Copy to .env, add API key
├── README.md            # Quick-start guide
├── audit.db             # Created automatically on first run
├── logs/                # Created automatically
│   ├── loan_agent.jsonl
│   ├── compliance.jsonl
│   └── manual_review_queue.jsonl
├── agents/              # Multi-agent system
├── tools/               # Skills (@tool functions)
├── mcp/                 # FastMCP servers
├── hooks/               # Pre/post processing
├── governance/          # Audit + compliance
├── observability/       # Metrics + logging
├── tests/               # pytest + locust
└── docs/                # Documentation
```
