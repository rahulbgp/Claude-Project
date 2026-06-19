# Coding Standards

## Python
- Python 3.11+; type hints on all public functions
- Dataclasses for structured data transfer between agents
- No global mutable state outside `config/settings.py`
- All agent classes take an `anthropic.Anthropic` client in `__init__`

## Project Layout
- `config/` — all settings, thresholds, and env vars
- `orchestrator/` — SDK delegation hub only; no business logic
- `core/` — domain models, rules engine, context manager
- `frontend/` — Streamlit UI; import from core/orchestrator only
- `rag/` — retrieval layer; pure functions, no side effects
- `mcp/` — HTTP MCP server; stateless tools only
- `observability/` — logging, metrics, tracing; no domain logic
- `governance/` — audit trail and compliance; append-only writes

## Error Handling
- Every agent method must have a `_fallback_*` pure rule-based path
- Use `_run_with_retry` in the orchestrator for all agent calls
- Never let an exception propagate to the UI without a user-friendly message

## Testing
- Unit tests in `tests/` — mock the Anthropic client
- Load tests in `load_tests/` using Locust
- All tests must pass before pushing to `main`

## Git
- Branch from `main`; PR required for all changes
- Commit messages: `<type>(<scope>): <summary>`
- Never commit `.env` or `settings.local.json`
