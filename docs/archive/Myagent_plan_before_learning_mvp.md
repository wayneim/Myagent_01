# MyAgent 01 项目计划

## 1. 项目目标

构建一个类似 Codex、Claude Code、OpenCode 的通用自动化 Agent，运行在本地开发环境中，具备以下能力：

- 理解自然语言任务并进行多轮推理
- 读取、搜索、创建和修改项目文件
- 执行命令行操作并根据结果继续处理任务
- 生成、修改和调试代码
- 支持多个云端模型之间切换
- 支持可扩展的工具和技能
- 在文件和命令执行前提供可控的安全策略

初始实现使用 MiniMax，后续逐步支持 DeepSeek 及其他兼容模型。

## 2. 已确认的设计决策

### 2.1 技术栈

- 编程语言：Python
- Agent 框架：原生实现，不依赖 LangChain、LlamaIndex 等 Agent 框架
- 模型调用：云端 API
- 交互方式：第一阶段使用命令行 REPL
- 项目定位：通用自动化平台，而不仅是单一代码生成器

### 2.2 模型兼容策略

不同模型及其 API 兼容层对工具调用的支持不一致，因此 Agent 不能把某一种厂商协议暴露给主循环或工具实现。

但文本 XML 解析不应成为 MiniMax 的默认路径。MiniMax 当前提供 Anthropic 和 OpenAI 兼容接口，并支持原生工具调用；第一阶段应优先保留并回传该接口要求的完整 assistant 工具调用消息和 tool result 消息。这样才能正确支持多轮工具调用、工具调用 ID、并发工具调用以及后续的流式响应。

采用三层 Provider 适配策略：

1. Provider Adapter 将各厂商响应转换为内部规范的 `AssistantTurn`、`ToolCall` 和 `ToolResult`。
2. 对支持原生工具调用的 Provider，使用其原生工具协议。MiniMax 初始接入优先使用 Anthropic 兼容 API；OpenAI 兼容 API 为可选传输方式。
3. 仅对明确不支持原生工具调用、且经过模型能力验证的 Provider，启用 Provider 专属文本工具调用协议作为降级路径。

内部工具调用结构至少包含不可变的 `call_id`、工具名、JSON 参数、来源协议和解析错误信息。工具执行层只能消费经过校验的内部结构，不感知模型厂商格式。

文本降级格式不应声称“通用 XML 都能可靠解析”。需要按 Provider 注册格式化器、流式增量解析器和恢复策略。例如可以支持：

- `<tool_call>{"name":"...","arguments":{...}}</tool_call>`
- Provider 特有的 XML/分隔符格式

解析原则：

- 原生工具调用优先级最高；只有原生调用为空且 Provider 明确声明文本协议时才解析文本。
- 文本协议是受控能力，不对任意普通回答做宽松正则扫描，避免把代码或文档中的 XML/JSON 误执行成工具调用。
- 流式响应必须增量缓冲，在完整调用边界到达后才解析和执行。
- 解析失败时保留原始响应并将结构化错误反馈给模型，不能静默丢失输出。
- 工具参数先做 JSON 解码，再做严格 Schema 校验。
- Provider 能力通过版本化 Model Profile 声明，不能只依赖 `supports_native_tool_calls: bool`。

### 2.3 初始模型

第一阶段默认接入 MiniMax。

模型层需要抽象出统一接口，至少包含：

- 模型名称
- API 基础地址
- API Key
- API 协议类型（Anthropic、OpenAI 或自定义）
- 原生工具调用、并发工具调用、流式调用和图像输入等能力声明
- 文本工具调用协议及其版本（仅在必要时配置）
- 请求超时和重试配置
- 最大上下文长度
- 最大输出长度、价格/配额信息和可用性状态

后续可以通过配置切换 DeepSeek、OpenAI、Anthropic 或其他兼容 API 的模型，而不修改 Agent 主循环和工具实现。不同 Provider 的请求、响应和消息续传由 Adapter 负责，不能假定“OpenAI 兼容”就意味着工具调用、流式格式和上下文语义完全相同。

## 3. 总体架构

