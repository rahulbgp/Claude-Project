---
description: Run a full loan eligibility check for an applicant through the multi-agent pipeline
---

Run a complete loan eligibility evaluation using the multi-agent pipeline.

## Usage
```
/check-eligibility <name> <age> <monthly_income> <existing_emi> <credit_score> <employment_type> <loan_amount>
```

Or pass as JSON: `/check-eligibility {"name": "...", "age": 30, ...}`

## What this does
1. Runs `hooks/pre_hooks.py::run_pre_hooks()` — validate, sanitize, mask PII, enrich, rate-limit
2. Calls `agents/orchestrator.py::OrchestratorAgent.run()` — full multi-agent pipeline
3. Runs `hooks/post_hooks.py::run_post_hooks()` — audit trail, compliance log, metrics, bias check, review queue
4. Returns the `LoanDecision` with verdict, reasons, risk band, and explanation

## Example
```python
from agents.orchestrator import OrchestratorAgent
from hooks.pre_hooks import run_pre_hooks
from hooks.post_hooks import run_post_hooks
import uuid, time

applicant = {
    "name": "$ARGUMENTS",
    "age": 35,
    "monthly_income": 80000,
    "existing_emi": 10000,
    "credit_score": 720,
    "employment_type": "Salaried",
    "loan_amount": 500000,
}

trace_id = str(uuid.uuid4())
start = time.time()
pre_ctx = run_pre_hooks(applicant, trace_id)
orchestrator = OrchestratorAgent()
decision = orchestrator.run(pre_ctx["data"], trace_id)
run_post_hooks(decision, pre_ctx, trace_id, start)
print(decision)
```

Parse any arguments provided after the command as the applicant data, fill in defaults for missing fields, then execute the pipeline above.
