# MyAgent Development Handoff

## Goal and baseline

MyAgent is a Python learning project for building a minimal local coding agent and understanding its mechanisms. First stabilize one agent, then add one teachable mechanism at a time.

`Myagent_plan.md` is the current product and architecture baseline. The former platform plan is preserved in `docs/archive/Myagent_plan_before_learning_mvp.md` for reference; it does not override the new milestone scope.

## Workspace and environment

- Repository: `D:\Develop\Project\Myagent_01`
- Remote: `https://github.com/wayneim/Myagent_01.git`
- Baseline before S1: `8fc6ab5` on `main`; consult git log/status for the current revision and working changes.
- User-installed Python: `D:\Develop\Environment\python\python.exe` (3.15.0).
- Project virtual environment: `venv`, not `.venv`.
- Use `venv\Scripts\python.exe` explicitly. An existing terminal may still have the old PATH.
- Dependencies are installed with `venv\Scripts\python.exe -m pip install -e ".[dev]"`.
- Never reset, delete or overwrite unrelated user work. Do not commit or push without explicit instruction.

## Current milestone

S0 and S1 implement the development environment and a reliable offline single-agent loop:

- `protocol.py`: UserMessage, AssistantTurn, ToolCall, ToolResult, ToolResultsMessage, events and responses.
- `session.py`: Session owns the complete transcript; SessionStore retains and retrieves sessions in memory.
- `core.py`: orchestrates model/tool turns, stores both assistant and tool messages, bounds steps and handles ProviderError/cancellation.
- `providers/minimax.py` and `providers/qwen.py`: rebuild requests from the supplied transcript; they do not cache conversation history. Original assistant payloads are JSON dictionaries, preserving required protocol blocks and IDs.
- `tools/executor.py`: validates JSON Schema, checks every declared resource through PermissionEngine, executes and normalizes errors/output limits.
- `security/permissions.py`: matching deny wins over allow; among other matching rules the last match wins. CLI approvals remain one-time.
- `security/workspace.py` and file search tools: enforce workspace/sensitive paths for searches and direct reads; searches also check each matched file's read permission.
- `runtime.py`: plan mode exposes inspection tools; build adds editing tools. Local Shell is registered only with explicit opt-in.
- `cli/repl.py`: followups share a session; :new isolates a new conversation. One-shot failures return nonzero status; JSON mode is one-shot only and defaults to noninteractive approval denial. `--approval-mode interactive` enables one-time terminal approvals on stderr when stdin and stderr are terminals; without a terminal, ASK is denied.

## Verified on 2026-10-18

- `venv\Scripts\python.exe -m pytest -q`: **56 passed, 1 skipped**.
- The skipped test requires permission to create Windows symbolic links. Do not claim it passed.
- `venv\Scripts\python.exe -m pip check`: no broken requirements.
- `venv\Scripts\python.exe -m compileall -q myagent main.py`: passed.
- `venv\Scripts\python.exe main.py --help`: passed.
- `tests/test_provider_contract.py` exercises real SDK response models with mocked network calls for both providers, including replay, isolation and error mapping.
- `tests/test_workflow.py` uses scripted model decisions, real file tools and local Python assertions. It verifies read -> failing check -> failed edit -> corrected edit -> passing check -> followup.
- No real MiniMax or Qwen API call was performed. Do not infer real model success from scripted tests.

## Development rules

- Keep Agent dependent on internal protocols/interfaces; no SDK types or provider-specific branches in Core.
- Add providers through LLMProvider, tools through Tool/ToolRegistry; do not dispatch by hard-coded tool names in Core.
- Session is the source of truth. Provider clients may be shared, conversation history may not be hidden in providers.
- Preserve call_id and protocol-required assistant/result ordering. Cancellation must close declared tool batches.
- Native tools are the default. Provider-specific text/XML parsing is a separately enabled fallback, never a generic regex scan over model text.
- All authorization goes through PermissionEngine; compound tools expose every target with resources(). Search results need per-file authorization too.
- All Shell execution goes through SandboxBackend. LocalProcessBackend is unsandboxed; never describe cwd, approval prompts or path filters as OS isolation.
- Shell is disabled by default. `--allow-unsandboxed-shell` enables local execution with one-time approval for every command.
- Current local execution has no network enforcement or environment isolation.
- Prefer exact replacements for small edits and structured patches for multi-file changes.
- Use FakeProviders and scratch workspaces for reproducible regression tests. Do not load real secrets or invoke paid APIs for routine tests.
- Check git status before and after substantive work. No unsolicited commit, push, multi-agent delegation or recurring automation.

## Remaining limitations

- Sessions/events are memory-only; no disk resume, compaction, durable memory or token/cost accounting.
- No streaming, explicit application retry policy, repeated-call detection, background jobs, scheduler or team runtime.
- Ctrl+C is normalized by Core, but local subprocess cancellation does not yet guarantee termination of the entire process tree.
- apply_patch still applies operations sequentially. A later preflight/I/O failure may leave earlier edits in place; it is not transactional.
- File writes lack expected-hash conflict detection and use a fixed temporary filename.
- Searches skip common generated directories, binary-looking files and oversized grep files, but do not implement full gitignore support or regex CPU timeouts.
- Per-tool output truncation is not a complete context-management system; large reads and subprocess capture still need work.
- SDK/default model compatibility requires a separately configured real-provider smoke run.

## Next step: S2 single-agent MVP

1. Load bounded workspace/project instructions and include OS/Shell/workspace facts in prompt assembly.
2. Add unique atomic-write temporaries, expected-content hashes and full patch preflight before writes.
3. Capture Git baseline and summarize this task's changes without resetting existing user work.
4. Validate one configured real provider in a disposable exercise repository, then address actual timeout/truncation/retry issues observed.
5. Advance to Hooks/Todo/Skills only after that coding MVP is understood and verified. Follow the full staged plan for later mechanisms.
