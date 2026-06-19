# Pre-Processing Hooks

Run **before** the OrchestratorAgent processes the applicant data.
Implementation: `middleware/pre_hooks.py` — entry point: `run_pre_hooks(applicant_data, trace_id, session_id)`

## Hook chain (executed in order)

### 1. validate_input
Type-checks and range-validates every input field.
- `name`: non-empty string
- `age`: number, 18–80
- `monthly_income`: positive number
- `existing_emi`: zero or positive
- `credit_score`: 300–900
- `employment_type`: one of Salaried | Self-Employed | Contract | Unemployed
- `loan_amount`: positive number

Raises `ValueError` with a clear message listing all failures if any field is invalid.

### 2. sanitize_input
Normalises and clamps all values:
- Strips whitespace from strings; caps `name` at 100 chars
- Converts `age` to `int`, monetary fields to `float` (2 d.p.)
- Preserves loan terms: `loan_tenure_months`, `annual_interest_rate`, `estimated_new_emi`

### 3. mask_pii
Replaces the applicant's name with a SHA-256 hash (`APPLICANT_<12-char-hex>`) in the logging context.
- `context["applicant_hash"]` — used in all audit/compliance records
- `context["original_name"]` — preserved for display in the UI
- The name in `context["data"]` is **not** replaced (shown to user)

### 4. enrich_input
Adds derived fields to `context["derived"]`:
- `annual_income` = monthly_income × 12
- `loan_to_income_ratio` = loan_amount / annual_income
- `existing_emi_to_income_ratio` = existing_emi / monthly_income
- `age_group`: 21-24 | 25-34 | 35-44 | 45-54 | 55-60

### 5. check_rate_limit
In-memory per-session rate limiting: max 10 requests/minute (`MAX_REQUESTS_PER_MINUTE` from config).
Raises `RuntimeError` if exceeded.

## Return value
Returns a `context` dict with keys: `data`, `trace_id`, `session_id`, `applicant_hash`, `original_name`, `derived`.
