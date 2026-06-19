"""
Unit tests for all 8 loan tools in tools/loan_tools.py
These test the pure Python logic without any API calls.
"""

import json
import pytest
from tools.loan_tools import (
    check_credit_score,
    check_dti_ratio,
    check_age_eligibility,
    check_employment_stability,
    compute_loan_emi,
    assess_risk_band,
    check_bias_indicators,
    execute_tool,
)


# ─── check_credit_score ─────────────────────────────────────────────────────────

class TestCheckCreditScore:
    def test_excellent_score_passes(self):
        result = json.loads(check_credit_score(780))
        assert result["passed"] is True
        assert result["category"] == "Excellent"

    def test_good_score_passes(self):
        result = json.loads(check_credit_score(720))
        assert result["passed"] is True
        assert result["category"] == "Good"

    def test_fair_score_fails(self):
        result = json.loads(check_credit_score(670))
        assert result["passed"] is False
        assert result["category"] == "Fair"

    def test_poor_score_fails(self):
        result = json.loads(check_credit_score(580))
        assert result["passed"] is False
        assert result["category"] == "Poor"

    def test_exactly_at_minimum_passes(self):
        result = json.loads(check_credit_score(700))
        assert result["passed"] is True

    def test_one_below_minimum_fails(self):
        result = json.loads(check_credit_score(699))
        assert result["passed"] is False


# ─── check_dti_ratio ────────────────────────────────────────────────────────────

class TestCheckDtiRatio:
    def test_dti_within_limit_passes(self):
        # (10000 + 15000) / 100000 = 25% — well within 40%
        result = json.loads(check_dti_ratio(100_000, 10_000, 15_000))
        assert result["passed"] is True
        assert result["dti_ratio_percent"] == pytest.approx(25.0, rel=0.01)

    def test_dti_exactly_at_limit_passes(self):
        # 40000 / 100000 = 40% — exactly at limit
        result = json.loads(check_dti_ratio(100_000, 20_000, 20_000))
        assert result["passed"] is True

    def test_dti_exceeds_limit_fails(self):
        # 45000 / 100000 = 45% — over limit
        result = json.loads(check_dti_ratio(100_000, 25_000, 20_000))
        assert result["passed"] is False

    def test_zero_income_returns_error(self):
        result = json.loads(check_dti_ratio(0, 10_000, 5_000))
        assert result["passed"] is False

    def test_zero_existing_emi_uses_only_loan_emi(self):
        # 20000 / 100000 = 20%
        result = json.loads(check_dti_ratio(100_000, 0, 20_000))
        assert result["passed"] is True
        assert result["total_emi"] == 20_000


# ─── check_age_eligibility ──────────────────────────────────────────────────────

class TestCheckAgeEligibility:
    def test_age_21_passes(self):
        result = json.loads(check_age_eligibility(21))
        assert result["passed"] is True

    def test_age_60_passes(self):
        result = json.loads(check_age_eligibility(60))
        assert result["passed"] is True

    def test_age_20_fails(self):
        result = json.loads(check_age_eligibility(20))
        assert result["passed"] is False

    def test_age_61_fails(self):
        result = json.loads(check_age_eligibility(61))
        assert result["passed"] is False

    def test_middle_age_passes(self):
        result = json.loads(check_age_eligibility(40))
        assert result["passed"] is True


# ─── check_employment_stability ────────────────────────────────────────────────

class TestCheckEmploymentStability:
    def test_salaried_passes_with_highest_score(self):
        result = json.loads(check_employment_stability("Salaried"))
        assert result["passed"] is True
        assert result["stability_score"] == 1.0

    def test_self_employed_passes(self):
        result = json.loads(check_employment_stability("Self-Employed"))
        assert result["passed"] is True
        assert result["stability_score"] == 0.75

    def test_contract_passes(self):
        result = json.loads(check_employment_stability("Contract"))
        assert result["passed"] is True
        assert result["stability_score"] == 0.60

    def test_unemployed_fails(self):
        result = json.loads(check_employment_stability("Unemployed"))
        assert result["passed"] is False
        assert result["stability_score"] == 0.0

    def test_unknown_type_fails(self):
        result = json.loads(check_employment_stability("Freelancer"))
        assert result["passed"] is False


# ─── compute_loan_emi ──────────────────────────────────────────────────────────

class TestComputeLoanEmi:
    def test_standard_loan_emi_calculation(self):
        # 500000 at 10% for 60 months
        result = json.loads(compute_loan_emi(500_000, 0.10, 60))
        # Standard EMI should be approximately 10624
        assert 10_000 < result["monthly_emi"] < 11_500
        assert result["loan_amount"] == 500_000

    def test_zero_interest_rate(self):
        result = json.loads(compute_loan_emi(120_000, 0.0, 12))
        assert result["monthly_emi"] == pytest.approx(10_000, rel=0.01)

    def test_negative_loan_amount_returns_error(self):
        result = json.loads(compute_loan_emi(-100))
        assert "error" in result

    def test_total_payment_greater_than_loan(self):
        result = json.loads(compute_loan_emi(500_000, 0.10, 60))
        assert result["total_payment"] > result["loan_amount"]
        assert result["total_interest"] > 0


# ─── assess_risk_band ──────────────────────────────────────────────────────────

class TestAssessRiskBand:
    def test_excellent_profile_low_risk(self):
        result = json.loads(assess_risk_band(800, 0.20, 1.0))
        assert result["risk_band"] == "LOW"

    def test_poor_profile_critical_risk(self):
        result = json.loads(assess_risk_band(500, 0.80, 0.0))
        assert result["risk_band"] == "CRITICAL"

    def test_medium_profile_medium_risk(self):
        result = json.loads(assess_risk_band(720, 0.35, 0.75))
        assert result["risk_band"] in ("LOW", "MEDIUM")

    def test_borderline_credit_high_dti(self):
        result = json.loads(assess_risk_band(650, 0.45, 0.60))
        assert result["risk_band"] in ("HIGH", "CRITICAL")


# ─── check_bias_indicators ─────────────────────────────────────────────────────

class TestCheckBiasIndicators:
    def test_no_flags_for_normal_rejection(self):
        result = json.loads(check_bias_indicators(30, "Salaried", "NOT_ELIGIBLE"))
        # Salaried, middle-aged — no special bias flag
        assert result["bias_risk"] == "LOW"

    def test_young_rejection_gets_flagged(self):
        result = json.loads(check_bias_indicators(22, "Salaried", "NOT_ELIGIBLE"))
        assert len(result["bias_flags"]) > 0

    def test_eligible_no_flags(self):
        result = json.loads(check_bias_indicators(35, "Salaried", "ELIGIBLE"))
        assert result["bias_check_passed"] is True


# ─── execute_tool dispatcher ────────────────────────────────────────────────────

class TestExecuteTool:
    def test_dispatches_credit_score_tool(self):
        result = json.loads(execute_tool("check_credit_score", {"credit_score": 750}))
        assert "passed" in result

    def test_unknown_tool_returns_error(self):
        result = json.loads(execute_tool("nonexistent_tool", {}))
        assert "error" in result

    def test_bad_arguments_returns_error(self):
        result = json.loads(execute_tool("check_credit_score", {"wrong_param": "x"}))
        assert "error" in result
