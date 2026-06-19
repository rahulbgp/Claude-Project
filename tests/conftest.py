"""
pytest fixtures shared across all test modules.
"""

import json
import os
import sys
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def eligible_applicant():
    """A clearly eligible applicant."""
    return {
        "name": "Rahul Sharma",
        "age": 35,
        "monthly_income": 100_000.0,
        "existing_emi": 10_000.0,
        "credit_score": 780,
        "employment_type": "Salaried",
        "loan_amount": 500_000.0,
    }


@pytest.fixture
def ineligible_applicant():
    """A clearly ineligible applicant (multiple fail conditions)."""
    return {
        "name": "Test Case",
        "age": 65,
        "monthly_income": 20_000.0,
        "existing_emi": 15_000.0,
        "credit_score": 550,
        "employment_type": "Unemployed",
        "loan_amount": 1_000_000.0,
    }


@pytest.fixture
def borderline_applicant():
    """A borderline applicant who should get MANUAL_REVIEW."""
    return {
        "name": "Priya Patel",
        "age": 40,
        "monthly_income": 50_000.0,
        "existing_emi": 10_000.0,
        "credit_score": 680,
        "employment_type": "Contract",
        "loan_amount": 300_000.0,
    }


@pytest.fixture
def young_applicant():
    """A young applicant at the age boundary."""
    return {
        "name": "Young Person",
        "age": 21,
        "monthly_income": 40_000.0,
        "existing_emi": 0.0,
        "credit_score": 710,
        "employment_type": "Salaried",
        "loan_amount": 200_000.0,
    }


@pytest.fixture
def mock_anthropic_message():
    """Factory for creating mock Anthropic message objects."""
    class MockContent:
        def __init__(self, type, text=None, id=None, name=None, input=None):
            self.type = type
            self.text = text
            self.id = id
            self.name = name
            self.input = input

    class MockMessage:
        def __init__(self, content, stop_reason="end_turn"):
            self.content = content
            self.stop_reason = stop_reason

    return {"MockContent": MockContent, "MockMessage": MockMessage}


@pytest.fixture
def tmp_db(tmp_path):
    """A temporary SQLite database path for testing."""
    return str(tmp_path / "test_audit.db")


@pytest.fixture
def tmp_log_dir(tmp_path):
    """A temporary directory for log files."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return str(log_dir)
