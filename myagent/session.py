"""Serializable session state and in-memory storage implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from .protocol import AgentEvent


@dataclass
class Session:
    workspace: Path
    session_id: str = field(default_factory=lambda: uuid4().hex)
    events: list[AgentEvent] = field(default_factory=list)
    messages: list[object] = field(default_factory=list)


class SessionStore:
    def create(self, workspace: Path) -> Session:
        return Session(workspace=workspace)
