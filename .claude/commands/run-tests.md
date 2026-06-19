---
description: Run the test suite for the loan eligibility system
---

Run the tests for the Loan Eligibility AI Agent.

## Unit tests
```bash
pytest tests/ -v
```

Key test files:
- `tests/test_agents.py` — OrchestratorAgent, EligibilityCheckerAgent, RiskAssessorAgent, ExplainerAgent
- `tests/test_hooks.py` — pre_hooks and post_hooks chain
- `tests/test_tools.py` — loan_tools.py tool functions
- `tests/test_eligibility.py` — end-to-end eligibility scenarios
- `tests/test_governance.py` — audit trail and compliance logger

## Load tests (requires api.py running)
```bash
uvicorn api:app --host 0.0.0.0 --port 8000 &
locust -f tests/locustfile.py --host=http://localhost:8000 \
       --users=10 --spawn-rate=2 --run-time=60s --headless
```

## Run specific test file
```bash
pytest tests/test_agents.py -v
pytest tests/test_hooks.py -v -k "pre_hook"
```

Run whichever tests are relevant to $ARGUMENTS, or run the full suite if no arguments given.
