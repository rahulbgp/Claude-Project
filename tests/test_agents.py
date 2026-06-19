"""
Unit tests for agents with mocked Anthropic API calls.
Tests the agent logic without making real API calls.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from agents.explainer import EligibilityResult, ExplainerAgent, LoanDecision, Verdict
from agents.risk_assessor import RiskAssessorAgent
from agents.eligibility_checker import EligibilityCheckerAgent


def make_eligibility_result(**kwargs):
    defaults = {
        "age_ok": True, "credit_score_ok": True, "dti_ok": True,
        "employment_ok": True, "credit_score": 750, "dti_ratio": 0.25,
        "employment_score": 1.0, "raw_tool_results": {},
    }
    defaults.update(kwargs)
    return EligibilityResult(**defaults)


# ─── EligibilityCheckerAgent fallback ──────────────────────────────────────────

class TestEligibilityCheckerFallback:
    def test_fallback_eligible_applicant(self, eligible_applicant):
        client = MagicMock()
        agent = EligibilityCheckerAgent(client)
        result = agent._fallback_eligibility(eligible_applicant)
        assert result.age_ok is True
        assert result.credit_score_ok is True  # 780 >= 700
        assert result.employment_ok is True    # Salaried

    def test_fallback_ineligible_age(self):
        client = MagicMock()
        agent = EligibilityCheckerAgent(client)
        data = {"age": 65, "credit_score": 750, "monthly_income": 100000,
                "existing_emi": 10000, "employment_type": "Salaried", "loan_amount": 300000}
        result = agent._fallback_eligibility(data)
        assert result.age_ok is False

    def test_fallback_unemployed_fails_employment(self):
        client = MagicMock()
        agent = EligibilityCheckerAgent(client)
        data = {"age": 35, "credit_score": 750, "monthly_income": 0,
                "existing_emi": 0, "employment_type": "Unemployed", "loan_amount": 100000}
        result = agent._fallback_eligibility(data)
        assert result.employment_ok is False

    def test_fallback_high_dti_fails(self):
        client = MagicMock()
        agent = EligibilityCheckerAgent(client)
        # income 30000, existing emi 20000 + large loan → DTI >> 40%
        data = {"age": 35, "credit_score": 720, "monthly_income": 30000,
                "existing_emi": 20000, "employment_type": "Salaried", "loan_amount": 500000}
        result = agent._fallback_eligibility(data)
        assert result.dti_ok is False


# ─── RiskAssessorAgent fallback ────────────────────────────────────────────────

class TestRiskAssessorFallback:
    def test_excellent_profile_low_risk(self):
        client = MagicMock()
        agent = RiskAssessorAgent(client)
        data = {"credit_score": 800, "employment_type": "Salaried", "loan_amount": 100000}
        risk = agent._fallback_risk_assessment(data, 0.20)
        assert risk == "LOW"

    def test_unemployed_critical_risk(self):
        client = MagicMock()
        agent = RiskAssessorAgent(client)
        data = {"credit_score": 600, "employment_type": "Unemployed", "loan_amount": 100000}
        risk = agent._fallback_risk_assessment(data, 0.50)
        assert risk == "CRITICAL"

    def test_poor_credit_high_dti_critical_or_high(self):
        client = MagicMock()
        agent = RiskAssessorAgent(client)
        data = {"credit_score": 580, "employment_type": "Contract", "loan_amount": 500000}
        risk = agent._fallback_risk_assessment(data, 0.55)
        assert risk in ("HIGH", "CRITICAL")


# ─── ExplainerAgent with mocked API ────────────────────────────────────────────

class TestExplainerAgentMocked:
    def test_eligible_verdict_returned_correctly(self, eligible_applicant):
        client = MagicMock()
        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "Congratulations! Your application looks great."
        mock_response.content = [mock_content]
        client.messages.create.return_value = mock_response

        agent = ExplainerAgent(client)
        eligibility = make_eligibility_result()
        decision = agent.run(eligibility, "LOW", eligible_applicant, "test-trace-001")

        assert decision.verdict == Verdict.ELIGIBLE
        assert isinstance(decision.reasons, list)
        assert len(decision.reasons) > 0
        assert isinstance(decision.dti_ratio, float)

    def test_ineligible_age_returns_not_eligible(self):
        client = MagicMock()
        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "Unfortunately your application cannot be approved."
        mock_response.content = [mock_content]
        client.messages.create.return_value = mock_response

        agent = ExplainerAgent(client)
        eligibility = make_eligibility_result(age_ok=False)
        data = {"age": 65, "credit_score": 750, "monthly_income": 100000,
                "existing_emi": 10000, "employment_type": "Salaried", "loan_amount": 300000}
        decision = agent.run(eligibility, "HIGH", data, "test-trace-002")
        assert decision.verdict == Verdict.NOT_ELIGIBLE

    def test_api_failure_uses_fallback_explanation(self, eligible_applicant):
        client = MagicMock()
        client.messages.create.side_effect = Exception("API unavailable")

        agent = ExplainerAgent(client)
        eligibility = make_eligibility_result()
        decision = agent.run(eligibility, "LOW", eligible_applicant, "test-trace-003")

        # Should still return ELIGIBLE with a fallback explanation
        assert decision.verdict == Verdict.ELIGIBLE
        assert len(decision.explanation) > 0

    def test_emi_to_income_ratio_computed(self):
        client = MagicMock()
        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "All good."
        mock_response.content = [mock_content]
        client.messages.create.return_value = mock_response

        agent = ExplainerAgent(client)
        eligibility = make_eligibility_result()
        data = {"age": 35, "credit_score": 750, "monthly_income": 100000,
                "existing_emi": 20000, "employment_type": "Salaried", "loan_amount": 300000}
        decision = agent.run(eligibility, "LOW", data, "test-trace-004")
        # 20000 / 100000 = 0.20
        assert decision.emi_to_income_ratio == pytest.approx(0.20, rel=0.01)
