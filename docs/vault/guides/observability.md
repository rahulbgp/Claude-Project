# Observability Guide

**Tags:** #guide #observability #prometheus #grafana #opentelemetry

## Stack

| Tool | Port | URL | Purpose |
|------|------|-----|---------|
| App metrics | 9090 | http://localhost:9090/metrics | Prometheus scrape target |
| Prometheus | 9091 | http://localhost:9091 | Time-series DB |
| Grafana | 3000 | http://localhost:3000 | Dashboards (admin/admin) |
| OTel Collector | 4317 | — | OTLP gRPC (optional) |
| SigNoz | 3301 | http://localhost:3301 | Full-stack OTel UI (optional) |

## Starting the Stack

```bash
docker-compose up -d
```

## Prometheus Metrics

Defined in `observability/metrics.py`:

| Metric | Type | Description |
|--------|------|-------------|
| `loan_requests_total` | Counter | Total requests by verdict + employment |
| `loan_active_requests` | Gauge | Currently processing |
| `loan_processing_seconds` | Histogram | End-to-end latency |
| `applicant_dti_ratio` | Histogram | DTI distribution |
| `agent_failures_total` | Counter | Failures per agent |
| `llm_tokens_total` | Counter | Token usage per agent |
| `llm_tokens_per_request` | Histogram | Tokens per call |
| `mcp_calls_total` | Counter | MCP call success/failure |

## OpenTelemetry

`observability/otel_tracer.py` — initialized at startup with optional OTLP endpoint.

Set `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317` in `.env` to export traces to Grafana Tempo or SigNoz.

## Grafana Dashboards

- **Loan Eligibility Agent** — 12 panels covering all 8 metrics
- **K6 Load Test** — 8 panels covering virtual users, request rate, latency percentiles

## Related

- [[guides/load-testing]]
- [[guides/architecture]]