```text
用户输入
   |
   v
CLI / REPL
   |
   v
Agent Core
   |
    +--> 会话、上下文和取消管理
   |
   +--> LLM Provider
   |       |
   |       +--> 原生 tool_calls
   |       |
   |       +--> 文本工具调用解析
   |
    +--> Tool Registry 和策略引擎
           |
           +--> 文件读取和搜索
           +--> 文件精确编辑
           +--> 文件创建和写入
           +--> Shell 命令执行
           +--> 后续扩展工具
                   |
                   v
              Security Layer
              OS 沙箱、权限、确认、网络策略
```

## 4. Agent 主循环

Agent 采用事件驱动的 Think -> Act -> Observe 循环。这里的“Think”是模型响应，不要求或保存模型私有推理内容。

1. 接收用户任务。
2. 建立会话 ID、工作区、Git 基线和取消令牌，加载分层项目指令。
3. 构造系统提示词、项目上下文和历史消息，请求 LLM 的流式或非流式响应。
4. Provider Adapter 归一化原生或已启用的文本工具调用，并保留厂商要求回传的原始 assistant turn。
5. 对每个工具调用进行参数校验、策略判定和必要的用户确认。
6. 对彼此独立且被策略允许的只读调用并发执行；写入操作默认串行执行。
7. 将带 `call_id` 的工具结果及必要的原始 Provider 消息加入会话历史。
8. 继续请求 LLM，直到模型返回最终答案、用户取消、触发预算/循环限制或出现不可恢复错误。

需要设置以下保护措施：

- 单次任务最大循环次数
- 单次工具执行超时
- 单次任务总执行时间限制
- 可取消的前台与后台工具任务
- 工具输出长度限制
- 工具输出进入上下文前的截断、落盘引用和按需重读策略
- 上下文超限时的摘要策略，且不丢失未完成工具调用、权限决定和关键文件变更
- 工具执行失败后的结构化错误反馈
- 重复工具调用和无进展循环检测
- 单任务 Token、费用和网络访问预算

## 5. 工具层设计

### 5.1 工具注册

所有工具通过注册中心统一管理。每个工具至少提供：

- 工具名称
- 功能描述
- 参数定义
- 是否需要用户确认
- 执行函数
- 结构化执行结果
- 资源声明（路径、命令、URL 等）和副作用标注
- 可取消性、超时、输出上限及可否并发执行

模型看到的是工具描述，运行时使用的是注册中心中的实际实现。

### 5.2 第一阶段工具

#### `read_file`

读取指定文件内容，支持行号范围和最大输出长度限制。

#### `glob`

按照文件模式搜索工作区中的文件，例如 `**/*.py`。

#### `grep`

在工作区文件中搜索文本或正则表达式，并限制结果数量和单行长度。

#### `edit_file`

通过旧文本和新文本进行精确替换：

```text
edit_file(path, old_string, new_string)
```

#### `write_file`

创建新文件或在明确授权后重写文件。

#### `bash`

在操作系统或容器沙箱中执行命令，返回退出码、标准输出、标准错误、运行目录和沙箱状态。

#### `apply_patch`

应用结构化补丁，可同时处理多个文件的创建、更新和删除。该工具与 `edit_file` 一样受统一的 `edit` 权限控制。

#### `git_status` / `git_diff`

读取变更基线、查看 Agent 产生的修改并为用户确认提供可审计的变更摘要。它们是代码 Agent 的核心观测工具，应进入第一阶段而不是后续阶段。

## 6. 文件修改策略

精确替换是 OpenCode 的主编辑路径，适合小范围、可验证的改动；但不应作为唯一编辑原语。Codex 广泛使用补丁，OpenCode 同时提供 `apply_patch`，因为多文件重构、文件删除和相邻变更需要原子表达。

第一阶段应同时实现精确替换和结构化补丁，两者共享同一权限检查、路径校验、原子写入与变更记录。

### 6.1 默认操作

```text
edit_file(
  path="src/example.py",
  old_string="旧代码片段",
  new_string="新代码片段"
)
```

### 6.2 执行规则

