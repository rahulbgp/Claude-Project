"""
OrchestratorAgent: The central coordinator for the multi-agent pipeline.

Features:
- Autonomous planning: dynamically generates an execution plan based on applicant profile
- Multi-agent coordination: delegates to EligibilityCheckerAgent, RiskAssessorAgent, ExplainerAgent
- Self-healing: retries failed agents with exponential backoff; activates fallback if all retries fail
- Full tracing: logs each plan step and agent execution result
"""

import logging
import time
from typing import Optional

import anthropic

from agents.eligibility_checker import EligibilityCheckerAgent
from agents.explainer import EligibilityResult, ExplainerAgent, LoanDecision, Verdict
from agents.risk_assessor import RiskAssessorAgent
from config import ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, MAX_RETRIES, MODEL, RETRY_BASE_DELAY
from observability.tracer import tracer
from observability.metrics import record_agent_failure

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """
    The autonomous planning orchestrator.

    Creates a multi-step execution plan based on the applicant's profile,
    then delegates to specialist agents in sequence.

    Bonus Features:
    - Autonomous Planning: short-circuits the plan for obvious cases
    - Multi-Agent Collaboration: delegates to 3 specialist agents
    - Self-Healing: retries + fallback for every agent call
    """

    def __init__(self):
        # Initialize the Anthropic client (supports OpenRouter via base_url override)
        client_kwargs = {"api_key": ANTHROPIC_API_KEY}
        if ANTHROPIC_BASE_URL:
            client_kwargs["base_url"] = ANTHROPIC_BASE_URL
        self.client = anthropic.Anthropic(**client_kwargs)

        # Initialize specialist agents
        self.eligibility_agent = EligibilityCheckerAgent(self.client)
        self.risk_agent = RiskAssessorAgent(self.client)
        self.explainer_agent = ExplainerAgent(self.client)

    def run(self, applicant_data: dict, trace_id: str) -> LoanDecision:
        """
        Main entry point. Creates a plan and executes it.

        Returns a LoanDecision with verdict, reasons, and explanation.
        """
        with tracer.trace_span(trace_id, "orchestrator", "OrchestratorAgent"):
            # Step 1: Create the execution plan (autonomous planning)
            plan = self._create_plan(applicant_data)
            tracer.log_plan(trace_id, plan)

            # Step 2: Check for fast-path short-circuits
            shortcut = self._check_fast_path(applicant_data, trace_id)
            if shortcut is not None:
                return shortcut

            # Step 3: Run the main eligibility check (with retries)
            eligibility = self._run_with_retry(
                agent_name="EligibilityCheckerAgent",
                agent_fn=lambda: self.eligibility_agent.run(applicant_data, trace_id),
                fallback_fn=lambda: self.eligibility_agent._fallback_eligibility(applicant_data),
                trace_id=trace_id,
            )

            # Step 4: Run the risk assessment (with retries)
            risk_band = self._run_with_retry(
                agent_name="RiskAssessorAgent",
                agent_fn=lambda: self.risk_agent.run(applicant_data, eligibility.dti_ratio, trace_id),
                fallback_fn=lambda: self.risk_agent._fallback_risk_assessment(applicant_data, eligibility.dti_ratio),
                trace_id=trace_id,
            )

            # Step 5: Generate decision and explanation (with retries)
            decision = self._run_with_retry(
                agent_name="ExplainerAgent",
                agent_fn=lambda: self.explainer_agent.run(eligibility, risk_band, applicant_data, trace_id),
                fallback_fn=lambda: self._fallback_decision(eligibility, risk_band, applicant_data),
                trace_id=trace_id,
            )

            logger.info(
                "Orchestrator completed",
                extra={
                    "trace_id": trace_id,
                    "verdict": decision.verdict.value,
                    "risk_band": risk_band,
                },
            )
            return decision

    def _create_plan(self, applicant_data: dict) -> list:
        """
        Dynamically create an execution plan based on the applicant's profile.
        This is the 'Autonomous Planning' bonus feature.

        The plan is logged and returned so the tracer can record it.
        """
        credit_score = applicant_data.get("credit_score", 700)
        age = applicant_data.get("age", 35)
        employment_type = applicant_data.get("employment_type", "Salaried")

        plan = [{"name": "policy_fetch", "description": "Fetch current loan rules from MCP server"}]

        # If clearly a hard failure, plan for quick rejection path
        if age < 21 or age > 60:
            plan.append({"name": "age_check_only", "description": "Age out of range — fast rejection path"})
            return plan

        if employment_type == "Unemployed":
            plan.append({"name": "employment_check_only", "description": "Unemployed — fast rejection path"})
            return plan

        # Full pipeline for normal cases
        plan.extend([
            {"name": "eligibility_check", "description": "Run full eligibility check (credit, EMI-to-Income ratio, age, employment)"},
            {"name": "risk_assessment", "description": "Assess composite risk band"},
            {"name": "explanation_generation", "description": "Determine verdict and generate explanation"},
        ])

        # Add a note if it's likely a clear approval or clear rejection
        if credit_score >= 750 and employment_type == "Salaried":
            plan.append({"name": "fast_approval_likely", "description": "Strong profile — likely approval"})
        elif credit_score < 600:
            plan.append({"name": "high_rejection_risk", "description": "Low credit score — likely rejection"})

        return plan

    def _check_fast_path(
        self, applicant_data: dict, trace_id: str
    ) -> Optional[LoanDecision]:
        """
        Short-circuit for obvious hard rejections — skip expensive API calls.
        Returns a LoanDecision if fast-path applies, else None.
        """
        age = applicant_data.get("age", 35)
        employment_type = applicant_data.get("employment_type", "Salaried")

        if age < 21 or age > 60:
            logger.info(
                "Fast path: age disqualification",
                extra={"trace_id": trace_id, "age": age},
            )
            from agents.explainer import EligibilityResult
            eligibility = self.eligibility_agent._fallback_eligibility(applicant_data)
            return self.explainer_agent.run(eligibility, "CRITICAL", applicant_data, trace_id)

        if employment_type == "Unemployed":
            logger.info(
                "Fast path: unemployed disqualification",
                extra={"trace_id": trace_id, "employment_type": employment_type},
            )
            eligibility = self.eligibility_agent._fallback_eligibility(applicant_data)
            return self.explainer_agent.run(eligibility, "CRITICAL", applicant_data, trace_id)

        return None

    def _run_with_retry(
        self,
        agent_name: str,
        agent_fn,
        fallback_fn,
        trace_id: str,
    ):
        """
        Run an agent function with exponential backoff retries.
        If all retries fail, activate the fallback (self-healing).
        """
        last_error = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                return agent_fn()
            except Exception as e:
                last_error = e
                record_agent_failure(agent_name, type(e).__name__)

                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    tracer.log_agent_retry(trace_id, agent_name, attempt + 1, str(e))
                    logger.warning(
                        f"Agent retry {attempt + 1}/{MAX_RETRIES}",
                        extra={"trace_id": trace_id, "agent": agent_name, "delay_s": delay},
                    )
                    time.sleep(delay)

        # All retries exhausted → self-healing fallback
        tracer.log_fallback_activated(trace_id, agent_name, str(last_error))
        logger.warning(
            f"Activating fallback for {agent_name}",
            extra={"trace_id": trace_id, "agent": agent_name},
        )
        return fallback_fn()

    def _fallback_decision(
        self,
        eligibility: EligibilityResult,
        risk_band: str,
        applicant_data: dict,
    ) -> LoanDecision:
        """Pure rule-based fallback decision when all API calls fail."""
        from agents.explainer import ExplainerAgent, Verdict

        # Use the explainer's deterministic path (no API call)
        local_explainer = ExplainerAgent(self.client)
        verdict = local_explainer._determine_verdict(eligibility, risk_band)
        reasons = local_explainer._collect_reasons(eligibility, risk_band, applicant_data)
        recommendations = local_explainer._generate_recommendations(verdict, eligibility, applicant_data)

        monthly_income = applicant_data.get("monthly_income", 1)
        existing_emi = applicant_data.get("existing_emi", 0)
        emi_to_income_ratio = existing_emi / monthly_income if monthly_income > 0 else 0.0

        fallback_explanations = {
            Verdict.ELIGIBLE: "Congratulations! Your financial profile meets our loan eligibility criteria.",
            Verdict.NOT_ELIGIBLE: "Based on your financial profile, we are unable to approve this loan application at this time.",
            Verdict.MANUAL_REVIEW: "Your application has been flagged for manual review by our loan officers.",
        }

        return LoanDecision(
            verdict=verdict,
            reasons=reasons,
            recommendations=recommendations,
            emi_to_income_ratio=round(emi_to_income_ratio, 4),
            dti_ratio=round(eligibility.dti_ratio, 4),
            risk_band=risk_band,
            explanation=fallback_explanations.get(verdict, "Please contact our branch for more information."),
            model_used=f"{MODEL} (fallback)",
            tool_calls_count=0,
        )
