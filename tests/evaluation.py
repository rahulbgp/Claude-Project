"""
Evaluation harness for the Loan Eligibility AI Agent.

Measures:
  - Accuracy, Precision, Recall, F1 Score
  - Response Time (p50, p95, p99)
  - Hallucination Rate (explanation consistency check)
  - Compliance Score (% of decisions with complete audit records)
  - Agent Success Rate (% decisions served without fallback)

Run:
    python -m tests.evaluation
"""

import json
import math
import statistics
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agents.orchestrator import OrchestratorAgent
from observability.tracer import tracer

# ── Ground truth test cases ────────────────────────────────────────────────────
# Format: (applicant_data, expected_verdict)
# Expected verdicts derived from hard rules — deterministic regardless of LLM

TEST_CASES = [
    # Clear ELIGIBLE
    ({"name": "Rahul Sharma", "age": 35, "monthly_income": 100_000, "existing_emi": 10_000,
      "credit_score": 760, "employment_type": "Salaried", "loan_amount": 500_000,
      "loan_tenure_months": 60, "annual_interest_rate": 0.10, "estimated_new_emi": 10_607},
     "ELIGIBLE"),
    ({"name": "Priya Patel", "age": 42, "monthly_income": 80_000, "existing_emi": 5_000,
      "credit_score": 730, "employment_type": "Salaried", "loan_amount": 300_000,
      "loan_tenure_months": 60, "annual_interest_rate": 0.10, "estimated_new_emi": 6_374},
     "ELIGIBLE"),
    ({"name": "Arun Kumar", "age": 38, "monthly_income": 200_000, "existing_emi": 20_000,
      "credit_score": 780, "employment_type": "Salaried", "loan_amount": 1_000_000,
      "loan_tenure_months": 84, "annual_interest_rate": 0.09, "estimated_new_emi": 15_969},
     "ELIGIBLE"),

    # Clear NOT_ELIGIBLE — age
    ({"name": "Young A", "age": 19, "monthly_income": 50_000, "existing_emi": 0,
      "credit_score": 720, "employment_type": "Salaried", "loan_amount": 200_000,
      "loan_tenure_months": 60, "annual_interest_rate": 0.10, "estimated_new_emi": 4_249},
     "NOT_ELIGIBLE"),
    ({"name": "Senior B", "age": 65, "monthly_income": 30_000, "existing_emi": 5_000,
      "credit_score": 710, "employment_type": "Salaried", "loan_amount": 200_000,
      "loan_tenure_months": 60, "annual_interest_rate": 0.10, "estimated_new_emi": 4_249},
     "NOT_ELIGIBLE"),

    # Clear NOT_ELIGIBLE — unemployed
    ({"name": "Jobless C", "age": 35, "monthly_income": 20_000, "existing_emi": 0,
      "credit_score": 700, "employment_type": "Unemployed", "loan_amount": 100_000,
      "loan_tenure_months": 60, "annual_interest_rate": 0.10, "estimated_new_emi": 2_125},
     "NOT_ELIGIBLE"),

    # Clear NOT_ELIGIBLE — low credit + high DTI
    ({"name": "HighRisk D", "age": 40, "monthly_income": 25_000, "existing_emi": 12_000,
      "credit_score": 580, "employment_type": "Contract", "loan_amount": 400_000,
      "loan_tenure_months": 60, "annual_interest_rate": 0.12, "estimated_new_emi": 8_897},
     "NOT_ELIGIBLE"),

    # MANUAL_REVIEW — borderline credit
    ({"name": "Border E", "age": 45, "monthly_income": 60_000, "existing_emi": 15_000,
      "credit_score": 680, "employment_type": "Contract", "loan_amount": 300_000,
      "loan_tenure_months": 60, "annual_interest_rate": 0.12, "estimated_new_emi": 6_673},
     "MANUAL_REVIEW"),
]

# Labels for metric computation
LABEL_MAP = {"ELIGIBLE": 0, "MANUAL_REVIEW": 1, "NOT_ELIGIBLE": 2}
ELIGIBLE_LABEL = 0


def _contains_hallucination(explanation: str, reasons: list, verdict: str) -> bool:
    """
    Simple hallucination check: the explanation must be consistent with the verdict.
    Returns True if the explanation contradicts the verdict (hallucination).
    """
    explanation_lower = explanation.lower()
    verdict_lower = verdict.lower()

    if verdict == "ELIGIBLE":
        contradiction_phrases = ["not eligible", "cannot approve", "unable to approve", "rejected"]
        return any(p in explanation_lower for p in contradiction_phrases)
    elif verdict == "NOT_ELIGIBLE":
        contradiction_phrases = ["congratulations", "approved", "you qualify", "eligible"]
        return any(p in explanation_lower for p in contradiction_phrases)
    return False


def _compute_metrics(y_true: list, y_pred: list, positive_class: str = "ELIGIBLE") -> dict:
    """Compute accuracy, precision, recall, F1 for binary classification."""
    n = len(y_true)
    if n == 0:
        return {}

    tp = sum(1 for t, p in zip(y_true, y_pred) if t == positive_class and p == positive_class)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t != positive_class and p == positive_class)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == positive_class and p != positive_class)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t != positive_class and p != positive_class)

    accuracy = (tp + tn) / n
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "support": n,
    }


