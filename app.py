"""
Loan Eligibility AI Agent — Streamlit Application
===================================================
Main entry point for the web interface.

Run with:  streamlit run app.py

Features:
- Input form with 7 applicant fields
- AI-powered eligibility decision via multi-agent system
- Shows verdict (Eligible / Not Eligible / Needs Manual Review)
- Shows reasons, EMI-to-income ratio, recommendations
- Displays recent decisions from the audit trail
- Prometheus metrics at http://localhost:9090/metrics
"""

import os
import sys
import time

import streamlit as st

# ─── Page Config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="Loan Eligibility AI Agent",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Bootstrap imports ────────────────────────────────────────────────────────
# Add project root to path if needed
sys.path.insert(0, os.path.dirname(__file__))

from observability.json_logger import setup_logging
from observability.metrics import start_metrics_server
from observability import otel_tracer
from observability.tracer import tracer
from governance import audit_trail
from middleware.pre_hooks import run_pre_hooks
from middleware.post_hooks import run_post_hooks
from pipeline.orchestrator import OrchestratorAgent
from pipeline.explainer import Verdict
from config import (
    PROMETHEUS_PORT, MCP_LOAN_RULES_PORT, MCP_AUDIT_PORT,
    MCP_ORCHESTRATION_PORT, OTEL_ENDPOINT, OTEL_SERVICE_NAME, MODEL,
)

# ─── One-time Initialization ───────────────────────────────────────────────────
# Use session_state to track initialization so it only runs once per session
if "initialized" not in st.session_state:
    setup_logging()
    start_metrics_server(PROMETHEUS_PORT)
    otel_tracer.initialize(service_name=OTEL_SERVICE_NAME, otlp_endpoint=OTEL_ENDPOINT or None)
    audit_trail.initialize_db()

    # Start MCP servers in daemon threads
    try:
        from services.server import start_mcp_servers
        from services.orchestration_mcp import start_orchestration_mcp
        start_mcp_servers(MCP_LOAN_RULES_PORT, MCP_AUDIT_PORT)
        start_orchestration_mcp(MCP_ORCHESTRATION_PORT)
        time.sleep(0.5)  # Brief pause to let servers start
    except Exception as e:
        st.warning(f"MCP servers could not start: {e}. Using default policy values.")

    st.session_state["initialized"] = True
    st.session_state["orchestrator"] = OrchestratorAgent()

orchestrator: OrchestratorAgent = st.session_state["orchestrator"]


# ─── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .eligible-badge {
        background-color: #28a745; color: white; padding: 10px 20px;
        border-radius: 8px; font-size: 1.4rem; font-weight: bold; display: inline-block;
    }
    .not-eligible-badge {
        background-color: #dc3545; color: white; padding: 10px 20px;
        border-radius: 8px; font-size: 1.4rem; font-weight: bold; display: inline-block;
    }
    .manual-review-badge {
        background-color: #ffc107; color: #333; padding: 10px 20px;
        border-radius: 8px; font-size: 1.4rem; font-weight: bold; display: inline-block;
    }
    .metric-box {
        background-color: #f8f9fa; border-radius: 8px; padding: 15px;
        border-left: 4px solid #007bff;
    }
    .trace-id {
        font-family: monospace; font-size: 0.75rem; color: #666;
    }
</style>
""", unsafe_allow_html=True)


# ─── Header ────────────────────────────────────────────────────────────────────
st.title("🏦 Loan Eligibility AI Agent")
st.markdown(
    "**Multi-agent banking system** powered by Claude AI. "
    "Fill in the applicant details below to check loan eligibility."
)
st.divider()


# ─── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ System Status")
    st.success(f"Model: `{MODEL}`")
    st.info(f"Metrics: [Prometheus](http://localhost:{PROMETHEUS_PORT}/metrics)")
    st.info(f"LoanRulesMCP: `localhost:{MCP_LOAN_RULES_PORT}`")
    st.info(f"AuditMCP: `localhost:{MCP_AUDIT_PORT}`")

    st.divider()
    st.header("📊 Eligibility Rules")
    st.markdown("""
