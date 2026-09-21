# MyAgent Development Handoff

## Project Goal

MyAgent is an extensible local coding agent inspired by Codex, Claude Code, and OpenCode. It is implemented in Python. Phase 1 starts with MiniMax through its Anthropic-compatible API and must keep provider, tool, permission, sandbox, session, and UI implementations replaceable.

The detailed architecture and phased plan are in `Myagent_plan.md`. Treat that file as the product and architecture baseline.

## Repository State

- Repository root: `D:\testDevelop\AiTest01\Myagent_01`
- Branch: `main`
- Remote: `origin` -> `https://github.com/wayneim/Myagent_01.git`
- Latest committed revision: `079c94e 9/20初版计划`
- Current implementation files are untracked and have not been committed or pushed.
- Do not reset, checkout, delete, or overwrite unrelated user work.
- Do not commit or push unless the user explicitly asks.

## Current Structure

```text
Myagent_01/
├── AGENTS.md                 # This handoff document
├── Myagent_plan.md           # Architecture and implementation plan
├── pyproject.toml            # Python package metadata and dependencies
├── README.md                 # Basic setup instructions
├── .env.example              # MiniMax and workspace environment variables
├── .gitignore
├── main.py                   # CLI entry point
├── myagent/
│   ├── protocol.py           # Provider-independent messages, tool calls, events
│   ├── config.py             # AgentConfig and ModelProfile
│   ├── provider.py           # LLMProvider abstraction
│   ├── core.py               # Provider/tool-independent Agent loop
│   ├── session.py            # In-memory Session and SessionStore
│   ├── runtime.py            # Default dependency composition
│   ├── providers/
│   │   └── minimax.py        # MiniMax Anthropic-compatible provider
│   ├── security/
│   │   ├── permissions.py    # allow/ask/deny rule engine
│   │   ├── sandbox.py        # SandboxBackend abstraction
│   │   └── workspace.py      # Workspace path and sensitive-file checks
│   ├── tools/
│   │   ├── base.py           # ToolSpec, Tool, ExecutionContext
│   │   ├── registry.py       # Tool discovery and model definitions
│   │   ├── files.py          # read_file, glob, grep, edit_file, write_file
│   │   ├── patch.py          # Simplified structured apply_patch
│   │   ├── git.py            # git_status and git_diff
│   │   └── shell.py          # Shell tool using injectable backend
│   └── cli/
│       └── repl.py           # Minimal interactive CLI
└── tests/
    ├── test_workspace.py
    ├── test_permissions.py
    ├── test_tools.py
    └── test_core.py
```

## Completed Work

- Created Python package structure and `pyproject.toml`.
- Added the internal protocol types: `ToolCall`, `ToolResult`, `AssistantTurn`, `AgentEvent`, and `AgentResponse`.
- Added `LLMProvider`, `Tool`, `ToolRegistry`, `PermissionEngine`, and `SandboxBackend` extension seams.
- Added workspace boundary enforcement and basic `.env` protection.
- Added built-in file read/search/edit/write, simple structured patch, Git status/diff, and Shell tools.
- Added MiniMax provider using the Anthropic SDK and Anthropic-compatible MiniMax endpoint.
- Added an Agent loop that depends on the provider and tool interfaces, not MiniMax directly.
- Added a minimal CLI and event rendering.
- Added tests for workspace escape, permissions, exact replacement, and FakeProvider-driven Agent execution.
- Migrated mistakenly created source files from `D:\testDevelop\AiTest01\myagent` into this repository. The source of truth is now this repository's `myagent/` directory.

## Important Current Limitations

### Verification

- `python -m pip install -e ".[dev]"` was started but timed out after 120 seconds while downloading dependencies.
- Because that command timed out, `python -m compileall myagent main.py` and `python -m pytest` did not run to completion.
- First continuation step: rerun dependency installation with sufficient timeout, then run compile and tests.

### Security

- `myagent.runtime.LocalProcessBackend` uses `subprocess.run(..., shell=True)` and returns `sandboxed=False`.
- It is intentionally an unsandboxed fallback, not a security boundary.
- The default `ApprovalHandler` rejects `ask` actions, so write tools and ordinary shell commands cannot run from the current CLI until interactive approval is implemented.
- Windows OS-level restricted process/container sandboxing is not implemented.
- The runtime has no network enforcement; `MYAGENT_NETWORK_MODE` is configuration only at this point.

### Agent and Session

- Session storage is in memory only.
- No persisted session, resume, cancellation command, token/cost budgets, context compaction, repeated-call detection, or parallel read-only scheduling yet.
- The Agent loop returns normalized tool results to the provider but does not yet have robust provider message replay or a Provider contract test suite.

### Provider

- MiniMax real API integration has not been run with an API key.
- Streaming, retry policy, rate-limit mapping, and non-native text-tool protocols are not implemented.
- No second Provider exists yet. Add it only through `LLMProvider` plus provider contract tests.

### Tools

- `apply_patch` accepts a list of `edit` and `write` operations. It is not a unified-diff parser and is not transactional across files.
- File edits do not yet check content hashes or detect concurrent file changes.
- `glob` and `grep` need stronger result limits, binary-file handling, and resolver-based sensitive-path enforcement.
- Git tools only expose status and unstaged diff.

### CLI

- No interactive `ApprovalHandler`.
- No `plan` / `build` mode selection.
- No task cancellation, retry, session resume, or pre-exit change summary.
- JSON event output exists via `--json-events`, but events are not persisted.

## Development Rules

- Keep `Agent` dependent only on internal protocols and interfaces. Do not import MiniMax SDK types in `core.py`.
- Add providers through `LLMProvider`; do not add provider-specific branches in Agent Core.
- Add tools through `Tool` and `ToolRegistry`; do not add hard-coded tool-name branches in Agent Core.
- All permission decisions must go through `PermissionEngine`.
- All Shell execution must go through a `SandboxBackend`; never claim the current local backend is sandboxed.
- Keep the MiniMax provider on native Anthropic-compatible tool calls by default. Text/XML tool-call parsing is a provider-specific fallback, not a generic regex scan.
- Preserve `call_id` and required provider tool-result sequencing.
- Prefer exact replacements for small edits and structured patches for multi-file changes.
- Check `git status` before and after substantive work. Do not commit or push without explicit user instruction.

## Recommended Next Steps

1. Complete dependency install and run:

```powershell
python -m pip install -e ".[dev]"
python -m compileall myagent main.py
python -m pytest
```

2. Fix any test, typing, import, or Anthropic SDK compatibility failures discovered by validation.
3. Implement CLI-backed `ApprovalHandler` and explicit `plan` / `build` policies.
4. Improve the execution boundary: add a Windows-capable sandbox backend or make unsandboxed mode opt-in with prominent warnings.
5. Make `apply_patch` atomic or return a preflight failure before changing any file.
6. Add persisted session/event storage with Git baseline capture.
7. Add MiniMax Provider contract tests using mocked Anthropic responses, then verify a real API call only after `MINIMAX_API_KEY` is configured.
8. Implement streaming and robust error/retry handling before adding DeepSeek or text-based tool-call protocols.

## Useful Commands

```powershell
git status --short
python -m pytest
python main.py --help
python main.py --workspace . "Inspect this project"
```

For a real MiniMax session, configure `MINIMAX_API_KEY` in the environment. Do not commit `.env`.
