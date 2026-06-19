"""
FastAPI REST endpoint for the Loan Eligibility AI Agent.
Used for load testing with Locust (Streamlit is not a standard REST API).

Run alongside Streamlit:
    uvicorn api:app --host 0.0.0.0 --port 8000

Endpoints:
    GET  /health         — health check
    POST /api/evaluate   — run loan eligibility check, returns JSON decision
    GET  /api/stats      — aggregate statistics from audit trail
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from observability.json_logger import setup_logging
from observability.metrics import start_metrics_server
from observability.tracer import tracer
from governance import audit_trail
from hooks.pre_hooks import run_pre_hooks
from hooks.post_hooks import run_post_hooks
from agents.orchestrator import OrchestratorAgent
from config import PROMETHEUS_PORT, MCP_LOAN_RULES_PORT, MCP_AUDIT_PORT

# ─── App Setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Loan Eligibility AI Agent API",
    description="REST API for loan eligibility checking — used for load testing and programmatic access",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Startup ───────────────────────────────────────────────────────────────────
_orchestrator: OrchestratorAgent = None


@app.on_event("startup")
async def startup():
    global _orchestrator
    setup_logging()
    start_metrics_server(PROMETHEUS_PORT)
    audit_trail.initialize_db()

    try:
        from mcp.server import start_mcp_servers
        start_mcp_servers(MCP_LOAN_RULES_PORT, MCP_AUDIT_PORT)
    except Exception:
        pass

    _orchestrator = OrchestratorAgent()


# ─── Request / Response Models ─────────────────────────────────────────────────
class LoanApplicationRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, example="Rahul Sharma")
    age: int = Field(..., ge=18, le=80, example=35)
    monthly_income: float = Field(..., gt=0, example=75000)
    existing_emi: float = Field(..., ge=0, example=10000)
    credit_score: int = Field(..., ge=300, le=900, example=720)
    employment_type: str = Field(..., example="Salaried")
    loan_amount: float = Field(..., gt=0, example=500000)


class LoanDecisionResponse(BaseModel):
    trace_id: str
    verdict: str
    reasons: list
    recommendations: list
    emi_to_income_ratio: float
    dti_ratio: float
    risk_band: str
    explanation: str
    processing_time_ms: int


# ─── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "loan-eligibility-ai-agent"}


@app.post("/api/evaluate", response_model=LoanDecisionResponse)
async def evaluate_loan(application: LoanApplicationRequest):
    """
    Evaluate loan eligibility for the given applicant data.
    Returns a structured decision with verdict, reasons, and recommendations.
    """
    trace_id = tracer.generate_trace_id()
    start_time = time.time()

    applicant_data = application.model_dump()

    try:
        # Pre-processing hooks
        pre_context = run_pre_hooks(applicant_data, trace_id=trace_id)

        # Run multi-agent pipeline
        decision = _orchestrator.run(pre_context["data"], trace_id)

        # Post-processing hooks
        run_post_hooks(decision, pre_context, trace_id, start_time)

        processing_ms = int((time.time() - start_time) * 1000)

        return LoanDecisionResponse(
            trace_id=trace_id,
            verdict=decision.verdict.value,
            reasons=decision.reasons,
            recommendations=decision.recommendations,
            emi_to_income_ratio=decision.emi_to_income_ratio,
            dti_ratio=decision.dti_ratio,
            risk_band=decision.risk_band,
            explanation=decision.explanation,
            processing_time_ms=processing_ms,
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get("/api/stats")
async def get_stats():
    """Return aggregate statistics from the audit trail."""
    try:
        stats = audit_trail.get_stats()
        recent = audit_trail.get_recent_decisions(5)
        return {"stats": stats, "recent_decisions": recent}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
