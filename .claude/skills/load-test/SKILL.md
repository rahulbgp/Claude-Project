# Skill: load-test

Run a Locust load test against the FastAPI endpoint.

## Usage
/load-test

## Steps
```bash
uvicorn api:app --host 0.0.0.0 --port 8000 &
locust -f load_tests/locustfile.py \
       --host=http://localhost:8000 \
       --users 10 --spawn-rate 2 --run-time 30s --headless \
       --html reports/load_test_report.html
```
