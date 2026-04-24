"""
In-memory store for active sessions.

Each entry holds the SessionState plus the infrastructure for
progress streaming (queue) and cancellation (event).
"""

import queue
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

from dj_clipper.models.session_model import SessionState


@dataclass
class SessionEntry:
    state: SessionState
    analysis_queue: queue.Queue = field(default_factory=queue.Queue)
    export_queue: queue.Queue = field(default_factory=queue.Queue)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    # Index into all_candidates for the next "generate more" slice
    next_all_idx: int = 0


_store: Dict[str, SessionEntry] = {}


def create(state: SessionState) -> SessionEntry:
    entry = SessionEntry(state=state)
    _store[state.session_id] = entry
    return entry


def get(session_id: str) -> Optional[SessionEntry]:
    return _store.get(session_id)


def delete(session_id: str) -> None:
    _store.pop(session_id, None)


def all_ids():
    return list(_store.keys())
