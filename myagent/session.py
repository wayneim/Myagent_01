"""Serializable session state and in-memory storage implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from .protocol import AgentEvent, Message


@dataclass
class Session:
    workspace: Path
    session_id: str = field(default_factory=lambda: uuid4().hex)
    events: list[AgentEvent] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)


class SessionStore:
    """Keep sessions for this process; disk persistence is a later milestone."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(self, workspace: Path) -> Session:
        session = Session(workspace=workspace.resolve())
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise ValueError(f"Unknown session: {session_id}") from None