- 文件路径必须位于允许的工作区内
- `old_string` 必须匹配到且只能匹配到一处
- 未找到匹配内容时返回明确错误
- 匹配多处时拒绝修改，要求模型提供更长上下文
- 修改前检查文件版本或内容哈希，防止文件被用户或其他 Agent 并发改动后发生错误覆盖
- 修改后返回变更摘要
- 写入采用临时文件加原子替换，避免进程中断造成半写入
- 保留会话级的修改清单，以 `git diff` 为主要审查和恢复依据；不要为每次编辑无条件复制全量备份

### 6.3 与其他方式的关系

- 精确替换：默认方式，适合局部修改，Token 消耗低
- Patch/Diff：第一阶段实现，适合多文件、删除和较大范围修改；补丁应用失败时返回冲突上下文，不自动盲目重试
- 全文件重写：仅用于新文件或明确要求重写的场景

## 7. 安全策略

当前“Level 0-4”分级不适合作为长期核心模型：它混合了物理隔离、权限提示和工具风险，无法表达“允许 `git status`、询问 `git push`、拒绝读取 `.env`”这类真实开发场景。

参考 Codex 的“沙箱 + approval policy”、Claude Code 的“OS 沙箱 + allow/ask/deny 规则”和 OpenCode 的按资源匹配规则，采用两层独立控制：

1. 沙箱策略决定进程事实上能够访问的文件、网络、环境变量和系统能力。
2. 权限策略以 `allow`、`ask`、`deny` 判断某个工具对某个资源是否可以运行。

默认建议为：工作区可写、工作区外禁止、网络关闭、敏感文件禁止读取、读操作自动允许、编辑和受信任的本地开发命令按规则允许，涉及网络、外部目录、发布、凭据和破坏性命令时询问。

### 7.1 文件系统沙箱

- 默认只允许访问当前 Agent 工作区
- 规范化路径后再检查边界，防止 `..` 路径穿越
- 拒绝访问工作区外的文件
- 对符号链接进行额外检查，避免绕过工作区限制
- 对敏感文件模式提供保护，例如密钥、凭据和系统配置文件
- 不把 Python/Node 等子进程视为可信；路径规则只能做应用层防护，必须由 OS 级隔离兜底
- 默认向子进程传递最小环境变量集合，避免 API Key 和用户凭据泄露给构建脚本

### 7.2 权限规则

每条规则由 `action`、`resource pattern` 和 `effect` 组成：

```text
effect: allow | ask | deny
action: read | edit | shell | network | external_directory | mcp.<server>.<tool>
resource: 路径、命令前缀、域名或工具输入对应的资源
```

规则必须有明确的优先级：先匹配不可覆盖的安全拒绝，再匹配项目/用户规则，最后使用会话默认值。应支持“仅本次”“本会话记住”“保存为项目规则”三种确认结果。

推荐最小默认规则示例：

```text
deny  read  .env
deny  read  .env.*
deny  read  **/secrets/**
allow read  <workspace>/**
allow glob  <workspace>/**
allow grep  <workspace>/**
ask   edit  <workspace>/**
allow shell git status*
allow shell git diff*
ask   shell *
ask   network *
deny  external_directory *
```

### 7.3 命令执行安全

- 命令默认在工作区作为当前目录执行，但这不是沙箱；Windows、macOS 和 Linux 需要分别选择可执行的 OS 级隔离后端
- 设置执行超时和输出大小上限
- 记录命令、参数、执行结果和用户授权状态
- 网络默认关闭；启用网络时按域名或工具调用单独授权
- 危险命令需要确认或直接拒绝，例如权限提升、磁盘格式化、递归删除、远程发布和凭据读取
- 不允许通过命令绕过文件沙箱；命令内启动的任意解释器、重定向和子进程都必须仍在 OS 沙箱约束内
- Windows 第一阶段应明确支持边界：优先使用受限子进程/容器后端；在没有可靠隔离后端时，降级为“需确认但非安全沙箱”，不得宣称已隔离

### 7.4 用户确认

确认提示至少包含：

- 将要执行的工具名称
- 目标文件或命令
- 可能影响的范围
- 允许一次、允许本次任务或拒绝
- 会话或项目级规则写入前的作用范围预览
- 对命令应显示解析后的实际命令、工作目录、网络需求和受影响文件，而非只显示原始字符串

## 8. 项目目录规划

