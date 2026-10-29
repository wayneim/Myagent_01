# MyAgent

这是一个用于学习 Agent 机制的 Python 本地 coding agent。先完成可靠的单 Agent，再逐步实现 Hooks、Todo、Skills、上下文管理、子 Agent、MCP 和任务协作。

构建顺序和每阶段验收见 [Myagent_plan.md](Myagent_plan.md)。原平台方案保存在 [docs/archive/](docs/archive/Myagent_plan_before_learning_mvp.md)。

## 开发环境

项目要求 Python >=3.11；当前开发环境使用 Python 3.15.0。虚拟环境放在项目根目录 `venv`。

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -e ".[dev]"
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe main.py --help
```

也可以激活环境后使用 `python` 和 `myagent`：

```powershell
.\venv\Scripts\Activate.ps1
```

如果 PowerShell 限制执行激活脚本，直接使用上面的 `venv\Scripts\python.exe` 即可，不必修改全局执行策略。

## 配置模型

复制 `.env.example` 为 `.env`，配置一个 Provider。不要提交 `.env`。

- MiniMax：`MYAGENT_PROVIDER=minimax`，设置 `MINIMAX_API_KEY`，按所用模型配置 `MINIMAX_MODEL`、`MINIMAX_BASE_URL`。
- Qwen：`MYAGENT_PROVIDER=qwen`，设置 `QWEN_API_KEY`，可设置 `QWEN_MODEL`、`QWEN_BASE_URL`。

未指定 `MYAGENT_PROVIDER` 时默认使用 MiniMax，不会根据其他厂商的 Key 自动切换。所选厂商的 Key 未配置或只有空白时，启动会提示 `.env` / 环境变量配置方式并以状态码 2 退出，不发送模型请求。模型名和地址也不能为空。

新增厂商时，实现 `LLMProvider`，在 `myagent/providers/registry.py` 注册 `ProviderSpec`（厂商名、环境变量前缀、默认模型、默认地址和工厂路径）。配置加载和运行时创建共用注册表，无需修改 Core 或增加厂商判断分支。配置的模型必须支持当前适配器使用的原生工具调用协议；程序不会自动检测模型能力。流式和文本工具协议尚未实现。

模型名和端点沿用项目配置，真实 API 兼容性尚需配置密钥后验证。

```powershell
.\venv\Scripts\python.exe main.py --workspace . --mode plan "阅读项目并解释入口"
.\venv\Scripts\python.exe main.py --workspace . --mode build
```

REPL 连续输入沿用当前会话；`:new` 创建新会话，`:help` 显示命令，`:quit` 退出。
当前会话只保存在内存中，退出程序后不能恢复。

## 项目指令与环境提示

默认通过 `build_agent()` 组装时，系统提示词由 `myagent/prompting.py` 生成，包含基础行为要求、实际 OS、绝对工作区路径、运行模式和 Shell 可用性。启用本地 Shell 时明确说明命令语法、逐次审批以及没有 OS/网络/环境变量隔离。

启动时只加载指定工作区根目录的 `AGENTS.md`，不读取父目录或递归扫描子目录；首版暂不支持嵌套指令继承。该文件为 UTF-8 文本（支持 BOM），最多 32 KiB。缺失时可正常启动；超限、编码错误、读取失败或不安全路径会明确报错，不静默截断。加载同时经过 `WorkspaceResolver` 和 `PermissionEngine`；链接不能越出工作区、指向敏感文件或绕过实际目标的读权限。

项目指令不能扩大工具权限，也不能改变实际执行能力；用户明确任务优先于项目约定。提示词在 Agent 创建时生成一次，同一实例的多轮任务和新会话使用同一份快照。修改指令后应重新创建 Agent 或重启 CLI。直接构造 `Agent` 的嵌入调用仍使用基础提示词，可显式传入自行组装的 `system_prompt`。

## 文件与命令权限

`plan` 只暴露读取、搜索和 Git 观察工具；`build` 增加文件编辑，每个目标文件须获得审批。
敏感路径和工作区外路径受到文件工具的应用层检查；这不是 OS 级沙箱。

Shell 默认关闭。需要运行命令时，请在练习工作区显式启用：

```powershell
.\venv\Scripts\python.exe main.py --workspace . --mode build --allow-unsandboxed-shell
```

本地后端使用 `subprocess`，不隔离文件系统、网络或继承的环境变量。Windows 使用 cmd.exe 语法。
每个命令都需本次审批。
JSON 事件模式只接受一次性任务，默认不进行交互审批，需审批的操作默认拒绝：

```powershell
.\venv\Scripts\python.exe main.py --json-events --mode plan "解释项目结构"
```

输出格式和审批方式可以独立选择。`--approval-mode` 支持：

- `auto`（默认）：普通文本模式询问审批；JSON 模式拒绝需要询问的操作。
- `interactive`：包括 JSON 模式在内，均可通过终端逐次审批。
- `deny`：不询问，拒绝所有需要询问的操作；规则明确允许的读取等操作仍可执行。

交互审批要求 stdin 和 stderr 都连接终端；否则不读取输入，需要询问的操作直接拒绝。审批提示写入 stderr，JSON 事件继续写入 stdout。输入 `y` 或 `yes` 仅批准本次操作，其他回答或输入结束（EOF）均拒绝。

```powershell
.\venv\Scripts\python.exe main.py --json-events --approval-mode interactive "创建一个示例文件" > events.jsonl
```

该命令将 JSON 事件保存到文件，审批仍在终端进行。不要合并 stderr 到 stdout，否则审批提示会混入 JSON 输出。这是终端审批，尚不提供程序间的 JSON 审批请求/响应协议。

## 文件修改与冲突检查

`read_file` 在正文和元数据中返回完整文件原始字节的 SHA-256（`sha256`），即使只请求部分行也一样。`edit_file` 和 `write_file` 可以传入 `expected_hash`：

- 64 位 SHA-256：要求当前内容与上次读取一致，否则返回 `conflict`，提示重新读取。
- `"missing"`：要求目标不存在，适合 `write_file` 创建新文件；已有空文件也不会被当作不存在。
- 省略：兼容原有调用，不检查更早的读取版本；仍检查本次准备和提交之间的内容变化。需要保护读取后的用户改动时，应使用 `expected_hash`。

哈希按原始字节计算，换行符和 BOM 均参与。编辑按 UTF-8 文本精确匹配，未修改部分的换行保持原样。每次提交使用目标目录内的唯一临时文件，关闭后替换，正常失败或中断时尝试清理；不会复用或覆盖旧的固定临时文件。

`apply_patch` 的每项操作必须明确提供 `kind`（`edit` / `write`）、`path` 及对应参数。所有操作先做 Schema、路径、原始内容及匹配检查，再在内存中顺序模拟。同一文件上的后续操作看到前一步的模拟结果；后续 `expected_hash` 如果提供，也必须对应那个模拟版本，不能重复使用最初的哈希。通常给首项操作传入读取哈希，后续同文件操作省略即可。

例如先创建再编辑同一文件，只会提交最终的 `hello agent` 内容一次：

```json
{"operations": [
  {"kind": "write", "path": "example.txt", "content": "hello\n", "expected_hash": "missing"},
  {"kind": "edit", "path": "example.txt", "old_string": "hello", "new_string": "hello agent"}
]}
```

预检失败不会修改文件、创建目录或临时文件。预检成功后按文件逐个提交；发生 I/O 错误或冲突时，正文和 `modified_files` 元数据报告已提交的文件，不自动回滚。无内容变化的文件不替换、不计入已修改文件。

这是乐观并发检查，不是文件锁或操作系统级 compare-and-swap；最后一次检查与替换之间仍有外部写入竞争窗口。多文件提交不具备事务原子性，提交阶段失败可能留下已提交文件或已创建目录。

## 从哪里阅读代码

1. `protocol.py`：规范化消息、工具调用、结果和事件。
2. `session.py`：内存历史与会话 ID。
3. `core.py`：追加消息、请求模型、执行工具、继续或停止。
4. `tools/executor.py`：校验参数、逐资源授权、执行与错误返回。
5. `providers/`：将同一份会话翻译成两种厂商协议。
6. `cli/repl.py`：会话切换、审批入口和事件展示。

不需要 API Key 的完整练习：

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_workflow.py -q
```

该练习使用脚本代替模型决策，实际读取文件、运行本地 Python 检查，经历检查失败、编辑失败、修正和检查通过，再进行追问。它验证执行机制，不证明真实模型的任务完成能力。

已知后续工作包括嵌套项目指令、任务完成判定、工具输出展示、Git 变更基线、持久会话和真实 Provider 验证。文件修改已具备哈希检查和补丁完整预检，但仍有上述并发竞争窗口及多文件部分提交限制。
