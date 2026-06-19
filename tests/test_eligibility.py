"""
Unit tests for the deterministic verdict logic in agents/explainer.py.
Tests the _determine_verdict() and _collect_reasons() methods without API calls.
"""

import pytest
from pipeline.explainer import EligibilityResult, ExplainerAgent, Verdict
from unittest.mock import MagicMock


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def explainer(mock_client):
    return ExplainerAgent(mock_client)


def make_eligibility(age_ok=True, credit_ok=True, dti_ok=True, emp_ok=True,
                     credit_score=750, dti_ratio=0.30, emp_score=1.0):
    return EligibilityResult(
        age_ok=age_ok,
        credit_score_ok=credit_ok,
        dti_ok=dti_ok,
        employment_ok=emp_ok,
        credit_score=credit_score,
        dti_ratio=dti_ratio,
        employment_score=emp_score,
        raw_tool_results={},
    )


# ─── Verdict Logic ─────────────────────────────────────────────────────────────

class TestDetermineVerdict:
    def test_all_pass_low_risk_is_eligible(self, explainer):
        eligibility = make_eligibility()
        verdict = explainer._determine_verdict(eligibility, "LOW")
        assert verdict == Verdict.ELIGIBLE

    def test_all_pass_medium_risk_is_eligible(self, explainer):
        eligibility = make_eligibility()
        verdict = explainer._determine_verdict(eligibility, "MEDIUM")
        assert verdict == Verdict.ELIGIBLE

    def test_age_fail_is_not_eligible(self, explainer):
        eligibility = make_eligibility(age_ok=False)
        verdict = explainer._determine_verdict(eligibility, "LOW")
        assert verdict == Verdict.NOT_ELIGIBLE

    def test_employment_fail_is_not_eligible(self, explainer):
        eligibility = make_eligibility(emp_ok=False)
        verdict = explainer._determine_verdict(eligibility, "LOW")
        assert verdict == Verdict.NOT_ELIGIBLE

    def test_critical_risk_is_not_eligible(self, explainer):
        eligibility = make_eligibility()
        verdict = explainer._determine_verdict(eligibility, "CRITICAL")
        assert verdict == Verdict.NOT_ELIGIBLE

    def test_high_risk_is_manual_review(self, explainer):
        eligibility = make_eligibility()
        verdict = explainer._determine_verdict(eligibility, "HIGH")
        assert verdict == Verdict.MANUAL_REVIEW

    def test_credit_fail_dti_ok_is_manual_review(self, explainer):
        eligibility = make_eligibility(credit_ok=False, dti_ok=True)
        verdict = explainer._determine_verdict(eligibility, "MEDIUM")
        assert verdict == Verdict.MANUAL_REVIEW

    def test_both_credit_and_dti_fail_is_not_eligible(self, explainer):
        eligibility = make_eligibility(credit_ok=False, dti_ok=False)
        verdict = explainer._determine_verdict(eligibility, "MEDIUM")
        assert verdict == Verdict.NOT_ELIGIBLE

    def test_dti_fail_credit_ok_is_manual_review(self, explainer):
        eligibility = make_eligibility(dti_ok=False, credit_ok=True)
        verdict = explainer._determine_verdict(eligibility, "MEDIUM")
        assert verdict == Verdict.MANUAL_REVIEW


# ─── Reasons Collection ────────────────────────────────────────────────────────

class TestCollectReasons:
    def test_reasons_include_credit_score_pass(self, explainer):
        eligibility = make_eligibility(credit_ok=True, credit_score=750)
        data = {"age": 35, "credit_score": 750, "employment_type": "Salaried",
                "monthly_income": 100000, "existing_emi": 10000, "loan_amount": 500000}
        reasons = explainer._collect_reasons(eligibility, "LOW", data)
        assert any("meets" in r.lower() for r in reasons)

    def test_reasons_include_credit_score_fail(self, explainer):
        eligibility = make_eligibility(credit_ok=False, credit_score=600)
        data = {"age": 35, "credit_score": 600, "employment_type": "Salaried",
                "monthly_income": 100000, "existing_emi": 10000, "loan_amount": 500000}
        reasons = explainer._collect_reasons(eligibility, "HIGH", data)
        assert any("below" in r.lower() or "does not meet" in r.lower() for r in reasons)

    def test_reasons_list_is_non_empty(self, explainer):
        eligibility = make_eligibility()
        data = {"age": 35, "credit_score": 750, "employment_type": "Salaried",
                "monthly_income": 100000, "existing_emi": 10000, "loan_amount": 500000}
        reasons = explainer._collect_reasons(eligibility, "LOW", data)
        assert len(reasons) >= 4


# ─── Recommendations ──────────────────────────────────────────────────────────

class TestGenerateRecommendations:
    def test_eligible_gets_positive_recommendation(self, explainer):
        eligibility = make_eligibility()
        recs = explainer._generate_recommendations(Verdict.ELIGIBLE, eligibility, {})
        assert any("proceed" in r.lower() or "qualify" in r.lower() or "congratulations" in r.lower() for r in recs)

    def test_not_eligible_low_credit_gets_credit_tip(self, explainer):
        eligibility = make_eligibility(credit_ok=False)
        recs = explainer._generate_recommendations(Verdict.NOT_ELIGIBLE, eligibility, {})
        assert any("credit" in r.lower() for r in recs)

    def test_not_eligible_high_dti_gets_emi_tip(self, explainer):
        eligibility = make_eligibility(dti_ok=False)
        recs = explainer._generate_recommendations(Verdict.NOT_ELIGIBLE, eligibility, {})
        assert any("emi" in r.lower() or "debt" in r.lower() or "loan" in r.lower() for r in recs)