```text
Myagent_01/
├── agent/
│   ├── __init__.py
│   ├── core.py              # Agent 主循环
│   ├── provider.py          # Provider 接口和能力模型
│   ├── providers/           # MiniMax、OpenAI、Anthropic 等适配器
│   ├── protocol.py          # 内部消息和工具调用规范
│   ├── session.py           # 会话、取消、预算和持久化
│   ├── context.py           # 消息历史和上下文压缩
│   └── config.py            # 配置管理
├── tools/
│   ├── __init__.py
│   ├── base.py              # 工具接口
│   ├── registry.py          # 工具注册中心
│   ├── file_read.py         # read_file、glob、grep
│   ├── file_edit.py         # 精确替换
│   ├── file_write.py        # 文件创建和写入
│   ├── patch.py             # 结构化补丁应用
│   ├── git.py               # Git 状态与差异读取
│   └── shell.py             # 受控命令执行
├── security/
│   ├── __init__.py
│   ├── sandbox.py            # 路径和工作区限制
│   ├── permissions.py       # 按资源匹配的规则与确认
│   └── command_policy.py    # 命令解析和风险分类
├── cli/
│   ├── __init__.py
│   └── repl.py              # 交互式命令行
├── tests/
│   ├── test_tool_parser.py
│   ├── test_sandbox.py
│   ├── test_file_edit.py
│   ├── test_permissions.py
│   ├── test_provider_minimax.py
│   └── test_agent_core.py
├── .env.example
├── requirements.txt
├── main.py
└── Myagent_plan.md
```

## 9. Phase 1 实现范围

### 9.1 基础能力

- Python 项目初始化
- MiniMax Anthropic 兼容 API 配置和原生工具调用
- Provider 接口、模型能力 Profile 和内部消息协议
- 已配置文本协议的工具调用解析，不把通用 XML 解析作为默认功能
- Agent 主循环
- 会话 ID、取消、步骤/费用预算和消息续传
- CLI REPL

### 9.2 文件和命令工具

- 文件读取
- 文件搜索
- 内容搜索
- 精确替换编辑
- 结构化补丁应用
- 新文件写入
- 受控 Shell 执行
- Git 状态和差异查看

### 9.3 安全能力

- 工作区路径边界和敏感文件拒绝规则
- `allow` / `ask` / `deny` 权限规则与资源匹配
- 文件写入、外部目录、网络和 Shell 的独立确认策略
- 命令超时
- 输出大小限制
- 基本审计日志
- 明确的 Windows 隔离后端或“未隔离”降级标识

### 9.4 测试重点

- 文本工具调用的多种格式解析
- 原生工具调用优先级
- Provider 工具调用消息和 `call_id` 的完整续传
- JSON 参数错误处理
- 流式文本工具调用的分块和不完整输入恢复
- 路径穿越防护
- 符号链接边界检查
- 精确替换的唯一匹配约束
- 补丁原子性和文件并发修改冲突
- 权限规则的优先级、外部目录和敏感文件拒绝
- Shell 超时和非零退出码
- Shell 子进程的网络、环境变量和工作区边界
- Agent 达到循环上限后的行为
- 用户取消、重复调用和 Token/费用预算耗尽后的行为

## 10. 后续阶段

### Phase 2：能力增强

- DeepSeek 等模型适配
- 可配置的模型路由和故障转移
- 更多 Provider 与文本工具协议注册表
- 浏览器自动化
- 网页搜索
- 上下文压缩
- MCP 客户端、技能和插件加载
- 只读 explore/review 子 Agent 与受限 build Agent

### Phase 3：平台化

- Web API 和 Web UI
- 多用户隔离
- 任务队列和后台执行
- 多 Agent 协作
- 审计和执行监控
- 工具权限策略管理
- 容器或虚拟机沙箱

## 11. 初始配置示例

环境变量示例：

```text
MINIMAX_API_KEY=your-api-key
MINIMAX_BASE_URL=https://api.minimax.cn/anthropic
MINIMAX_MODEL=MiniMax-M3
MYAGENT_WORKSPACE=.
MYAGENT_SANDBOX_MODE=workspace-write
MYAGENT_NETWORK_MODE=deny
```

