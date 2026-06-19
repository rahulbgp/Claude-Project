"""
OrchestrationMCP — generic, reusable Model Context Protocol server.

Provides domain-agnostic tools for multi-agent orchestration:
  - Agent registry  (register / list / get agent metadata)
  - Workflow state  (create / update / query workflow runs)
  - Config store    (set / get / delete runtime configuration)
  - Event bus       (publish / subscribe / pop events)

Runs on port 8767 in a daemon thread started by start_orchestration_mcp().
Claude Code can connect via .mcp.json entry:
  { "orchestration": { "type": "http", "url": "http://localhost:8767/mcp" } }
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_ORCH_DB = "orchestration.db"
_started = False
_start_lock = threading.Lock()


def _init_db() -> None:
    conn = sqlite3.connect(_ORCH_DB)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agent_registry (
            agent_id   TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            role       TEXT NOT NULL,
            capabilities TEXT NOT NULL,  -- JSON array
            endpoint   TEXT,
            registered_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workflow_runs (
            run_id     TEXT PRIMARY KEY,
            workflow   TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'RUNNING',
            context    TEXT NOT NULL DEFAULT '{}',  -- JSON object
            steps      TEXT NOT NULL DEFAULT '[]',  -- JSON array
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS config_store (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS event_bus (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            topic      TEXT NOT NULL,
            payload    TEXT NOT NULL,
            producer   TEXT NOT NULL DEFAULT 'system',
            consumed   INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def _run_orchestration_server(port: int) -> None:
    try:
        from mcp.server.fastmcp import FastMCP
        import uvicorn

        _init_db()
        mcp = FastMCP("OrchestrationMCP")

        # ── Agent Registry ────────────────────────────────────────────────────

        @mcp.tool()
        def register_agent(
            agent_id: str,
            name: str,
            role: str,
            capabilities: list,
            endpoint: str = "",
        ) -> dict:
            """Register an agent in the orchestration registry."""
            conn = sqlite3.connect(_ORCH_DB)
            conn.execute("""
                INSERT OR REPLACE INTO agent_registry
                (agent_id, name, role, capabilities, endpoint, registered_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (agent_id, name, role, json.dumps(capabilities), endpoint,
                  datetime.now(timezone.utc).isoformat()))
            conn.commit()
            conn.close()
            return {"status": "registered", "agent_id": agent_id}

        @mcp.tool()
        def list_agents(role_filter: str = "") -> dict:
            """List all registered agents, optionally filtered by role."""
            conn = sqlite3.connect(_ORCH_DB)
            conn.row_factory = sqlite3.Row
            if role_filter:
                rows = conn.execute(
                    "SELECT * FROM agent_registry WHERE role = ?", (role_filter,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM agent_registry").fetchall()
            conn.close()
            agents = []
            for r in rows:
                a = dict(r)
                a["capabilities"] = json.loads(a["capabilities"])
                agents.append(a)
            return {"agents": agents, "count": len(agents)}

        @mcp.tool()
        def get_agent(agent_id: str) -> dict:
            """Get metadata for a specific agent by ID."""
            conn = sqlite3.connect(_ORCH_DB)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM agent_registry WHERE agent_id = ?", (agent_id,)
            ).fetchone()
            conn.close()
            if not row:
                return {"error": f"Agent '{agent_id}' not found"}
            a = dict(row)
            a["capabilities"] = json.loads(a["capabilities"])
            return a

        # ── Workflow State ─────────────────────────────────────────────────────

        @mcp.tool()
        def create_workflow_run(run_id: str, workflow: str, context: dict = None) -> dict:
            """Create a new workflow run with initial context."""
            now = datetime.now(timezone.utc).isoformat()
            conn = sqlite3.connect(_ORCH_DB)
            conn.execute("""
                INSERT OR IGNORE INTO workflow_runs
                (run_id, workflow, status, context, steps, created_at, updated_at)
                VALUES (?, ?, 'RUNNING', ?, '[]', ?, ?)
            """, (run_id, workflow, json.dumps(context or {}), now, now))
            conn.commit()
            conn.close()
            return {"status": "created", "run_id": run_id}

        @mcp.tool()
        def update_workflow_step(
            run_id: str,
            step_name: str,
            step_status: str,
            step_result: dict = None,
        ) -> dict:
            """Append a completed step to the workflow run log."""
            conn = sqlite3.connect(_ORCH_DB)
            row = conn.execute(
                "SELECT steps FROM workflow_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if not row:
                conn.close()
                return {"error": f"Run '{run_id}' not found"}
            steps = json.loads(row[0])
            steps.append({
                "step": step_name,
                "status": step_status,
                "result": step_result or {},
                "at": datetime.now(timezone.utc).isoformat(),
            })
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("""
                UPDATE workflow_runs SET steps = ?, updated_at = ? WHERE run_id = ?
            """, (json.dumps(steps), now, run_id))
            conn.commit()
            conn.close()
            return {"status": "updated", "run_id": run_id, "steps_count": len(steps)}

        @mcp.tool()
        def complete_workflow_run(run_id: str, final_status: str = "COMPLETED") -> dict:
            """Mark a workflow run as completed (or FAILED / CANCELLED)."""
            now = datetime.now(timezone.utc).isoformat()
            conn = sqlite3.connect(_ORCH_DB)
            conn.execute("""
                UPDATE workflow_runs SET status = ?, updated_at = ? WHERE run_id = ?
            """, (final_status, now, run_id))
            conn.commit()
            conn.close()
            return {"status": final_status, "run_id": run_id}

        @mcp.tool()
        def get_workflow_run(run_id: str) -> dict:
            """Get the full state of a workflow run."""
            conn = sqlite3.connect(_ORCH_DB)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM workflow_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            conn.close()
            if not row:
                return {"error": f"Run '{run_id}' not found"}
            r = dict(row)
            r["context"] = json.loads(r["context"])
            r["steps"] = json.loads(r["steps"])
            return r

        @mcp.tool()
        def list_workflow_runs(workflow_filter: str = "", status_filter: str = "", limit: int = 20) -> dict:
            """List recent workflow runs, with optional workflow name and status filters."""
            conn = sqlite3.connect(_ORCH_DB)
            conn.row_factory = sqlite3.Row
            query = "SELECT run_id, workflow, status, created_at, updated_at FROM workflow_runs"
            params = []
            clauses = []
            if workflow_filter:
                clauses.append("workflow = ?")
                params.append(workflow_filter)
            if status_filter:
                clauses.append("status = ?")
                params.append(status_filter)
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            conn.close()
            return {"runs": [dict(r) for r in rows], "count": len(rows)}

        # ── Config Store ──────────────────────────────────────────────────────

        @mcp.tool()
        def set_config(key: str, value: Any) -> dict:
            """Set a runtime configuration value (any JSON-serialisable type)."""
            conn = sqlite3.connect(_ORCH_DB)
            conn.execute("""
                INSERT OR REPLACE INTO config_store (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, json.dumps(value), datetime.now(timezone.utc).isoformat()))
            conn.commit()
            conn.close()
            return {"status": "set", "key": key}

        @mcp.tool()
        def get_config(key: str, default: Any = None) -> dict:
            """Get a runtime configuration value by key."""
            conn = sqlite3.connect(_ORCH_DB)
            row = conn.execute("SELECT value FROM config_store WHERE key = ?", (key,)).fetchone()
            conn.close()
            if not row:
                return {"key": key, "value": default, "found": False}
            return {"key": key, "value": json.loads(row[0]), "found": True}

        @mcp.tool()
        def delete_config(key: str) -> dict:
            """Delete a runtime configuration key."""
            conn = sqlite3.connect(_ORCH_DB)
            conn.execute("DELETE FROM config_store WHERE key = ?", (key,))
            conn.commit()
            conn.close()
            return {"status": "deleted", "key": key}

        @mcp.tool()
        def list_config_keys() -> dict:
            """List all configuration keys currently stored."""
            conn = sqlite3.connect(_ORCH_DB)
            rows = conn.execute("SELECT key, updated_at FROM config_store ORDER BY key").fetchall()
            conn.close()
            return {"keys": [{"key": r[0], "updated_at": r[1]} for r in rows]}

        # ── Event Bus ─────────────────────────────────────────────────────────

        @mcp.tool()
        def publish_event(topic: str, payload: dict, producer: str = "system") -> dict:
            """Publish an event to the event bus."""
            conn = sqlite3.connect(_ORCH_DB)
            cursor = conn.execute("""
                INSERT INTO event_bus (topic, payload, producer, consumed, created_at)
                VALUES (?, ?, ?, 0, ?)
            """, (topic, json.dumps(payload), producer, datetime.now(timezone.utc).isoformat()))
            event_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return {"status": "published", "event_id": event_id, "topic": topic}

        @mcp.tool()
        def consume_events(topic: str, limit: int = 10) -> dict:
            """Consume unconsumed events from a topic (marks them as consumed)."""
            conn = sqlite3.connect(_ORCH_DB)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT id, topic, payload, producer, created_at
                FROM event_bus
                WHERE topic = ? AND consumed = 0
                ORDER BY id ASC LIMIT ?
            """, (topic, limit)).fetchall()
            ids = [r["id"] for r in rows]
            if ids:
                conn.execute(
                    f"UPDATE event_bus SET consumed = 1 WHERE id IN ({','.join('?' * len(ids))})",
                    ids,
                )
                conn.commit()
            conn.close()
            events = []
            for r in rows:
                e = dict(r)
                e["payload"] = json.loads(e["payload"])
                events.append(e)
            return {"events": events, "count": len(events)}

        @mcp.tool()
        def peek_events(topic: str, limit: int = 10) -> dict:
            """Peek at events on a topic without consuming them."""
            conn = sqlite3.connect(_ORCH_DB)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT id, topic, payload, producer, consumed, created_at
                FROM event_bus WHERE topic = ?
                ORDER BY id DESC LIMIT ?
            """, (topic, limit)).fetchall()
            conn.close()
            events = []
            for r in rows:
                e = dict(r)
                e["payload"] = json.loads(e["payload"])
                events.append(e)
            return {"events": events, "count": len(events)}

        logger.info(f"Starting OrchestrationMCP server on port {port}")
        uvicorn.run(mcp.streamable_http_app(), host="0.0.0.0", port=port, log_level="warning")

    except Exception as e:
        logger.error(f"OrchestrationMCP server failed to start: {e}")


def start_orchestration_mcp(port: int = 8767) -> None:
    """Start the OrchestrationMCP server in a daemon thread. Safe to call multiple times."""
    global _started
    with _start_lock:
        if _started:
            return
        t = threading.Thread(
            target=_run_orchestration_server,
            args=(port,),
            daemon=True,
            name="OrchestrationMCP",
        )
        t.start()
        _started = True
        logger.info(f"OrchestrationMCP starting on port {port}")