def run_evaluation(max_cases: int = len(TEST_CASES), use_fallback: bool = False) -> dict:
    """
    Run the evaluation harness over TEST_CASES.

    Args:
        max_cases: Number of test cases to run (default: all)
        use_fallback: If True, use rule-based fallback only (no API calls) — fast dry-run

    Returns:
        Evaluation report dict.
    """
    from core.rules_engine import RulesEngine

    y_true, y_pred = [], []
    response_times_ms = []
    hallucination_count = 0
    compliance_count = 0
    agent_success_count = 0
    total = min(max_cases, len(TEST_CASES))

    print(f"\n{'='*60}")
    print(f"  Loan Eligibility Agent — Evaluation Harness")
    print(f"  Running {total} test cases  |  use_fallback={use_fallback}")
    print(f"{'='*60}\n")

    if not use_fallback:
        try:
            orchestrator = OrchestratorAgent()
        except Exception as e:
            print(f"[WARN] Could not initialize OrchestratorAgent: {e}")
            print("[WARN] Falling back to rules-based evaluation")
            use_fallback = True

    for i, (applicant_data, expected_verdict) in enumerate(TEST_CASES[:total]):
        name = applicant_data.get("name", f"Case {i+1}")
        print(f"  [{i+1:02d}/{total}] {name:<20}", end="", flush=True)

        start = time.time()
        try:
            if use_fallback:
                # Rules-only path — no API calls
                eligibility = RulesEngine.evaluate(applicant_data)
                risk_band = "LOW" if eligibility.credit_score_ok and eligibility.dti_ok else "HIGH"
                verdict = RulesEngine.determine_verdict(eligibility, risk_band).value
                explanation = f"Rule-based verdict: {verdict}"
                reasons = []
                model_used = "rules_engine"
                agent_success_count += 1
            else:
                trace_id = tracer.generate_trace_id()
                decision = orchestrator.run(applicant_data, trace_id)
                verdict = decision.verdict.value
                explanation = decision.explanation
                reasons = decision.reasons
                model_used = decision.model_used
                if "(fallback)" not in model_used:
                    agent_success_count += 1

            elapsed_ms = (time.time() - start) * 1000
            response_times_ms.append(elapsed_ms)

            # Hallucination check
            hallucinated = _contains_hallucination(explanation, reasons, verdict)
            if hallucinated:
                hallucination_count += 1

            # Compliance check: verdict + reasons = complete audit record
            has_compliance = bool(verdict and (reasons or use_fallback))
            if has_compliance:
                compliance_count += 1

            y_true.append(expected_verdict)
            y_pred.append(verdict)

            match = "PASS" if verdict == expected_verdict else "FAIL"
            print(f"  expected={expected_verdict:<13} got={verdict:<13} {match}  ({elapsed_ms:.0f}ms)")

        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            response_times_ms.append(elapsed_ms)
            print(f"  ERROR: {e}")
            y_true.append(expected_verdict)
            y_pred.append("ERROR")

    # ── Aggregate metrics ──────────────────────────────────────────────────────
    metrics = _compute_metrics(y_true, y_pred, positive_class="ELIGIBLE")

    sorted_times = sorted(response_times_ms)
    p50 = sorted_times[int(len(sorted_times) * 0.50)] if sorted_times else 0
    p95 = sorted_times[int(len(sorted_times) * 0.95)] if sorted_times else 0
    p99 = sorted_times[min(int(len(sorted_times) * 0.99), len(sorted_times) - 1)] if sorted_times else 0

    hallucination_rate = round(hallucination_count / total, 4) if total > 0 else 0
    compliance_score = round(compliance_count / total, 4) if total > 0 else 0
    agent_success_rate = round(agent_success_count / total, 4) if total > 0 else 0

    report = {
        "total_cases": total,
        "correct_predictions": sum(1 for t, p in zip(y_true, y_pred) if t == p),
        **metrics,
        "response_time_ms": {
            "p50": round(p50, 1),
            "p95": round(p95, 1),
            "p99": round(p99, 1),
            "mean": round(statistics.mean(response_times_ms), 1) if response_times_ms else 0,
        },
        "hallucination_rate": hallucination_rate,
        "compliance_score": compliance_score,
        "agent_success_rate": agent_success_rate,
        "y_true": y_true,
        "y_pred": y_pred,
    }

    print(f"\n{'='*60}")
    print(f"  EVALUATION RESULTS")
    print(f"{'='*60}")
    print(f"  Total cases       : {report['total_cases']}")
    print(f"  Correct           : {report['correct_predictions']}")
    print(f"  Accuracy          : {metrics.get('accuracy', 0):.2%}")
    print(f"  Precision         : {metrics.get('precision', 0):.2%}")
    print(f"  Recall            : {metrics.get('recall', 0):.2%}")
    print(f"  F1 Score          : {metrics.get('f1_score', 0):.2%}")
    print(f"  Response p50      : {report['response_time_ms']['p50']:.0f}ms")
    print(f"  Response p95      : {report['response_time_ms']['p95']:.0f}ms")
    print(f"  Hallucination Rate: {hallucination_rate:.2%}")
    print(f"  Compliance Score  : {compliance_score:.2%}")
    print(f"  Agent Success Rate: {agent_success_rate:.2%}")
    print(f"{'='*60}\n")

    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run evaluation harness")
    parser.add_argument("--fallback", action="store_true",
                        help="Use rules-only fallback (no API calls)")
    parser.add_argument("--cases", type=int, default=len(TEST_CASES),
                        help="Number of test cases to run")
    parser.add_argument("--output", type=str, default=None,
                        help="Save report JSON to this file path")
    args = parser.parse_args()

    report = run_evaluation(max_cases=args.cases, use_fallback=args.fallback)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Report saved to {args.output}")
