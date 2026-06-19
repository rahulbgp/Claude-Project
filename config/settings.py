"""
Central configuration for the Loan Eligibility AI Agent.
All thresholds, constants, and environment variables are defined here.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ─── Anthropic Model ───────────────────────────────────────────────────────────
MODEL = os.getenv("ANTHROPIC_MODEL", "anthropic/claude-opus-4-5")
MAX_TOKENS = 4096
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "")  # Optional: override for OpenRouter etc.

# ─── Loan Eligibility Rules ────────────────────────────────────────────────────
# Credit score thresholds
MIN_CREDIT_SCORE = 700        # Below this → likely not eligible
EXCELLENT_CREDIT_SCORE = 750  # Above this → excellent credit

# Debt-to-Income ratio limit
# Total EMI (existing + new) must not exceed 40% of monthly income
MAX_DTI_RATIO = 0.40          # 40% threshold
PREFERRED_DTI_RATIO = 0.30    # Preferred threshold (lower is better)

# Age eligibility range
MIN_AGE = 21
MAX_AGE = 60

# Employment stability scores (1.0 = most stable, 0.0 = not eligible)
EMPLOYMENT_STABILITY_SCORES = {
    "Salaried": 1.0,
    "Self-Employed": 0.75,
    "Contract": 0.60,
    "Unemployed": 0.0,
}

# Loan-to-income ratio: max loan amount relative to annual income
MAX_LOAN_TO_INCOME_RATIO = 10

# Default loan parameters for EMI estimation
DEFAULT_LOAN_TENURE_MONTHS = 60   # 5 years
DEFAULT_ANNUAL_INTEREST_RATE = 0.10  # 10% per annum

# ─── Agent Configuration ───────────────────────────────────────────────────────
MAX_RETRIES = 2        # Retry failed agent calls this many times
RETRY_BASE_DELAY = 1   # Base delay in seconds for exponential backoff

# ─── MCP Server Configuration ──────────────────────────────────────────────────
MCP_LOAN_RULES_PORT    = int(os.getenv("MCP_LOAN_RULES_PORT",    "8765"))
MCP_AUDIT_PORT         = int(os.getenv("MCP_AUDIT_PORT",         "8766"))
MCP_ORCHESTRATION_PORT = int(os.getenv("MCP_ORCHESTRATION_PORT", "8767"))
MCP_LOAN_RULES_URL     = f"http://localhost:{MCP_LOAN_RULES_PORT}/mcp"
MCP_AUDIT_URL          = f"http://localhost:{MCP_AUDIT_PORT}/mcp"
MCP_ORCHESTRATION_URL  = f"http://localhost:{MCP_ORCHESTRATION_PORT}/mcp"

# ─── OpenTelemetry ─────────────────────────────────────────────────────────────
OTEL_ENDPOINT    = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "loan-eligibility-agent")

# ─── Neo4j Graph Database ──────────────────────────────────────────────────────
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4jpassword")

# ─── Observability ─────────────────────────────────────────────────────────────
PROMETHEUS_PORT = int(os.getenv("PROMETHEUS_PORT", "9090"))
LOG_DIR = "logs"
LOG_FILE = f"{LOG_DIR}/loan_agent.jsonl"
COMPLIANCE_LOG_FILE = f"{LOG_DIR}/compliance.jsonl"

# ─── Governance ────────────────────────────────────────────────────────────────
AUDIT_DB_PATH = "audit.db"
REVIEW_QUEUE_FILE = f"{LOG_DIR}/manual_review_queue.jsonl"

# Regulatory framework label (used in compliance logs)
REGULATORY_FRAMEWORK = "RBI_FAIR_LENDING_2023"

# ─── FastAPI (for load testing endpoint) ───────────────────────────────────────
API_HOST = "0.0.0.0"
API_PORT = 8000

# ─── Rate Limiting ─────────────────────────────────────────────────────────────
MAX_REQUESTS_PER_MINUTE = 10  # Per session
