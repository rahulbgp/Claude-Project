# Testing & Evaluation Report

## Loan Eligibility AI Agent

**Date:** 2026-06-19  

---

## 1. Test Coverage Overview

| Test File | Tests | Coverage Area |
|-----------|-------|--------------|
| `test_tools.py` | 26 | All 8 loan tool functions (unit) |
| `test_eligibility.py` | 15 | Verdict logic, reasons, recommendations |
| `test_agents.py` | 12 | Agent fallback paths (mocked API) |
| `test_hooks.py` | 16 | All 5 pre-hooks + full chain |
| `test_governance.py` | 9 | Audit trail + compliance logger |
| **Total** | **78** | **All core components** |

---

## 2. Unit Tests

### `test_tools.py` — Tool Function Tests

**Purpose:** Verify each `@tool` function returns the correct pass/fail result and data fields.

Key test cases:
- Credit score exactly at boundary (700) → PASS
- Credit score 1 below boundary (699) → FAIL
- EMI-to-Income ratio exactly at 40% → PASS
- EMI-to-Income ratio 40.01% → FAIL
- Zero income → error returned
- Age at lower bound (21) and upper bound (60) → both PASS
- Age 20 and 61 → both FAIL
- All 4 employment types produce correct stability scores
- EMI formula: 500k @ 10% / 60 months → ~₹10,624
- Risk band: excellent profile → LOW; poor profile → CRITICAL
- Bias indicator: young + rejection → flag created

### `test_eligibility.py` — Eligibility Logic Tests

**Purpose:** Test deterministic verdict rules without any API calls.

Key scenarios tested:
| Scenario | Expected Verdict |
|----------|-----------------|
| All criteria pass + LOW risk | ELIGIBLE |
| All criteria pass + MEDIUM risk | ELIGIBLE |
| Age fail | NOT_ELIGIBLE |
| Employment fail (Unemployed) | NOT_ELIGIBLE |
| CRITICAL risk band | NOT_ELIGIBLE |
| HIGH risk band | MANUAL_REVIEW |
| Credit fail + EMI-to-Income pass | MANUAL_REVIEW |
| Both credit + EMI-to-Income fail | NOT_ELIGIBLE |
| Credit pass + EMI-to-Income fail | MANUAL_REVIEW |

### `test_agents.py` — Agent Tests (Mocked API)

**Purpose:** Test agent fallback logic and result handling with mocked Anthropic responses.

- Eligible applicant through EligibilityChecker fallback → all checks pass
- Age 65 through fallback → `age_ok=False`
- Unemployed through fallback → `employment_ok=False`
- High EMI-to-Income ratio through fallback → `dti_ok=False`
- Excellent profile through RiskAssessor fallback → LOW
- Unemployed through RiskAssessor fallback → CRITICAL
- ExplainerAgent with mock API → correct Verdict enum returned
- ExplainerAgent API failure → fallback explanation used (no crash)
- EMI-to-income ratio calculation verified: 20000/100000 = 0.20

### `test_hooks.py` — Pre-Hook Tests

**Purpose:** Verify input validation, sanitization, PII masking, and enrichment.

Key assertions:
- Empty name raises ValueError
- Negative income raises ValueError
- Age < 18 raises ValueError
- Invalid credit score raises ValueError
- Unknown employment type raises ValueError
- Name whitespace stripped in sanitize
- applicant_hash starts with "APPLICANT_"
- Original name preserved in context (not lost)
- Hash is deterministic (same input → same hash)
- Age 22 → age_group "21-24"
- Loan/income ratio computed correctly

### `test_governance.py` — Governance Tests

**Purpose:** Verify audit trail and compliance logging work correctly.

Key assertions:
- `initialize_db()` creates `audit_log` table
- Written decision readable back with correct fields
- Duplicate `trace_id` silently ignored (immutability)
- Stats counts correct after multiple writes
- Compliance record written with all required fields
- `regulatory_framework` field present
- `bias_check_passed` field correct

---

## 3. Running the Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-mock

# Run all unit tests
pytest tests/ -v

# Run specific test file
pytest tests/test_tools.py -v

# Run with coverage report
pip install pytest-cov
pytest tests/ --cov=. --cov-report=html
```

---

## 4. Load Testing

### Setup

```bash
# Start the FastAPI endpoint (terminal 1)
uvicorn api:app --host 0.0.0.0 --port 8000

# Run Locust load test (terminal 2)
locust -f tests/locustfile.py \
       --host=http://localhost:8000 \
       --users=10 \
       --spawn-rate=2 \
       --run-time=60s \
       --headless
```

### Load Test Scenarios

| Task | Weight | Description |
|------|--------|-------------|
| submit_eligible_application | 60% | Standard eligible applicant |
| submit_borderline_application | 20% | Borderline / manual review |
| submit_ineligible_application | 10% | Clear rejection |
| health_check | 5% | GET /health |
| get_stats | 5% | GET /api/stats |

### Expected Load Test Results

| Metric | Target | Notes |
|--------|--------|-------|
| Response time (p50) | < 5s | Includes Claude API latency |
| Response time (p95) | < 15s | Within API rate limits |
| Error rate | < 1% | Exc. anthropic rate limits |
| Requests/sec | 2-5 | Limited by Claude API rate limits |

*Note: Real-world throughput depends heavily on Claude API rate limits for your account tier.*

---

## 5. Evaluation Methodology

### Accuracy Testing

Manual test cases verified against expected verdicts:

| Test Case | Credit | EMI-to-Income | Age | Employment | Expected | Result |
|-----------|--------|---------------|-----|-----------|----------|--------|
| Perfect applicant | 800 | 20% | 35 | Salaried | ELIGIBLE | ✅ |
| Too old | 800 | 20% | 65 | Salaried | NOT_ELIGIBLE | ✅ |
| Too young | 800 | 20% | 19 | Salaried | NOT_ELIGIBLE | ✅ |
| Low credit | 580 | 20% | 35 | Salaried | NOT_ELIGIBLE | ✅ |
| High EMI-to-Income | 750 | 55% | 35 | Salaried | NOT_ELIGIBLE | ✅ |
| Unemployed | 750 | 20% | 35 | Unemployed | NOT_ELIGIBLE | ✅ |
| Borderline credit | 680 | 35% | 40 | Contract | MANUAL_REVIEW | ✅ |
| Fair credit + ok ratio | 670 | 30% | 35 | Salaried | MANUAL_REVIEW | ✅ |

### Explainability Evaluation

Each decision includes:
- 5+ specific reasons (financial metric-based)
- Plain-English explanation (2-4 sentences)
- Actionable recommendations (2-3 items)
- Quantified EMI-to-Income ratio percentage
- Risk band classification

---

## 6. Self-Healing Tests

To test self-healing behavior:

```python
# In a test, patch the Anthropic client to always raise:
from unittest.mock import patch, MagicMock
import anthropic

with patch.object(anthropic.Anthropic, 'messages') as mock_create:
    mock_create.create.side_effect = Exception("API unavailable")
    # The orchestrator should still return a valid LoanDecision
    # via the fallback rule-based path
    result = orchestrator.run(eligible_applicant, "test-trace")
    assert result.verdict is not None
```

The self-healing test confirms that the system produces valid decisions even with complete API failure.
