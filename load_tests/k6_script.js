/**
 * K6 load test for the Loan Eligibility AI Agent REST API.
 *
 * Targets the FastAPI endpoint at api.py (port 8000).
 *
 * Run:
 *   k6 run load_tests/k6_script.js
 *
 * With env overrides:
 *   K6_TARGET_URL=http://localhost:8000 k6 run load_tests/k6_script.js
 *
 * With Grafana/InfluxDB output:
 *   k6 run --out influxdb=http://localhost:8086/k6 load_tests/k6_script.js
 *
 * With Prometheus remote-write output:
 *   K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9090/api/v1/write \
 *   k6 run --out=experimental-prometheus-rw load_tests/k6_script.js
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';
import { randomItem } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// ── Custom metrics ─────────────────────────────────────────────────────────────
const eligibleCount     = new Counter('loan_eligible_count');
const ineligibleCount   = new Counter('loan_ineligible_count');
const manualReviewCount = new Counter('loan_manual_review_count');
const errorRate         = new Rate('loan_api_error_rate');
const processingTime    = new Trend('loan_processing_ms', true);

// ── Test configuration ─────────────────────────────────────────────────────────
const TARGET = __ENV.K6_TARGET_URL || 'http://localhost:8000';

export const options = {
  stages: [
    { duration: '30s', target: 5  },  // ramp up
    { duration: '60s', target: 10 },  // steady load
    { duration: '30s', target: 20 },  // spike
    { duration: '30s', target: 10 },  // recover
    { duration: '30s', target: 0  },  // ramp down
  ],
  thresholds: {
    http_req_duration:      ['p(95)<30000'],  // 95th percentile under 30s (AI calls are slow)
    http_req_failed:        ['rate<0.05'],    // less than 5% hard failures
    loan_api_error_rate:    ['rate<0.10'],    // less than 10% business-level errors
  },
};

// ── Sample applicant profiles ──────────────────────────────────────────────────
const ELIGIBLE_PROFILES = [
  { name: 'Rahul Sharma',   age: 35, monthly_income: 100000, existing_emi: 10000, credit_score: 760, employment_type: 'Salaried',      loan_amount: 500000 },
  { name: 'Priya Patel',    age: 42, monthly_income: 80000,  existing_emi: 5000,  credit_score: 730, employment_type: 'Salaried',      loan_amount: 300000 },
  { name: 'Arun Kumar',     age: 38, monthly_income: 150000, existing_emi: 30000, credit_score: 750, employment_type: 'Self-Employed', loan_amount: 1000000 },
];

const BORDERLINE_PROFILES = [
  { name: 'Sunita Verma',   age: 45, monthly_income: 60000,  existing_emi: 15000, credit_score: 680, employment_type: 'Contract',      loan_amount: 400000 },
  { name: 'Deepak Nair',    age: 55, monthly_income: 70000,  existing_emi: 20000, credit_score: 705, employment_type: 'Self-Employed', loan_amount: 600000 },
];

const INELIGIBLE_PROFILES = [
  { name: 'Test User A',    age: 65, monthly_income: 20000,  existing_emi: 15000, credit_score: 550, employment_type: 'Unemployed',    loan_amount: 1000000 },
  { name: 'Test User B',    age: 30, monthly_income: 25000,  existing_emi: 20000, credit_score: 580, employment_type: 'Contract',      loan_amount: 800000 },
];

// ── Scenario weights: 60% eligible, 25% borderline, 15% ineligible ─────────────
function pickProfile() {
  const r = Math.random();
  if (r < 0.60) return randomItem(ELIGIBLE_PROFILES);
  if (r < 0.85) return randomItem(BORDERLINE_PROFILES);
  return randomItem(INELIGIBLE_PROFILES);
}

// ── Default scenario ───────────────────────────────────────────────────────────
export default function () {
  const profile = pickProfile();

  // Health check (5% of iterations)
  if (Math.random() < 0.05) {
    const health = http.get(`${TARGET}/health`);
    check(health, { 'health 200': (r) => r.status === 200 });
    sleep(1);
    return;
  }

  // Main evaluate endpoint
  const payload = JSON.stringify(profile);
  const params  = { headers: { 'Content-Type': 'application/json' } };

  const res = http.post(`${TARGET}/api/evaluate`, payload, params);

  const ok = check(res, {
    'status 200':     (r) => r.status === 200,
    'has verdict':    (r) => {
      try { return !!JSON.parse(r.body).verdict; } catch { return false; }
    },
    'under 30s':      (r) => r.timings.duration < 30000,
  });

  errorRate.add(!ok);

  if (res.status === 200) {
    const body = JSON.parse(res.body);
    const verdict = body.verdict || '';
    if (verdict === 'ELIGIBLE')       eligibleCount.add(1);
    else if (verdict === 'NOT_ELIGIBLE') ineligibleCount.add(1);
    else if (verdict === 'MANUAL_REVIEW') manualReviewCount.add(1);

    if (body.processing_time_ms) {
      processingTime.add(body.processing_time_ms);
    }
  }

  sleep(Math.random() * 2 + 1);  // 1–3s think time
}

// ── Teardown — print summary ───────────────────────────────────────────────────
export function handleSummary(data) {
  return {
    'load_tests/k6_results.json': JSON.stringify(data, null, 2),
    stdout: `
=== K6 Loan Agent Load Test Summary ===
HTTP Failures:     ${data.metrics.http_req_failed?.values?.rate?.toFixed(4) ?? 'n/a'}
p95 Duration:      ${data.metrics.http_req_duration?.values?.['p(95)']?.toFixed(0) ?? 'n/a'} ms
Eligible:          ${data.metrics.loan_eligible_count?.values?.count ?? 0}
Ineligible:        ${data.metrics.loan_ineligible_count?.values?.count ?? 0}
Manual Review:     ${data.metrics.loan_manual_review_count?.values?.count ?? 0}
Processing p95:    ${data.metrics.loan_processing_ms?.values?.['p(95)']?.toFixed(0) ?? 'n/a'} ms
`,
  };
}
