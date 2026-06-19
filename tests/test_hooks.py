"""
Unit tests for pre- and post-processing hooks.
"""

import json
import os
import pytest


# ─── Pre-Hook Tests ────────────────────────────────────────────────────────────

class TestValidateInput:
    def test_valid_input_passes(self, eligible_applicant):
        from middleware.pre_hooks import validate_input
        context = {"data": eligible_applicant, "trace_id": "test"}
        result = validate_input(context)
        assert result["data"]["name"] == eligible_applicant["name"]

    def test_empty_name_raises(self, eligible_applicant):
        from middleware.pre_hooks import validate_input
        data = {**eligible_applicant, "name": ""}
        with pytest.raises(ValueError, match="Name"):
            validate_input({"data": data, "trace_id": "test"})

    def test_negative_income_raises(self, eligible_applicant):
        from middleware.pre_hooks import validate_input
        data = {**eligible_applicant, "monthly_income": -1000}
        with pytest.raises(ValueError, match="income"):
            validate_input({"data": data, "trace_id": "test"})

    def test_invalid_age_raises(self, eligible_applicant):
        from middleware.pre_hooks import validate_input
        data = {**eligible_applicant, "age": 17}
        with pytest.raises(ValueError, match="Age"):
            validate_input({"data": data, "trace_id": "test"})

    def test_invalid_credit_score_raises(self, eligible_applicant):
        from middleware.pre_hooks import validate_input
        data = {**eligible_applicant, "credit_score": 100}
        with pytest.raises(ValueError, match="Credit"):
            validate_input({"data": data, "trace_id": "test"})

    def test_invalid_employment_type_raises(self, eligible_applicant):
        from middleware.pre_hooks import validate_input
        data = {**eligible_applicant, "employment_type": "Gig Worker"}
        with pytest.raises(ValueError, match="Employment"):
            validate_input({"data": data, "trace_id": "test"})


class TestSanitizeInput:
    def test_name_whitespace_stripped(self, eligible_applicant):
        from middleware.pre_hooks import sanitize_input
        data = {**eligible_applicant, "name": "  Rahul  "}
        context = {"data": data}
        result = sanitize_input(context)
        assert result["data"]["name"] == "Rahul"

    def test_numeric_types_converted(self, eligible_applicant):
        from middleware.pre_hooks import sanitize_input
        data = {**eligible_applicant, "age": "35", "credit_score": "720"}
        context = {"data": data}
        result = sanitize_input(context)
        assert isinstance(result["data"]["age"], int)
        assert isinstance(result["data"]["credit_score"], int)


class TestMaskPii:
    def test_applicant_hash_created(self, eligible_applicant):
        from middleware.pre_hooks import mask_pii
        context = {"data": eligible_applicant.copy(), "trace_id": "test"}
        result = mask_pii(context)
        assert "applicant_hash" in result
        assert result["applicant_hash"].startswith("APPLICANT_")

    def test_original_name_preserved(self, eligible_applicant):
        from middleware.pre_hooks import mask_pii
        context = {"data": eligible_applicant.copy(), "trace_id": "test"}
        result = mask_pii(context)
        assert result["original_name"] == eligible_applicant["name"]
        # Name should still be in data for UI display
        assert result["data"]["name"] == eligible_applicant["name"]

    def test_hash_is_deterministic(self, eligible_applicant):
        from middleware.pre_hooks import mask_pii
        context1 = {"data": eligible_applicant.copy(), "trace_id": "test"}
        context2 = {"data": eligible_applicant.copy(), "trace_id": "test"}
        r1 = mask_pii(context1)
        r2 = mask_pii(context2)
        assert r1["applicant_hash"] == r2["applicant_hash"]


class TestEnrichInput:
    def test_derived_fields_added(self, eligible_applicant):
        from middleware.pre_hooks import enrich_input
        context = {"data": eligible_applicant.copy(), "trace_id": "test"}
        result = enrich_input(context)
        assert "derived" in result
        assert "age_group" in result["derived"]
        assert "loan_to_income_ratio" in result["derived"]

    def test_age_group_correct(self, eligible_applicant):
        from middleware.pre_hooks import enrich_input
        data = {**eligible_applicant, "age": 22}
        context = {"data": data, "trace_id": "test"}
        result = enrich_input(context)
        assert result["derived"]["age_group"] == "21-24"

    def test_loan_to_income_ratio_correct(self, eligible_applicant):
        from middleware.pre_hooks import enrich_input
        # Income: 100000/month, annual = 1200000, loan = 500000 → ratio = 0.4167
        data = {**eligible_applicant, "monthly_income": 100000, "loan_amount": 500000}
        context = {"data": data, "trace_id": "test"}
        result = enrich_input(context)
        expected = 500000 / (100000 * 12)
        assert result["derived"]["loan_to_income_ratio"] == pytest.approx(expected, rel=0.01)


class TestRunPreHooks:
    def test_full_pipeline_succeeds(self, eligible_applicant):
        from middleware.pre_hooks import run_pre_hooks
        ctx = run_pre_hooks(eligible_applicant, trace_id="test123")
        assert "data" in ctx
        assert "applicant_hash" in ctx
        assert "derived" in ctx

    def test_invalid_input_raises(self):
        from middleware.pre_hooks import run_pre_hooks
        with pytest.raises(ValueError):
            run_pre_hooks(
                {"name": "", "age": 35, "monthly_income": 50000, "existing_emi": 0,
                 "credit_score": 720, "employment_type": "Salaried", "loan_amount": 200000},
                trace_id="test",
            )
