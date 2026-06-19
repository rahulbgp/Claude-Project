"""
Unit tests for governance components: audit trail and compliance logger.
"""

import json
import os
import pytest
import sqlite3


class TestAuditTrail:
    def test_initialize_creates_table(self, tmp_db, monkeypatch):
        monkeypatch.setattr("config.AUDIT_DB_PATH", tmp_db)
        import importlib
        import governance.audit_trail
        importlib.reload(governance.audit_trail)
        from governance.audit_trail import initialize_db

        initialize_db()
        conn = sqlite3.connect(tmp_db)
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        conn.close()
        assert any("audit_log" in str(t) for t in tables)

    def test_write_and_read_decision(self, tmp_db, monkeypatch):
        monkeypatch.setattr("config.AUDIT_DB_PATH", tmp_db)
        import importlib
        import governance.audit_trail
        importlib.reload(governance.audit_trail)
        from governance.audit_trail import initialize_db, write_decision, get_recent_decisions

        initialize_db()
        write_decision(
            trace_id="trace-001",
            applicant_hash="APPLICANT_ABCDEF",
            credit_score=750,
            monthly_income=100_000,
            existing_emi=10_000,
            loan_amount=500_000,
            age=35,
            employment_type="Salaried",
            verdict="ELIGIBLE",
            dti_ratio=0.25,
            risk_band="LOW",
            reasons=["Good credit score", "EMI-to-Income ratio within limits"],
            model_used="claude-opus-4-5",
        )

        decisions = get_recent_decisions(1)
        assert len(decisions) == 1
        assert decisions[0]["verdict"] == "ELIGIBLE"
        assert decisions[0]["trace_id"] == "trace-001"

    def test_duplicate_trace_id_ignored(self, tmp_db, monkeypatch):
        monkeypatch.setattr("config.AUDIT_DB_PATH", tmp_db)
        import importlib
        import governance.audit_trail
        importlib.reload(governance.audit_trail)
        from governance.audit_trail import initialize_db, write_decision, get_recent_decisions

        initialize_db()
        for _ in range(2):
            write_decision(
                trace_id="trace-dup",
                applicant_hash="APPLICANT_XYZ",
                credit_score=700,
                monthly_income=80_000,
                existing_emi=0,
                loan_amount=300_000,
                age=30,
                employment_type="Salaried",
                verdict="ELIGIBLE",
                dti_ratio=0.20,
                risk_band="LOW",
                reasons=[],
                model_used="test",
            )

        decisions = get_recent_decisions(10)
        dup_decisions = [d for d in decisions if d["trace_id"] == "trace-dup"]
        assert len(dup_decisions) == 1  # Duplicate should be ignored

    def test_get_stats_returns_correct_counts(self, tmp_db, monkeypatch):
        monkeypatch.setattr("config.AUDIT_DB_PATH", tmp_db)
        import importlib
        import governance.audit_trail
        importlib.reload(governance.audit_trail)
        from governance.audit_trail import initialize_db, write_decision, get_stats

        initialize_db()
        cases = [
            ("t1", "ELIGIBLE"),
            ("t2", "ELIGIBLE"),
            ("t3", "NOT_ELIGIBLE"),
            ("t4", "MANUAL_REVIEW"),
        ]
        for trace_id, verdict in cases:
            write_decision(
                trace_id=trace_id, applicant_hash="H", credit_score=700,
                monthly_income=80000, existing_emi=5000, loan_amount=300000,
                age=30, employment_type="Salaried", verdict=verdict,
                dti_ratio=0.20, risk_band="LOW", reasons=[], model_used="test",
            )

        stats = get_stats()
        assert stats["total"] == 4
        assert stats["eligible"] == 2
        assert stats["not_eligible"] == 1
        assert stats["manual_review"] == 1


class TestComplianceLogger:
    def test_compliance_record_written(self, tmp_log_dir, monkeypatch):
        compliance_file = os.path.join(tmp_log_dir, "compliance.jsonl")
        monkeypatch.setattr("config.COMPLIANCE_LOG_FILE", compliance_file)
        monkeypatch.setattr("config.LOG_DIR", tmp_log_dir)
        import importlib
        import governance.compliance_logger
        importlib.reload(governance.compliance_logger)
        from governance.compliance_logger import write_compliance_record

        write_compliance_record(
            trace_id="trace-c1",
            applicant_hash="APPLICANT_TEST",
            verdict="ELIGIBLE",
            reasons=["Good credit score"],
            non_discriminatory_reasons=["Credit score 750 meets requirements"],
            employment_type="Salaried",
            age_group="35-44",
            model_version="claude-opus-4-5",
            bias_check_passed=True,
            human_review_flag=False,
            dti_ratio=0.25,
        )

        with open(compliance_file) as f:
            record = json.loads(f.readline())

        assert record["trace_id"] == "trace-c1"
        assert record["decision"] == "ELIGIBLE"
        assert record["bias_check_passed"] is True
        assert "regulatory_framework" in record

    def test_get_age_group_classification(self):
        from governance.compliance_logger import get_age_group
        assert get_age_group(22) == "21-24"
        assert get_age_group(30) == "25-34"
        assert get_age_group(40) == "35-44"
        assert get_age_group(50) == "45-54"
        assert get_age_group(57) == "55-60"