| Rule | Threshold |
|------|-----------|
| Credit Score | ≥ 700 |
| EMI-to-Income Ratio | ≤ 40% |
| Age Range | 21–60 years |
| Employment | Salaried (best) |
    """)

    st.divider()
    st.header("📖 How It Works")
    st.markdown("""
**Step 1 — Fill the form** with your loan details.

**Step 2 — The AI agent checks 4 rules:**

| Rule | What it checks | Pass condition |
|------|---------------|----------------|
| 🏦 Credit Score | Your credit history score | Must be **≥ 700** |
| 💰 EMI-to-Income | (Existing + New EMI) ÷ Income | Must be **≤ 40%** |
| 🎂 Age | Applicant age | Must be **21 – 60 years** |
| 💼 Employment | Job stability | Salaried is best |

**Step 3 — You get one of 3 outputs:**
- ✅ **Eligible** — All rules passed
- ❌ **Not Eligible** — One or more hard rules failed
- ⚠️ **Needs Manual Review** — Borderline case
    """)
    st.caption(
        "Outputs: **Eligible** / **Not Eligible** / **Needs Manual Review**"
    )


# ─── Input Form ────────────────────────────────────────────────────────────────
st.subheader("📋 Applicant Information")

with st.form("loan_application_form"):
    col1, col2, col3 = st.columns(3)

    with col1:
        applicant_name = st.text_input(
            "Full Name *",
            placeholder="e.g. Rahul Sharma",
            help="Applicant's full legal name",
        )
        age = st.number_input(
            "Age (years) *",
            min_value=18,
            max_value=80,
            value=35,
            step=1,
            help="Must be between 21 and 60 for eligibility",
        )
        employment_type = st.selectbox(
            "Employment Type *",
            options=["Salaried", "Self-Employed", "Contract", "Unemployed"],
            help="Salaried employees have the highest stability score",
        )

    with col2:
        monthly_income = st.number_input(
            "Monthly Income (₹) *",
            min_value=1000.0,
            max_value=10_000_000.0,
            value=75_000.0,
            step=1000.0,
            format="%.0f",
            help="Net monthly take-home income in rupees",
        )
        existing_emi = st.number_input(
            "Existing Monthly EMI (₹) *",
            min_value=0.0,
            max_value=10_000_000.0,
            value=10_000.0,
            step=500.0,
            format="%.0f",
            help="Total of all current loan EMI payments per month",
        )

    with col3:
        credit_score = st.number_input(
            "Credit Score *",
            min_value=300,
            max_value=900,
            value=720,
            step=1,
            help="CIBIL/Credit score (300–900). Score ≥ 700 is considered good.",
        )
        loan_amount = st.number_input(
            "Loan Amount Required (₹) *",
            min_value=10_000.0,
            max_value=50_000_000.0,
            value=500_000.0,
            step=10_000.0,
            format="%.0f",
            help="Total loan amount being requested",
        )

    # ── Loan Terms (needed to compute the new EMI accurately) ─────────────────
    st.markdown("**Loan Terms** — used to calculate your estimated new EMI")
    col4, col5 = st.columns(2)
    with col4:
        loan_tenure_months = st.selectbox(
            "Loan Tenure *",
            options=[12, 24, 36, 48, 60, 84, 120, 180, 240],
            index=4,           # default = 60 months (5 years)
            format_func=lambda m: f"{m} months ({m // 12} yr{'' if m // 12 == 1 else 's'})",
            help="How many months you want to repay the loan. Longer tenure = lower EMI but more interest.",
        )
    with col5:
        annual_interest_rate = st.number_input(
            "Annual Interest Rate (%) *",
            min_value=1.0,
            max_value=36.0,
            value=10.0,
            step=0.5,
            format="%.1f",
            help="The yearly interest rate offered by the bank. Typical range: 8–18%.",
        )

    st.divider()
    submitted = st.form_submit_button(
        "🔍 Check Loan Eligibility",
        use_container_width=True,
        type="primary",
    )


# ─── Process Application ───────────────────────────────────────────────────────
if submitted:
    # Basic UI validation before calling the agents
    if not applicant_name.strip():
        st.error("Please enter the applicant's name.")
        st.stop()

    # Compute estimated new loan EMI upfront so it's visible to the user
    import math
    monthly_rate = (annual_interest_rate / 100) / 12
    n = int(loan_tenure_months)
    if monthly_rate > 0:
        estimated_new_emi = (float(loan_amount) * monthly_rate * math.pow(1 + monthly_rate, n)
                             / (math.pow(1 + monthly_rate, n) - 1))
    else:
        estimated_new_emi = float(loan_amount) / n
    estimated_new_emi = round(estimated_new_emi, 2)

    applicant_data = {
        "name": applicant_name.strip(),
        "age": int(age),
        "monthly_income": float(monthly_income),
        "existing_emi": float(existing_emi),
        "credit_score": int(credit_score),
        "employment_type": employment_type,
        "loan_amount": float(loan_amount),
        # Loan terms — passed so agents use the correct EMI in DTI calculation
        "loan_tenure_months": int(loan_tenure_months),
        "annual_interest_rate": float(annual_interest_rate) / 100,  # store as decimal
        "estimated_new_emi": estimated_new_emi,
    }

    # Generate a unique trace ID for this request
    trace_id = tracer.generate_trace_id()
    start_time = time.time()

    with st.spinner("🤖 AI agents are analyzing your application..."):
        try:
            # Step 1: Pre-processing hooks (validate, sanitize, mask PII, enrich)
            pre_context = run_pre_hooks(
                applicant_data,
                trace_id=trace_id,
                session_id=st.session_state.get("session_id", "streamlit"),
            )

            # Step 2: Run the multi-agent orchestrator
            decision = orchestrator.run(pre_context["data"], trace_id)

            # Step 3: Post-processing hooks (audit, compliance, metrics, bias check)
            bias_flags = run_post_hooks(decision, pre_context, trace_id, start_time)

        except ValueError as e:
            st.error(f"❌ Input validation error: {e}")
            st.stop()
        except RuntimeError as e:
            st.error(f"⚠️ {e}")
            st.stop()
        except Exception as e:
            st.error(f"❌ An unexpected error occurred: {e}")
            st.stop()

    # ─── Results Display ──────────────────────────────────────────────────────
    st.divider()
    st.subheader("📊 Eligibility Decision")

    # Verdict badge
    verdict_val = decision.verdict.value
    if decision.verdict == Verdict.ELIGIBLE:
        st.markdown(
            '<div class="eligible-badge">✅ ELIGIBLE FOR LOAN</div>',
            unsafe_allow_html=True,
        )
        st.success("")
    elif decision.verdict == Verdict.NOT_ELIGIBLE:
        st.markdown(
            '<div class="not-eligible-badge">❌ NOT ELIGIBLE</div>',
            unsafe_allow_html=True,
        )
        st.error("")
    else:
        st.markdown(
            '<div class="manual-review-badge">⚠️ NEEDS MANUAL REVIEW</div>',
            unsafe_allow_html=True,
        )
        st.warning("")

    st.markdown("")  # Spacing

    # Show the computed EMI so the user can see exactly what was used
    st.markdown(
        f"**Estimated New Loan EMI:** ₹{estimated_new_emi:,.0f} / month "
        f"({int(loan_tenure_months)} months @ {annual_interest_rate:.1f}% p.a.)"
    )

    # ── Key metrics row ──────────────────────────────────────────────────────
    # EMI-to-income ratio = (existing EMI + new loan EMI) ÷ monthly income
    # Rule: must be ≤ 40%. This is the single most important number.
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        dti_pct = round(decision.dti_ratio * 100, 1)
        # Green delta when within limit, red when over limit
        dti_color = "normal" if decision.dti_ratio <= 0.40 else "inverse"
        st.metric(
            "EMI-to-Income Ratio",  # Requirement: Show EMI-to-income ratio
            f"{dti_pct}%",
            delta="Max allowed: 40%",
            delta_color=dti_color,
            help="(Existing EMI + New Loan EMI) ÷ Monthly Income. Must be ≤ 40%.",
        )
    with col2:
        # Existing EMI alone as a percentage of income (before new loan)
        emi_pct = round(decision.emi_to_income_ratio * 100, 1)
        st.metric(
            "Existing EMI / Income",
            f"{emi_pct}%",
            help="Your current EMI payments as a % of income, before this loan.",
        )
    with col3:
        st.metric("Risk Band", decision.risk_band,
                  help="LOW / MEDIUM / HIGH / CRITICAL — composite of credit, EMI-to-Income ratio, employment.")
    with col4:
        st.metric("Credit Score", applicant_data["credit_score"],
                  help="Minimum required: 700. Above 750 is Excellent.")

    st.divider()

    # Explanation
    st.subheader("💬 Explanation")
    st.info(decision.explanation)

    # Reasons
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📋 Decision Reasons")
        for reason in decision.reasons:
            if any(bad in reason.lower() for bad in ["does not", "exceed", "outside", "not"]):
                st.markdown(f"🔴 {reason}")
            else:
                st.markdown(f"🟢 {reason}")

    with col2:
        st.subheader("💡 Recommendations")
        for rec in decision.recommendations:
            st.markdown(f"→ {rec}")

    # Bias flags (only shown if any flagged)
    if bias_flags:
        with st.expander("⚠️ Fairness Monitor Flags", expanded=False):
            for flag in bias_flags:
                st.warning(f"**{flag.get('risk', 'LOW')} Risk**: {flag.get('message', '')}")

    # Technical details (collapsed by default)
    with st.expander("🔧 Technical Details", expanded=False):
        st.markdown(f"**Trace ID:** `{trace_id}`")
        st.markdown(f"**Model:** `{decision.model_used}`")
        st.markdown(f"**Tool Calls:** {decision.tool_calls_count}")
        processing_ms = int((time.time() - start_time) * 1000)
        st.markdown(f"**Processing Time:** {processing_ms}ms")

    st.divider()

# ─── Audit Log Table ───────────────────────────────────────────────────────────
st.subheader("📜 Recent Decisions (Audit Log)")
try:
    recent = audit_trail.get_recent_decisions(10)
    if recent:
        import pandas as pd

        df = pd.DataFrame(recent)
        # Rename columns for display
        display_cols = {
            "trace_id": "Trace ID",
            "timestamp": "Timestamp",
            "applicant_hash": "Applicant",
            "age": "Age",
            "employment_type": "Employment",
            "credit_score": "Credit Score",
            "verdict": "Verdict",
            "dti_ratio": "EMI-to-Income Ratio",
            "risk_band": "Risk",
            "processing_time_ms": "Time (ms)",
        }
        df = df[[c for c in display_cols if c in df.columns]]
        df = df.rename(columns={k: v for k, v in display_cols.items() if k in df.columns})

        # Shorten trace ID for display
        if "Trace ID" in df.columns:
            df["Trace ID"] = df["Trace ID"].str[:8] + "..."

        st.dataframe(df, use_container_width=True, height=300)

        # Aggregate stats
        stats = audit_trail.get_stats()
        if stats["total"] > 0:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Decisions", stats["total"])
            with col2:
                st.metric("Eligible", stats["eligible"])
            with col3:
                st.metric("Not Eligible", stats["not_eligible"])
            with col4:
                st.metric("Manual Review", stats["manual_review"])
    else:
        st.info("No decisions yet. Submit an application above to get started!")
except Exception as e:
    st.caption(f"(Audit log not available: {e})")

# ─── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "🏦 Loan Eligibility AI Agent | "
    f"Metrics: [localhost:{PROMETHEUS_PORT}](http://localhost:{PROMETHEUS_PORT}/metrics) | "
    "Logs: `logs/loan_agent.jsonl`"
)
