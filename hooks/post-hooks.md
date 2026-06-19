# Post-Processing Hooks

Run **after** the OrchestratorAgent returns a `LoanDecision`.
Implementation: `middleware/post_hooks.py` — entry point: `run_post_hooks(decision, pre_context, trace_id, start_time)`

Returns: `list` of bias flags found.

## Hook chain (executed in order)

### 1. record_audit_trail
Writes the loan decision to the immutable SQLite audit log (`audit.db`).
Fields recorded: `trace_id`, `applicant_hash`, `credit_score`, `monthly_income`, `existing_emi`, `loan_amount`, `age`, `employment_type`, `verdict`, `dti_ratio`, `risk_band`, `reasons`, `model_used`, `tool_calls_count`, `processing_time_ms`, `compliance_status`.
Implementation: `governance/audit_trail.py::write_decision()`

### 2. check_decision_bias
Runs bias analysis via `tools/bias_checker.py::aggregate_bias_check()`.
Checks for proxy-variable bias (age group, employment type correlated with rejection).
Returns a list of `bias_flags` dicts — each with `type`, `severity`, `note`.
Logs a warning if any flags are found.

### 3. emit_compliance_log
Writes a structured JSONL compliance record to `logs/compliance.jsonl`.
Filters reasons to financial-metric-based only (non-discriminatory subset).
Sets `bias_check_passed = True` if no HIGH-severity flags.
Regulatory framework: `RBI_FAIR_LENDING_2023`.
Implementation: `governance/compliance_logger.py::write_compliance_record()`

### 4. update_prometheus_metrics
Updates Prometheus counters and histograms via `observability/metrics.py::record_request()`.
Tracks: verdict counts, employment-type breakdown, request duration, DTI ratio distribution.

### 5. notify_manual_review
If `verdict == MANUAL_REVIEW`, appends a record to `logs/manual_review_queue.jsonl`.
Fields: `trace_id`, `applicant_hash`, `credit_score`, `employment_type`, `dti_ratio`, `risk_band`, `reasons`, `status: PENDING_REVIEW`.

## Error handling
Each hook runs independently inside a `try/except`. A failing hook logs an error but does not abort the chain — the response is always returned to the user.
