"""Execution backend abstraction; policy is separate from isolation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int
    stdout: str
    stderr: str
    sandboxed: bool


class SandboxBackend(ABC):
    @abstractmethod
    def run(self, command: str, workspace: Path, timeout_seconds: int) -> ProcessResult:
        """Execute a command under the backend's actual isolation guarantees."""
