"""Minimal interactive CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from myagent.config import AgentConfig
from myagent.protocol import AgentEvent, EventType
from myagent.runtime import build_agent
from myagent.security.permissions import CliApprovalHandler


def _print_event(event: AgentEvent) -> None:
    if event.type is EventType.ASSISTANT_TURN and event.data.get("text"):
        print(event.data["text"])
    elif event.type is EventType.TOOL_REQUESTED:
        print(f"[tool] {event.data['name']}")
    elif event.type is EventType.TOOL_COMPLETED:
        print(f"[tool result] {event.data['content']}")
    elif event.type is EventType.ERROR:
        print(f"[error] {event.data['message']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="MyAgent coding assistant")
    parser.add_argument("task", nargs="?", help="One-shot task")
    parser.add_argument("--workspace", type=Path, default=None)
    parser.add_argument("--json-events", action="store_true")
    parser.add_argument("--mode", choices=("plan", "build"), default="build")
    args = parser.parse_args()
    config = AgentConfig.from_environment(args.workspace)
    handler = lambda event: print(json.dumps({"type": event.type.value, "data": event.data}, default=str)) if args.json_events else _print_event(event)
    approval_handler = None if args.json_events else CliApprovalHandler()
    agent = build_agent(config, handler, mode=args.mode, approval_handler=approval_handler)
    if args.task:
        agent.run(args.task, max_steps=config.max_steps)
        return
    while True:
        try:
            task = input("myagent> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if task in {":q", ":quit", ":exit"}:
            return
        if task:
            agent.run(task, max_steps=config.max_steps)


if __name__ == "__main__":
    main()
