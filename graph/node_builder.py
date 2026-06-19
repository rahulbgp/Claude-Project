"""
Graph node builder for Neo4j — Step 18.

Converts each loan decision into a set of relational nodes and edges:

  (Applicant)-[:APPLIED_FOR]->(LoanApplication)
  (LoanApplication)-[:EVALUATED_BY]->(Decision)
  (Decision)-[:TRIGGERED_BY]->(PolicyRule)
  (Decision)-[:ASSESSED_AS]->(RiskBand)
  (Decision)-[:PROCESSED_BY]->(AgentStep)
  (AgentStep)-[:NEXT]->(AgentStep)

Falls back gracefully if Neo4j is not running or the neo4j package is absent.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4jpassword")

try:
    from neo4j import GraphDatabase
    _NEO4J_AVAILABLE = True
except ImportError:
    _NEO4J_AVAILABLE = False


class GraphNodeBuilder:
    """
    Writes loan decision graphs to Neo4j.

    Usage:
        builder = GraphNodeBuilder()
        builder.build(decision, pre_context, trace_id, agent_steps)
        builder.close()

    Or as a standalone function:
        build_decision_graph(decision, pre_context, trace_id)
    """

    def __init__(self) -> None:
        self._driver = None
        if not _NEO4J_AVAILABLE:
            logger.warning("neo4j package not installed — graph writes disabled")
            return
        try:
            self._driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            self._driver.verify_connectivity()
            self._ensure_constraints()
            logger.info("Connected to Neo4j at %s", NEO4J_URI)
        except Exception as exc:
            logger.warning("Neo4j not reachable (%s) — graph writes disabled", exc)
            self._driver = None

    def close(self) -> None:
        if self._driver:
            self._driver.close()

    def is_available(self) -> bool:
        return self._driver is not None

    def _ensure_constraints(self) -> None:
        with self._driver.session() as session:
            for label, prop in [
                ("Applicant",        "applicant_hash"),
                ("LoanApplication",  "trace_id"),
                ("Decision",         "trace_id"),
                ("PolicyRule",       "rule_name"),
                ("RiskBand",         "band"),
            ]:
                try:
                    session.run(
                        f"CREATE CONSTRAINT IF NOT EXISTS "
                        f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
                    )
                except Exception:
                    pass  # older Neo4j syntax; skip

    def build(
        self,
        decision,           # LoanDecision dataclass from pipeline/explainer.py
        pre_context: dict,
        trace_id: str,
        agent_steps: Optional[list] = None,
    ) -> bool:
        """
        Write the full decision graph. Returns True on success, False on failure.

        agent_steps is an optional ordered list of dicts:
            [{"agent": "EligibilityChecker", "duration_ms": 420, "status": "OK"}, ...]
        """
        if not self._driver:
            return False

        try:
            with self._driver.session() as session:
                session.execute_write(
                    self._write_graph,
                    decision, pre_context, trace_id, agent_steps or []
                )
            return True
        except Exception as exc:
            logger.error("Graph write failed for trace %s: %s", trace_id, exc)
            return False

    @staticmethod
    def _write_graph(tx, decision, pre_context, trace_id, agent_steps):
        data            = pre_context.get("data", {})
        applicant_hash  = pre_context.get("applicant_hash", "UNKNOWN")
        derived         = pre_context.get("derived", {})
        age_group       = derived.get("age_group", "unknown")

        # ── Applicant node ────────────────────────────────────────────────────
        tx.run("""
            MERGE (a:Applicant {applicant_hash: $applicant_hash})
            SET   a.employment_type = $employment_type,
                  a.age_group       = $age_group
        """, applicant_hash=applicant_hash,
             employment_type=data.get("employment_type", "Unknown"),
             age_group=age_group)

        # ── LoanApplication node ──────────────────────────────────────────────
        tx.run("""
            MERGE (app:LoanApplication {trace_id: $trace_id})
            SET   app.loan_amount   = $loan_amount,
                  app.credit_score  = $credit_score,
                  app.dti_ratio     = $dti_ratio,
                  app.existing_emi  = $existing_emi,
                  app.age           = $age
        """, trace_id=trace_id,
             loan_amount  = data.get("loan_amount",   0),
             credit_score = data.get("credit_score",  0),
             dti_ratio    = decision.dti_ratio,
             existing_emi = data.get("existing_emi",  0),
             age          = data.get("age",            0))

        # Applicant → Application edge
        tx.run("""
            MATCH (a:Applicant {applicant_hash: $applicant_hash}),
                  (app:LoanApplication {trace_id: $trace_id})
            MERGE (a)-[:APPLIED_FOR]->(app)
        """, applicant_hash=applicant_hash, trace_id=trace_id)

        # ── Decision node ─────────────────────────────────────────────────────
        tx.run("""
            MERGE (d:Decision {trace_id: $trace_id})
            SET   d.verdict             = $verdict,
                  d.risk_band           = $risk_band,
                  d.dti_ratio           = $dti_ratio,
                  d.model_used          = $model_used,
                  d.tool_calls_count    = $tool_calls_count
        """, trace_id=trace_id,
             verdict          = decision.verdict.value,
             risk_band        = decision.risk_band,
             dti_ratio        = decision.dti_ratio,
             model_used       = decision.model_used,
             tool_calls_count = decision.tool_calls_count)

        # Application → Decision edge
        tx.run("""
            MATCH (app:LoanApplication {trace_id: $trace_id}),
                  (d:Decision          {trace_id: $trace_id})
            MERGE (app)-[:EVALUATED_BY]->(d)
        """, trace_id=trace_id)

        # ── PolicyRule nodes (from decision reasons) ──────────────────────────
        rule_map = {
            "credit":     "credit_score_rule",
            "dti":        "dti_ratio_rule",
            "emi":        "dti_ratio_rule",
            "age":        "age_rule",
            "employ":     "employment_rule",
            "compliance": "compliance_rule",
        }
        seen_rules = set()
        for reason in decision.reasons:
            reason_lower = reason.lower()
            for keyword, rule_name in rule_map.items():
                if keyword in reason_lower and rule_name not in seen_rules:
                    seen_rules.add(rule_name)
                    passed = not any(w in reason_lower
                                     for w in ["not", "does not", "exceed", "below", "above", "outside"])
                    tx.run("""
                        MERGE (r:PolicyRule {rule_name: $rule_name})
                        WITH r
                        MATCH (d:Decision {trace_id: $trace_id})
                        MERGE (d)-[:TRIGGERED_BY {passed: $passed, reason: $reason}]->(r)
                    """, rule_name=rule_name, trace_id=trace_id, passed=passed, reason=reason)

        # ── RiskBand node ─────────────────────────────────────────────────────
        tx.run("""
            MERGE (rb:RiskBand {band: $band})
            WITH rb
            MATCH (d:Decision {trace_id: $trace_id})
            MERGE (d)-[:ASSESSED_AS]->(rb)
        """, band=decision.risk_band, trace_id=trace_id)

        # ── AgentStep nodes (optional) ────────────────────────────────────────
        if agent_steps:
            prev_step_id = None
            for i, step in enumerate(agent_steps):
                step_id = f"{trace_id}::{step['agent']}::{i}"
                tx.run("""
                    MERGE (s:AgentStep {step_id: $step_id})
                    SET   s.agent       = $agent,
                          s.duration_ms = $duration_ms,
                          s.status      = $status,
                          s.trace_id    = $trace_id
                    WITH s
                    MATCH (d:Decision {trace_id: $trace_id})
                    MERGE (d)-[:PROCESSED_BY]->(s)
                """, step_id=step_id,
                     agent=step.get("agent", "unknown"),
                     duration_ms=step.get("duration_ms", 0),
                     status=step.get("status", "OK"),
                     trace_id=trace_id)

                if prev_step_id:
                    tx.run("""
                        MATCH (prev:AgentStep {step_id: $prev_id}),
                              (curr:AgentStep {step_id: $curr_id})
                        MERGE (prev)-[:NEXT]->(curr)
                    """, prev_id=prev_step_id, curr_id=step_id)

                prev_step_id = step_id


# ── Module-level singleton (lazy) ─────────────────────────────────────────────

_builder: Optional[GraphNodeBuilder] = None


def _get_builder() -> GraphNodeBuilder:
    global _builder
    if _builder is None:
        _builder = GraphNodeBuilder()
    return _builder


def build_decision_graph(
    decision,
    pre_context: dict,
    trace_id: str,
    agent_steps: Optional[list] = None,
) -> bool:
    """
    Convenience function. Writes the loan decision to Neo4j using the module singleton.
    Returns True on success, False if Neo4j is unavailable.
    """
    return _get_builder().build(decision, pre_context, trace_id, agent_steps)
