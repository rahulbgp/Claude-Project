"""
Distributed tracing for the Loan Eligibility AI Agent.
Generates trace IDs and span context managers for end-to-end request tracing.
"""

import uuid
import time
import logging
from contextlib import contextmanager
from typing import Generator


logger = logging.getLogger(__name__)


class Tracer:
    """
    Manages trace IDs and execution spans.
    Every loan request gets a unique trace_id. All log entries within
    that request carry the same trace_id so you can reconstruct the full
    execution timeline from the log file.
    """

    def generate_trace_id(self) -> str:
        """Generate a unique trace ID for a new loan request."""
        return str(uuid.uuid4())

    @contextmanager
    def trace_span(
        self, trace_id: str, span_name: str, agent_name: str = "unknown"
    ) -> Generator[dict, None, None]:
        """
        Context manager that logs the start and end of a processing span.

        Usage:
            with tracer.trace_span(trace_id, "eligibility_check", "EligibilityAgent") as span:
                result = do_work()
                span["result_summary"] = result.verdict
        """
        start_time = time.time()
        span_data: dict = {
            "trace_id": trace_id,
            "span_name": span_name,
            "agent_name": agent_name,
            "start_time": start_time,
        }

        logger.info(
            "Span started",
            extra={
                "trace_id": trace_id,
                "span": span_name,
                "agent": agent_name,
                "event": "span_start",
            },
        )

        try:
            yield span_data
        finally:
            duration_ms = (time.time() - start_time) * 1000
            span_data["duration_ms"] = duration_ms

            logger.info(
                "Span completed",
                extra={
                    "trace_id": trace_id,
                    "span": span_name,
                    "agent": agent_name,
                    "duration_ms": round(duration_ms, 2),
                    "event": "span_end",
                },
            )

    def log_plan(self, trace_id: str, plan: list) -> None:
        """Log the orchestrator's execution plan as a structured JSON entry."""
        logger.info(
            "Execution plan created",
            extra={
                "trace_id": trace_id,
                "event": "plan_created",
                "plan_steps": [step["name"] for step in plan],
                "plan_count": len(plan),
            },
        )

    def log_agent_retry(
        self, trace_id: str, agent_name: str, attempt: int, error: str
    ) -> None:
        """Log a retry attempt for a failed agent call."""
        logger.warning(
            "Agent retry",
            extra={
                "trace_id": trace_id,
                "event": "agent_retry",
                "agent": agent_name,
                "attempt": attempt,
                "error": error,
            },
        )

    def log_fallback_activated(self, trace_id: str, agent_name: str, reason: str) -> None:
        """Log when the self-healing fallback is activated."""
        logger.warning(
            "Fallback activated",
            extra={
                "trace_id": trace_id,
                "event": "fallback_activated",
                "agent": agent_name,
                "reason": reason,
            },
        )

    def log_decision(self, trace_id: str, verdict: str, dti_ratio: float) -> None:
        """Log the final loan decision."""
        logger.info(
            "Loan decision made",
            extra={
                "trace_id": trace_id,
                "event": "decision",
                "verdict": verdict,
                "dti_ratio": round(dti_ratio, 4),
            },
        )


# Singleton tracer instance used across the application
tracer = Tracer()
