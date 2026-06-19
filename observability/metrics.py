"""
Prometheus metrics for the Loan Eligibility AI Agent.
Tracks request counts, processing times, active requests, failures, and MCP calls.
"""

import threading
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Track whether the metrics server has been started (avoid double-start)
_metrics_server_started = False
_metrics_lock = threading.Lock()


# ─── Metric Definitions ────────────────────────────────────────────────────────

# Total loan requests processed, broken down by verdict and employment type
LOAN_REQUESTS_TOTAL = Counter(
    "loan_requests_total",
    "Total number of loan eligibility requests processed",
    ["verdict", "employment_type"],
)

# Time taken to process each loan request (in seconds)
LOAN_PROCESSING_TIME = Histogram(
    "loan_processing_seconds",
    "Time taken to process a loan eligibility request",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0],
)

# Number of requests currently being processed
ACTIVE_REQUESTS = Gauge(
    "loan_active_requests",
    "Number of loan requests currently being processed",
)

# Agent-level failures (helps identify which agent is failing)
AGENT_FAILURES_TOTAL = Counter(
    "agent_failures_total",
    "Total number of agent execution failures",
    ["agent_name", "error_type"],
)

# Distribution of applicant DTI ratios (useful for risk analysis)
DTI_RATIO_HISTOGRAM = Histogram(
    "applicant_dti_ratio",
    "Distribution of EMI-to-Income ratios across applicants",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0],
)

# MCP server call tracking (helps monitor policy server usage)
MCP_CALLS_TOTAL = Counter(
    "mcp_calls_total",
    "Total number of MCP server tool calls",
    ["server_name", "tool_name", "status"],
)


def start_metrics_server(port: int = 9090) -> None:
    """Start the Prometheus metrics HTTP server (only starts once)."""
    global _metrics_server_started
    with _metrics_lock:
        if not _metrics_server_started:
            try:
                start_http_server(port)
                _metrics_server_started = True
                print(f"[Metrics] Prometheus metrics server started on port {port}")
            except OSError:
                # Port already in use (e.g., reloading Streamlit) — that's fine
                _metrics_server_started = True


def record_request(verdict: str, employment_type: str, duration_seconds: float, dti_ratio: float) -> None:
    """Record metrics for a completed loan request."""
    LOAN_REQUESTS_TOTAL.labels(verdict=verdict, employment_type=employment_type).inc()
    LOAN_PROCESSING_TIME.observe(duration_seconds)
    DTI_RATIO_HISTOGRAM.observe(min(dti_ratio, 1.0))


def record_agent_failure(agent_name: str, error_type: str) -> None:
    """Record an agent-level failure."""
    AGENT_FAILURES_TOTAL.labels(agent_name=agent_name, error_type=error_type).inc()


def record_mcp_call(server_name: str, tool_name: str, success: bool) -> None:
    """Record an MCP tool call."""
    status = "success" if success else "failure"
    MCP_CALLS_TOTAL.labels(server_name=server_name, tool_name=tool_name, status=status).inc()
