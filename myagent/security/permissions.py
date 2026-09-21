"""Resource-level allow, ask, and deny policy evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fnmatch import fnmatch


class PermissionEffect(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True)
class PermissionRule:
    action: str
    resource: str
    effect: PermissionEffect


class ApprovalHandler:
    def approve(self, action: str, resource: str) -> bool:
        return False


class CliApprovalHandler(ApprovalHandler):
    """Ask for one-time approval through a terminal prompt."""

    def __init__(self, input_fn=input, output_fn=print) -> None:
        self._input = input_fn
        self._output = output_fn

    def approve(self, action: str, resource: str) -> bool:
        self._output(f"Permission required: {action} {resource}")
        answer = self._input("Allow this action? [y/N] ").strip().lower()
        return answer in {"y", "yes"}


class PermissionEngine:
    def __init__(self, rules: list[PermissionRule], approval_handler: ApprovalHandler | None = None) -> None:
        self._rules = rules
        self._approval_handler = approval_handler or ApprovalHandler()

    def check(self, action: str, resource: str) -> bool:
        effect = PermissionEffect.ASK
        for rule in self._rules:
            if rule.action in ("*", action) and fnmatch(resource, rule.resource):
                effect = rule.effect
        if effect is PermissionEffect.ALLOW:
            return True
        if effect is PermissionEffect.DENY:
            return False
        return self._approval_handler.approve(action, resource)
