"""
OpenTelemetry tracing and metrics for the Loan Eligibility AI Agent.

Exports traces and metrics via OTLP (compatible with Jaeger, Grafana Tempo,
SigNoz, and any OpenTelemetry Collector).

Falls back gracefully to no-op if opentelemetry packages are not installed.
"""

import logging
import time
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

# ── Try to import OTel; degrade gracefully if not installed ────────────────────
try:
    from opentelemetry import trace, metrics as otel_metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        ConsoleMetricExporter,
        PeriodicExportingMetricReader,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.semconv.resource import ResourceAttributes
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        _OTLP_AVAILABLE = True
    except ImportError:
        _OTLP_AVAILABLE = False
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False
    _OTLP_AVAILABLE = False

_initialized = False

# Module-level tracer and meter (no-op if OTel not available)
_tracer = None
_meter = None

# OTel metric instruments
_request_counter = None
_latency_histogram = None
_token_counter = None
_agent_failure_counter = None


def initialize(
    service_name: str = "loan-eligibility-agent",
    otlp_endpoint: Optional[str] = None,
    enable_console: bool = False,
) -> None:
    """
    Initialize OpenTelemetry providers.
    Call once at application startup (app.py / api.py).

    Args:
        service_name: OTel resource service.name
        otlp_endpoint: e.g. "http://localhost:4317" for Grafana Agent / SigNoz / Jaeger
        enable_console: also print spans to stdout (useful for local debugging)
    """
    global _initialized, _tracer, _meter
    global _request_counter, _latency_histogram, _token_counter, _agent_failure_counter

    if _initialized or not _OTEL_AVAILABLE:
        if not _OTEL_AVAILABLE:
            logger.warning(
                "OpenTelemetry packages not installed. "
                "Run: pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc"
            )
        return

    resource = Resource.create({ResourceAttributes.SERVICE_NAME: service_name})

    # ── Trace provider ────────────────────────────────────────────────────────
    trace_provider = TracerProvider(resource=resource)

    if otlp_endpoint and _OTLP_AVAILABLE:
        otlp_span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        trace_provider.add_span_processor(BatchSpanProcessor(otlp_span_exporter))
        logger.info(f"OTel traces → OTLP at {otlp_endpoint}")

    if enable_console:
        trace_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(trace_provider)
    _tracer = trace.get_tracer(service_name)

    # ── Metrics provider ──────────────────────────────────────────────────────
    readers = []
    if otlp_endpoint and _OTLP_AVAILABLE:
        otlp_metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)
        readers.append(PeriodicExportingMetricReader(otlp_metric_exporter, export_interval_millis=15000))

    if enable_console:
        readers.append(PeriodicExportingMetricReader(ConsoleMetricExporter(), export_interval_millis=30000))

    meter_provider = MeterProvider(resource=resource, metric_readers=readers)
    otel_metrics.set_meter_provider(meter_provider)
    _meter = otel_metrics.get_meter(service_name)

    # ── Metric instruments ────────────────────────────────────────────────────
    _request_counter = _meter.create_counter(
        "loan_requests_total",
        description="Total loan eligibility requests",
        unit="1",
    )
    _latency_histogram = _meter.create_histogram(
        "loan_request_duration_ms",
        description="Loan request processing latency in milliseconds",
        unit="ms",
    )
    _token_counter = _meter.create_counter(
        "llm_tokens_total",
        description="Total LLM tokens used (input + output)",
        unit="1",
    )
    _agent_failure_counter = _meter.create_counter(
        "agent_failures_total",
        description="Total agent-level failures",
        unit="1",
    )

    _initialized = True
    logger.info("OpenTelemetry initialized")


@contextmanager
def trace_span(trace_id: str, span_name: str, agent_name: str = "unknown",
               attributes: Optional[dict] = None):
    """
    Context manager that creates an OTel span if OTel is initialized,
    otherwise falls back to a plain timing block.

    Usage:
        with otel_tracer.trace_span(trace_id, "eligibility_check", "EligibilityAgent") as span:
            result = do_work()
    """
    start = time.time()
    span_attrs = {"trace_id": trace_id, "agent": agent_name, **(attributes or {})}

    if _tracer:
        with _tracer.start_as_current_span(span_name, attributes=span_attrs) as otel_span:
            try:
                yield otel_span
            except Exception as exc:
                otel_span.record_exception(exc)
                raise
            finally:
                duration_ms = (time.time() - start) * 1000
                otel_span.set_attribute("duration_ms", round(duration_ms, 2))
    else:
        # No-op span — just yield a plain dict
        span_data = {"trace_id": trace_id, "span_name": span_name}
        try:
            yield span_data
        finally:
            pass


def record_request(verdict: str, employment_type: str, duration_ms: float) -> None:
    """Record a completed loan request in OTel metrics."""
    if _request_counter:
        _request_counter.add(1, {"verdict": verdict, "employment_type": employment_type})
    if _latency_histogram:
        _latency_histogram.record(duration_ms, {"verdict": verdict})


def record_token_usage(agent_name: str, input_tokens: int, output_tokens: int) -> None:
    """Record LLM token usage for an agent call."""
    if _token_counter:
        _token_counter.add(input_tokens, {"agent": agent_name, "type": "input"})
        _token_counter.add(output_tokens, {"agent": agent_name, "type": "output"})
    logger.debug(
        "Token usage",
        extra={
            "agent": agent_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


def record_agent_failure(agent_name: str, error_type: str) -> None:
    """Record an agent failure in OTel metrics."""
    if _agent_failure_counter:
        _agent_failure_counter.add(1, {"agent": agent_name, "error_type": error_type})
