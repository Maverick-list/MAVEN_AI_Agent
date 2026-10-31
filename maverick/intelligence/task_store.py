"""Maverick DevOS - Persistent Task & Execution Plan Storage Engine.

Maintains an atomic, WAL-backed SQLite database at ~/.maverick/tasks.db to ensure
orchestrated DAG plans, human approval gates, step results, and verification records
persist across server restarts, crashes, and multi-turn user workflows.
"""

from contextlib import contextmanager
import json
import logging
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("maverick.intelligence.task_store")

DEFAULT_DB_DIR = os.path.expanduser("~/.maverick")
DEFAULT_DB_PATH = os.path.join(DEFAULT_DB_DIR, "tasks.db")


class TaskStore:
    """
    SQLite-backed persistent store for orchestrated DAG execution plans.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create task execution ledger table with indexing."""
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orchestrated_plans (
                    plan_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    completed_at REAL,
                    awaiting_step_id INTEGER,
                    steps_count INTEGER DEFAULT 0,
                    payload TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_plans_created ON orchestrated_plans(created_at DESC);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_plans_status ON orchestrated_plans(status);"
            )

    def save_plan_data(self, plan_dict: Dict[str, Any]) -> None:
        """Upsert a plan data dictionary."""
        plan_id = plan_dict.get("plan_id", "")
        if not plan_id:
            return

        goal = plan_dict.get("goal", "")
        status = plan_dict.get("status", "pending")
        created_at = plan_dict.get("created_at", time.time())
        completed_at = plan_dict.get("completed_at")
        awaiting_step_id = plan_dict.get("awaiting_step_id")
        steps = plan_dict.get("steps", [])
        payload = json.dumps(plan_dict)
        now = time.time()

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO orchestrated_plans (
                    plan_id, goal, status, created_at, completed_at,
                    awaiting_step_id, steps_count, payload, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plan_id) DO UPDATE SET
                    status = excluded.status,
                    completed_at = excluded.completed_at,
                    awaiting_step_id = excluded.awaiting_step_id,
                    steps_count = excluded.steps_count,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at;
                """,
                (
                    plan_id,
                    goal,
                    status,
                    created_at,
                    completed_at,
                    awaiting_step_id,
                    len(steps),
                    payload,
                    now,
                ),
            )

    def get_plan_data(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full plan data by ID."""
        with self._connection() as conn:
            cur = conn.execute(
                "SELECT payload FROM orchestrated_plans WHERE plan_id = ?;",
                (plan_id,),
            )
            row = cur.fetchone()
            if row:
                try:
                    return json.loads(row["payload"])
                except Exception:
                    return None
            return None

    def list_plans(
        self,
        limit: int = 20,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List recent plans, optionally filtered by status."""
        query = "SELECT plan_id, goal, status, created_at, completed_at, awaiting_step_id, steps_count FROM orchestrated_plans"
        params: List[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?;"
        params.append(limit)

        results = []
        with self._connection() as conn:
            cur = conn.execute(query, tuple(params))
            for row in cur.fetchall():
                results.append(dict(row))
        return results

    def delete_plan(self, plan_id: str) -> bool:
        """Delete plan by ID."""
        with self._connection() as conn:
            cur = conn.execute(
                "DELETE FROM orchestrated_plans WHERE plan_id = ?;",
                (plan_id,),
            )
            return cur.rowcount > 0

    def clear(self) -> None:
        """Purge all stored plans (for test cleanup)."""
        with self._connection() as conn:
            conn.execute("DELETE FROM orchestrated_plans;")
