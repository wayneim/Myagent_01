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

模型名和端点沿用项目配置，真实 API 兼容性尚需配置密钥后验证。

```powershell
.\venv\Scripts\python.exe main.py --workspace . --mode plan "阅读项目并解释入口"
.\venv\Scripts\python.exe main.py --workspace . --mode build
```

REPL 连续输入沿用当前会话；`:new` 创建新会话，`:help` 显示命令，`:quit` 退出。
当前会话只保存在内存中，退出程序后不能恢复。

## 文件与命令权限

`plan` 只暴露读取、搜索和 Git 观察工具；`build` 增加文件编辑，每个目标文件须获得审批。
敏感路径和工作区外路径受到文件工具的应用层检查；这不是 OS 级沙箱。

Shell 默认关闭。需要运行命令时，请在练习工作区显式启用：

```powershell
.\venv\Scripts\python.exe main.py --workspace . --mode build --allow-unsandboxed-shell
```

本地后端使用 `subprocess`，不隔离文件系统、网络或继承的环境变量。Windows 使用 cmd.exe 语法。
每个命令都需本次审批；配置中的 network_mode 当前不执行网络限制。
JSON 事件模式只接受一次性任务，不进行交互审批，需审批的操作默认拒绝：

```powershell
.\venv\Scripts\python.exe main.py --json-events --mode plan "解释项目结构"
```

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

已知后续工作包括项目指令加载、补丁预检/并发编辑冲突、Git 变更基线、持久会话和真实 Provider 验证。当前 apply_patch 仍会顺序修改文件，后续操作失败时可能保留前面的修改。
