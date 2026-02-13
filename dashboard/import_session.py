"""
In-memory session manager for the Import Wizard.

Stores wizard state (parsed rows, mappings, duplicates, preview) between
API calls. Sessions auto-expire after 30 minutes.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ImportSession:
    """Holds all wizard state for a single import session."""

    session_id: str
    created_at: float

    # Step 1: Parse
    raw_headers: List[str] = field(default_factory=list)
    raw_rows: List[Dict[str, str]] = field(default_factory=list)
    detected_ecosystems: Dict[str, int] = field(default_factory=dict)
    input_method: str = ""  # "file" or "paste"
    filename: Optional[str] = None

    # Step 2: Column Mapping
    column_mapping: Optional[Dict[str, str]] = None  # incoming -> canonical
    auto_mappings: Optional[List[Dict]] = None  # auto-generated suggestions
    computed_columns: List[str] = field(default_factory=list)
    mapped_rows: Optional[List[Dict[str, str]]] = None

    # Step 3: Ecosystem Split + Duplicates
    ecosystem_splits: Optional[Dict[str, List[Dict]]] = None
    duplicates: Optional[Dict[str, List[Dict]]] = None  # chain -> matches
    new_rows: Optional[Dict[str, List[Dict]]] = None  # chain -> new rows
    unmatched_ecosystems: List[str] = field(default_factory=list)

    # Step 4: Merge Preview
    merge_strategies: Dict[str, Dict[str, str]] = field(default_factory=dict)
    merge_preview: Optional[Dict[str, Dict]] = None  # chain -> preview

    # Step 5: Commit Result
    commit_result: Optional[Dict] = None


class ImportSessionManager:
    """Thread-safe in-memory session store with auto-expiry."""

    def __init__(self, ttl_seconds: int = 1800):
        self._lock = threading.Lock()
        self._sessions: Dict[str, ImportSession] = {}
        self._ttl = ttl_seconds

    def create_session(self) -> ImportSession:
        """Create a new session and clean up expired ones."""
        with self._lock:
            self._cleanup_expired()
            session_id = uuid.uuid4().hex[:12]
            session = ImportSession(
                session_id=session_id,
                created_at=time.time(),
            )
            self._sessions[session_id] = session
            return session

    def get_session(self, session_id: str) -> Optional[ImportSession]:
        """Get a session by ID, or None if not found/expired."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if time.time() - session.created_at > self._ttl:
                del self._sessions[session_id]
                return None
            return session

    def update_session(self, session_id: str, **kwargs: Any) -> bool:
        """Update session fields. Returns False if session not found."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            for key, value in kwargs.items():
                if hasattr(session, key):
                    setattr(session, key, value)
            return True

    def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        with self._lock:
            self._sessions.pop(session_id, None)

    def _cleanup_expired(self) -> None:
        """Remove sessions older than TTL. Called under lock."""
        now = time.time()
        expired = [
            sid
            for sid, s in self._sessions.items()
            if now - s.created_at > self._ttl
        ]
        for sid in expired:
            del self._sessions[sid]


# Singleton instance
import_sessions = ImportSessionManager()
