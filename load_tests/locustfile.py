"""
Locust load test for the Loan Eligibility AI Agent REST API.

The load test targets the FastAPI endpoint at api.py (not Streamlit directly).

Run:
    # Start the API server first:
    uvicorn api:app --host 0.0.0.0 --port 8000

    # Then run locust:
    locust -f tests/locustfile.py --host=http://localhost:8000

    # Or headless:
    locust -f tests/locustfile.py --host=http://localhost:8000 \
           --users 10 --spawn-rate 2 --run-time 60s --headless
"""

import random
from locust import HttpUser, task, between


# Sample applicant profiles for realistic load testing
ELIGIBLE_PROFILES = [
    {
        "name": "Rahul Sharma",
        "age": 35,
        "monthly_income": 100_000,
        "existing_emi": 10_000,
        "credit_score": 760,
        "employment_type": "Salaried",
        "loan_amount": 500_000,
    },
    {
        "name": "Priya Patel",
        "age": 42,
        "monthly_income": 80_000,
        "existing_emi": 5_000,
        "credit_score": 730,
        "employment_type": "Salaried",
        "loan_amount": 300_000,
    },
    {
        "name": "Arun Kumar",
        "age": 38,
        "monthly_income": 150_000,
        "existing_emi": 30_000,
        "credit_score": 750,
        "employment_type": "Self-Employed",
        "loan_amount": 1_000_000,
    },
]

BORDERLINE_PROFILES = [
    {
        "name": "Sunita Verma",
        "age": 45,
        "monthly_income": 60_000,
        "existing_emi": 15_000,
        "credit_score": 680,
        "employment_type": "Contract",
        "loan_amount": 400_000,
    },
    {
        "name": "Deepak Nair",
        "age": 55,
        "monthly_income": 70_000,
        "existing_emi": 20_000,
        "credit_score": 705,
        "employment_type": "Self-Employed",
        "loan_amount": 600_000,
    },
]

INELIGIBLE_PROFILES = [
    {
        "name": "Test User A",
        "age": 65,
        "monthly_income": 20_000,
        "existing_emi": 15_000,
        "credit_score": 550,
        "employment_type": "Unemployed",
        "loan_amount": 1_000_000,
    },
    {
        "name": "Test User B",
        "age": 30,
        "monthly_income": 25_000,
        "existing_emi": 20_000,
        "credit_score": 580,
        "employment_type": "Contract",
        "loan_amount": 800_000,
    },
]


class LoanApplicantUser(HttpUser):
    """
    Simulates a mix of loan applicants hitting the API:
    - 60% eligible profiles (happy path)
    - 25% borderline profiles (manual review path)
    - 15% ineligible profiles (rejection path)
    """

    # Wait 1-3 seconds between requests (realistic user think time)
    wait_time = between(1, 3)

    @task(6)
    def submit_eligible_application(self):
        """Submit an application that should be approved."""
        profile = random.choice(ELIGIBLE_PROFILES)
        with self.client.post(
            "/api/evaluate",
            json=profile,
            name="/api/evaluate [eligible]",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("verdict") not in ("ELIGIBLE", "MANUAL_REVIEW"):
                    response.failure(f"Unexpected verdict: {data.get('verdict')}")
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(2)
    def submit_borderline_application(self):
        """Submit a borderline application (may get manual review)."""
        profile = random.choice(BORDERLINE_PROFILES)
        with self.client.post(
            "/api/evaluate",
            json=profile,
            name="/api/evaluate [borderline]",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(1)
    def submit_ineligible_application(self):
        """Submit an application that should be rejected."""
        profile = random.choice(INELIGIBLE_PROFILES)
        with self.client.post(
            "/api/evaluate",
            json=profile,
            name="/api/evaluate [ineligible]",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(1)
    def health_check(self):
        """Periodic health check."""
        self.client.get("/health", name="/health")

    @task(1)
    def get_stats(self):
        """Read audit stats."""
        self.client.get("/api/stats", name="/api/stats")