实际模型名称、API 地址、区域和请求格式以 MiniMax 当前 API 文档为准，不能在代码中硬编码为唯一实现。MiniMax 也提供 OpenAI 兼容地址；该地址应由 Provider 配置选择，而非由 Agent 主循环假定。

## 12. 实施顺序

Phase 1 采用“扩展点先行、最小闭环交付”的顺序。每个扩展点先定义稳定内部协议，再接入一个可运行实现。这样新增模型、工具、权限后端或 UI 时，不需要重写 Agent 主循环。

### 12.1 阶段 A：基础工程和稳定协议

1. 在 `Myagent_01` 初始化 Git 仓库，建立 `.gitignore`、提交规范、基础 CI 和测试目录。
2. 定义内部消息协议：`UserMessage`、`AssistantTurn`、`ToolCall`、`ToolResult`、`FinalAnswer`。
3. 定义事件协议：任务开始、模型响应、工具请求、权限请求、工具结果、文件变更、任务结束和错误。
4. 定义 Provider 接口、Model Profile、Tool Protocol Adapter 和统一错误类型。
5. 定义 Tool 接口、Tool Registry、资源声明、副作用标注、超时、取消和并发能力。
6. 定义配置接口和分层配置来源：默认值、用户配置、项目配置、会话覆盖和环境变量。

验收标准：核心模块只能依赖内部协议和接口，不能直接导入 MiniMax SDK、CLI 实现或具体工具模块。

### 12.2 阶段 B：安全和执行后端

1. 实现 `WorkspaceResolver`，统一处理路径规范化、路径穿越、符号链接和敏感文件。
2. 实现 `PermissionEngine`，支持 `allow`、`ask`、`deny`、规则优先级、资源匹配和一次性/会话级授权。
3. 实现 `SandboxBackend` 抽象接口，至少定义文件系统、网络、环境变量、工作目录和进程生命周期能力。
4. 实现 Windows 初始执行后端，并明确报告其实际隔离能力；如果当前环境无法提供 OS 级隔离，必须进入严格确认降级模式。
5. 实现 `CommandPolicy`，把命令解析、风险分类和权限资源生成独立出来，不在 Shell 工具中硬编码黑名单。
6. 实现统一 `ExecutionContext`，向所有工具传递工作区、权限、取消令牌、超时和审计上下文。

验收标准：任何工具都必须通过同一个策略入口；Shell、补丁和自定义工具不能自行绕过权限或路径检查。

### 12.3 阶段 C：工具扩展层

1. 实现只读工具：`read_file`、`glob`、`grep`。
2. 实现编辑工具：`edit_file`、`apply_patch`、`write_file`。
3. 实现 Git 适配器和工具：`git_status`、`git_diff`，记录任务开始时的 Git HEAD 和工作区状态。
4. 实现 Shell 工具，但只依赖 `ExecutionContext` 和 `SandboxBackend`，不直接依赖权限实现。
5. 为每个工具补充独立 Schema、资源声明、错误类型、超时和取消行为。
6. 支持工具注册表按配置启用/禁用工具，为后续 MCP 和插件加载保留同一注册接口。

验收标准：新增一个工具只需要实现 Tool 接口并注册，不需要修改 Agent Core、CLI 或权限引擎。

### 12.4 阶段 D：MiniMax Provider 和协议适配

1. 实现通用 `LLMProvider` 接口和 MiniMax Anthropic Provider。
2. 优先验证原生工具调用、流式响应、工具调用 ID、多工具调用和 tool result 续传。
3. 将 MiniMax 原始响应保存在 Provider 层，转换为内部 `AssistantTurn`，避免主循环依赖 Anthropic 消息结构。
4. 实现重试、超时、限流、API 错误和上下文超限的统一错误映射。
5. 预留 OpenAI 兼容 Provider，但只有完成 Provider 契约测试后才能接入 Agent。
6. 为非原生工具调用定义独立 `TextToolProtocol` 接口；文本协议不得混入通用响应解析器。

验收标准：将 MiniMax Provider 替换为测试 Provider 后，Agent Core、工具和权限测试无需修改。

### 12.5 阶段 E：Agent Core 和会话

