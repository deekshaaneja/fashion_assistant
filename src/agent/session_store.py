"""SessionStore: `DesignSession` persistence (product brief section 51).
sqlite3 (stdlib, no new dependency) rather than a JSON-file-per-session
store -- a single local file is just as non-distributed, but gives
serialized writes and a trivial "list all sessions" for free instead of a
hand-rolled file-locking scheme. One row per session, the session's own
`model_dump_json()` as the payload -- this store has no opinion on the
shape of a session, it only persists/reloads it.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from src.domain.models.session import DesignSession
from src.providers.settings import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class SessionStore:
    def __init__(self, db_path: str | None = None) -> None:
        path = Path(db_path or get_settings().agent_session_db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(_SCHEMA)
            self._conn.commit()

    def load(self, session_id: str) -> DesignSession | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        return DesignSession.model_validate_json(row[0])

    def save(self, session: DesignSession) -> None:
        # Validated round-trip BEFORE writing -- a corrupt/partial write
        # never survives to the next read (section 43).
        payload = session.model_dump_json()
        DesignSession.model_validate_json(payload)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sessions (session_id, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET payload_json = excluded.payload_json,
                                                        updated_at = excluded.updated_at
                """,
                (session.session_id, payload, session.created_at.isoformat(), session.updated_at.isoformat()),
            )
            self._conn.commit()

    def list_ids(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT session_id FROM sessions").fetchall()
        return [r[0] for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        _store = SessionStore()
    return _store


def reset_session_store_cache() -> None:
    """Test-only escape hatch -- mirrors `asset_store_module._store = None`
    used by the Phase 4 tests when settings/paths change between tests."""
    global _store
    _store = None
