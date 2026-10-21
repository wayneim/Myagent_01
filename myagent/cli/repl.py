"""Minimal interactive CLI."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
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
    elif event.type in {EventType.ERROR, EventType.TASK_CANCELLED}:
        print(f"[error] {event.data['message']}")


def _approval_handler(mode: str, json_events: bool) -> CliApprovalHandler | None:
    """Keep approval policy separate from event formatting; never read piped input."""
    if mode == "deny" or (mode == "auto" and json_events):
        return None
    if not sys.stdin.isatty() or not sys.stderr.isatty():   # 判断是否交互式终端
        return None

    def read_answer(prompt: str) -> str:
        print(prompt, file=sys.stderr, end="", flush=True)
        return input()

    return CliApprovalHandler(
        input_fn=read_answer,
        output_fn=lambda message: print(message, file=sys.stderr, flush=True),  # 打印到错误流中，数据与审批提示分离
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="MyAgent coding assistant")
    parser.add_argument("task", nargs="?", help="One-shot task")                # 可选的一次性任务指令，提供则执行完退出，不进入循环
    parser.add_argument("--workspace", type=Path, default=None)
    parser.add_argument("--json-events", action="store_true")                   # 开启后所有事件输出 JSON 格式
    parser.add_argument(
        "--approval-mode", choices=("auto", "interactive", "deny"), default="auto",
        help="Approval for ASK rules: auto prompts in text mode, interactive also prompts in JSON mode, deny never prompts; prompting requires terminal stdin and stderr",
    )
    parser.add_argument("--mode", choices=("plan", "build"), default="build")   # 运行模式
    parser.add_argument("--allow-unsandboxed-shell", action="store_true", help="Enable the local shell without OS isolation; each call still requires approval")
    args = parser.parse_args()
    if args.json_events and not args.task:
        parser.error("--json-events requires a one-shot task")
    # 打印事件
    handler = lambda event: print(json.dumps({"type": event.type.value, "data": event.data}, default=str)) if args.json_events else _print_event(event)
    approval_handler = _approval_handler(args.approval_mode, args.json_events)
    try:
        config = replace(AgentConfig.from_environment(args.workspace), allow_unsandboxed_shell=args.allow_unsandboxed_shell)
        agent = build_agent(config, handler, mode=args.mode, approval_handler=approval_handler)
    except ValueError as exc:
        handler(AgentEvent(EventType.ERROR, {"message": str(exc)}))
        return 2
    if args.allow_unsandboxed_shell and args.mode == "build":
        warning = "Local shell enabled: NO OS isolation; filesystem, network and inherited environment are unrestricted."
        if args.json_events:
            print(json.dumps({"type": "warning", "data": {"message": warning}}))
        else:
            print(f"[warning] {warning}")
    if args.task:
        response = agent.run(args.task, max_steps=config.max_steps)
        return 0 if response.completed else 1
    session = agent.new_session()
    print("Commands: :new (new conversation), :help, :quit")
    while True:
        try:
            task = input("myagent> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if task in {":q", ":quit", ":exit"}:
            return 0
        if task == ":new":
            session = agent.new_session()
            print("Started a new conversation.")
            continue
        if task == ":help":
            print("Commands: :new (new conversation), :help, :quit")
            continue
        if task:
            agent.run(task, max_steps=config.max_steps, session_id=session.session_id)


if __name__ == "__main__":
    raise SystemExit(main())
