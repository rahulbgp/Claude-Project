# Load Testing Guide

**Tags:** #guide #load-testing #k6 #locust

## Tools Available

| Tool | Script | Output |
|------|--------|--------|
| Locust | `load_tests/locustfile.py` | Web UI at :8089 |
| K6 | `load_tests/k6_script.js` | JSON + Grafana |

## Locust

```bash
# Start the API first
uvicorn api:app --host 0.0.0.0 --port 8000

# Run Locust web UI
locust -f load_tests/locustfile.py --host=http://localhost:8000

# Headless
locust -f load_tests/locustfile.py --host=http://localhost:8000 \
       --users 10 --spawn-rate 2 --run-time 60s --headless
```

## K6

```bash
# Install K6
# macOS: brew install k6
# Linux: https://k6.io/docs/getting-started/installation/

# Basic run
k6 run load_tests/k6_script.js

# With Prometheus remote-write output (needs K6 built with xk6-prometheus)
K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9090/api/v1/write \
k6 run --out=experimental-prometheus-rw load_tests/k6_script.js

# With InfluxDB output (classic K6 OSS)
k6 run --out influxdb=http://localhost:8086/k6 load_tests/k6_script.js
```

### Load Profile

| Stage | VUs | Duration |
|-------|-----|----------|
| Ramp up | 5 | 30s |
| Steady | 10 | 60s |
| Spike | 20 | 30s |
| Recover | 10 | 30s |
| Ramp down | 0 | 30s |

### Thresholds

| Metric | Threshold |
|--------|-----------|
| `http_req_duration p(95)` | < 30s |
| `http_req_failed` | < 5% |
| `loan_api_error_rate` | < 10% |

## Grafana Dashboard

The **K6 Load Test — Loan Agent** dashboard (`observability/grafana/provisioning/dashboards/k6-load-test.json`) visualises K6 metrics once exported to Prometheus.

## Related

- [[guides/observability]]
- [[guides/architecture]]
