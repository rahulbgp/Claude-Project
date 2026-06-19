"""
MCP (Model Context Protocol) servers for the Loan Eligibility AI Agent.

Two servers:
  - LoanRulesMCP on port 8765: exposes loan policy rules as MCP tools
  - AuditMCP on port 8766: exposes audit decision logging as MCP tools

Each server runs in a daemon thread started by app.py.
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Track whether servers have been started
_servers_started = False
_start_lock = threading.Lock()


def _run_loan_rules_server(port: int) -> None:
    """Run the LoanRulesMCP server (used for loan policy rules)."""
    try:
        from mcp.server.fastmcp import FastMCP
        import uvicorn

        mcp = FastMCP("LoanRulesMCP")
        from services.policy_db import POLICIES

        @mcp.tool()
        def get_credit_score_threshold() -> dict:
            """Get the minimum credit score required for loan approval."""
            return POLICIES["credit_score"]

        @mcp.tool()
        def get_dti_policy() -> dict:
            """Get the EMI-to-Income ratio policy limits."""
            return POLICIES["dti"]

        @mcp.tool()
        def get_age_policy() -> dict:
            """Get the eligible age range for loan applicants."""
            return POLICIES["age"]

        @mcp.tool()
        def get_employment_policy() -> dict:
            """Get employment type stability scores."""
            return POLICIES["employment"]

        @mcp.tool()
        def get_loan_products() -> dict:
            """Get available loan products and their default terms."""
            return POLICIES["loan_products"]

        @mcp.tool()
        def get_compliance_rules() -> dict:
            """Get regulatory compliance requirements."""
            return POLICIES["compliance"]

        logger.info(f"Starting LoanRulesMCP server on port {port}")
        uvicorn.run(mcp.streamable_http_app(), host="0.0.0.0", port=port, log_level="warning")

    except Exception as e:
        logger.error(f"LoanRulesMCP server failed to start: {e}")


def _run_audit_server(port: int) -> None:
    """Run the AuditMCP server (used for audit decision logging via MCP)."""
    try:
        from mcp.server.fastmcp import FastMCP
        import uvicorn
        from config import AUDIT_DB_PATH

        mcp = FastMCP("AuditMCP")

        @mcp.tool()
        def log_decision(
            trace_id: str,
            verdict: str,
            reasons: list,
            dti_ratio: float,
        ) -> dict:
            """Log a loan decision to the audit trail via MCP."""
            try:
                conn = sqlite3.connect(AUDIT_DB_PATH)
                conn.execute("""
                    INSERT OR IGNORE INTO audit_log
                    (trace_id, timestamp, applicant_hash, verdict, dti_ratio,
                     reasons, model_used, compliance_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trace_id,
                    datetime.now(timezone.utc).isoformat(),
                    "MCP_LOG",
                    verdict,
                    dti_ratio,
                    json.dumps(reasons),
                    "AuditMCP",
                    "COMPLIANT",
                ))
                conn.commit()
                conn.close()
                return {"status": "logged", "trace_id": trace_id}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        @mcp.tool()
        def get_decision_history(limit: int = 10) -> dict:
            """Retrieve recent loan decisions from the audit trail."""
            try:
                conn = sqlite3.connect(AUDIT_DB_PATH)
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT trace_id, timestamp, verdict, dti_ratio
                    FROM audit_log ORDER BY id DESC LIMIT ?
                """, (limit,)).fetchall()
                conn.close()
                return {"decisions": [dict(r) for r in rows], "count": len(rows)}
            except Exception as e:
                return {"decisions": [], "count": 0, "error": str(e)}

        logger.info(f"Starting AuditMCP server on port {port}")
        uvicorn.run(mcp.streamable_http_app(), host="0.0.0.0", port=port, log_level="warning")

    except Exception as e:
        logger.error(f"AuditMCP server failed to start: {e}")


def start_mcp_servers(loan_rules_port: int = 8765, audit_port: int = 8766) -> None:
    """
    Start both MCP servers in daemon threads.
    Safe to call multiple times — only starts once.
    """
    global _servers_started
    with _start_lock:
        if _servers_started:
            return

        # LoanRulesMCP thread
        loan_thread = threading.Thread(
            target=_run_loan_rules_server,
            args=(loan_rules_port,),
            daemon=True,
            name="LoanRulesMCP",
        )
        loan_thread.start()

        # AuditMCP thread
        audit_thread = threading.Thread(
            target=_run_audit_server,
            args=(audit_port,),
            daemon=True,
            name="AuditMCP",
        )
        audit_thread.start()

        _servers_started = True
        logger.info(f"MCP servers starting: LoanRulesMCP:{loan_rules_port}, AuditMCP:{audit_port}")