1. 实现事件驱动的 Agent Core，使用依赖注入获取 Provider、Tool Registry、Permission Engine、Sandbox Backend 和 Session Store。
2. 实现工具调用调度：只读调用可并发，编辑和 Shell 默认串行；并发策略由工具能力声明决定。
3. 实现循环上限、Token/费用预算、工具超时、取消、重复调用和无进展检测。
4. 实现上下文管理：输出截断、文件引用、摘要和未完成调用保护。
5. 实现 Session Store，保存会话元数据、事件日志、Provider 消息、权限决定和变更清单。
6. 实现会话恢复和中断恢复，恢复前校验工作区路径、Git HEAD 和配置版本。

验收标准：Agent Core 可以用 FakeProvider、FakeTool 和 FakePermissionEngine 完成完整测试，不需要网络、真实 Shell 或真实模型。

### 12.6 阶段 F：CLI 和最小可用闭环

1. 实现 CLI REPL，展示流式文本、工具调用、权限提示、命令结果和文件变更。
2. 支持 `plan`、`build` 两种预设：`plan` 禁止编辑和 Shell，`build` 按默认权限策略运行。
3. 实现任务取消、重试、会话恢复、`git diff` 查看和退出前未提交变更提示。
4. 实现结构化 JSON 事件输出，为后续 Web UI、CI 和远程执行保留接口。
5. 将用户交互封装为 `ApprovalHandler`，CLI 只是第一种实现，后续可替换为 Web 或 API handler。

验收标准：完成一个真实任务：读取项目、修改一个或多个文件、运行测试、展示 diff，并能够在中断后恢复。

### 12.7 阶段 G：扩展性验证和发布门槛

1. 使用 FakeProvider 验证 Provider 可替换。
2. 使用第二个测试 Provider 验证不同消息格式不会渗透到 Core。
3. 注册一个外部示例工具，验证 Tool Registry 可扩展。
4. 替换 ApprovalHandler 为自动策略实现，验证 CLI 不是权限耦合点。
5. 替换 SandboxBackend，验证 Shell 工具不需要改动。
6. 在 Git 仓库中验证多文件补丁、冲突、恢复和审计记录。
7. 执行契约测试、单元测试、安全测试、Provider Mock 测试和最小端到端测试。

发布门槛：未通过扩展性验证时，不进入 DeepSeek、MCP、浏览器自动化或多 Agent 开发。

## 13. Phase 1 扩展性约束

- Agent Core 只依赖内部协议和接口，不依赖具体 Provider、工具、CLI 或沙箱实现。
- 所有跨模块通信优先使用不可变数据对象和结构化事件，不传递厂商 SDK 对象。
- Provider 适配器负责外部 API 差异，工具层不读取模型原始响应。
- Tool Registry 是工具的唯一发现入口，禁止在 Agent Core 中写工具名称分支。
- Permission Engine 是权限的唯一决策入口，工具不能自行实现确认逻辑。
- Sandbox Backend 是执行隔离的唯一入口，Shell 工具不能直接决定网络、环境变量或系统权限。
- 文件工具、Shell 工具、MCP 工具和未来插件都遵循同一 Tool 接口和资源声明模型。
- 外部协议、配置文件和 Session Store 必须带版本号，升级时提供迁移策略。
- 不用全局单例保存会话、Provider、权限或工具状态；通过依赖注入传递运行上下文。
- 同一任务中的事件必须可序列化，保证未来可以接入 Web UI、队列和远程执行。
- 对新增能力优先增加实现类或注册项，不通过修改核心 `if/elif` 分支扩展。

## 14. 约束和原则

- 先保证工具执行可靠，再扩展复杂 Agent 能力
- 模型协议适配与工具执行解耦
- 原生 Provider 协议优先，文本工具调用只能按能力 Profile 显式启用
- 所有外部输入都必须进行校验
- 权限提示不是安全边界；必须区分应用层授权和 OS 级隔离
- 默认最小权限，危险操作显式授权
- 文件修改尽量保持小范围和可恢复
- 失败必须返回结构化、可供模型理解的错误
- 不把模型输出直接当作可执行命令或可信路径
- 不依赖单一模型的 Function Calling 能力
- 不把当前工作目录、命令前缀白名单或字符串黑名单误认为 Shell 沙箱
