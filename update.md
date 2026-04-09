# LangChain Agent 升级方案

## 背景与目标

### 现状痛点

| 问题 | 位置 | 表现 |
|------|------|------|
| 硬编码意图分类 | `chat.py:116-153` | `if intent == CHAT/ANALYSIS/PROCESSING` 三选一，后续逻辑完全分离 |
| 意图识别阻塞调用 | `intent_service.py:67` | 每次对话先调一次 LLM 分类，再调一次 LLM 处理 = 至少 2 次 LLM 调用 |
| 上下文文本拼接 | `context_builder.py:40-365` | 历史消息转成字符串塞进 prompt，token 浪费且上限低 |
| 固定管线 | `excel_processor.py:70-82` | `_build_stages()` 只返回线性 `[GenerateValidateStage, ExecuteStage]`，无法动态增减 |
| 无工具抽象 | 无 | `filter/sort/group_by` 等操作用 if/else 散落在 `executor.py` 中，无法被 LLM 直接调用 |

### 升级目标

1. **意图消解为工具选择** — 去掉独立的意图识别步骤，Agent 自己决定调用哪些工具
2. **管线动态化** — Agent 根据用户需求自主规划工具调用顺序，不预先绑定
3. **上下文结构化** — 用 LangChain `ConversationBufferMemory` 管理对话历史，不再文本拼接
4. **工具可观测** — 每步工具调用都有 `step_tracker` 级别的记录，支持流式 SSE 上报
5. **澄清自然融入** — 工具返回 `Observation` 或 Agent `ask_for_input` 实现多轮澄清，无需独立分支

---

## 架构设计

### 整体架构

```
POST /chat
  └─► ExcelAgentExecutor
        ├─► ConversationBufferMemory (从 ThreadTurn 加载/保存历史)
        ├─► ChatPromptTemplate (system prompt + memory messages)
        └─► Agent (ReAct / Tool-calling)
              └─► Tools (每个 = 原有能力的包装)
                    ├─ ReadExcelTool        ← excel_parser.py + FileCollection 加载
                    ├─ GetSchemaTool        ← 从 FileCollection 提取表结构
                    ├─ FilterTool           ← executor.py _execute_filter
                    ├─ SortTool             ← executor.py _execute_sort
                    ├─ GroupByTool          ← executor.py _execute_group_by
                    ├─ AddColumnTool        ← executor.py _execute_add_column
                    ├─ UpdateColumnTool     ← executor.py _execute_update_column
                    ├─ AggregateTool        ← executor.py _execute_aggregate
                    ├─ ComputeTool          ← executor.py _execute_compute
                    ├─ PivotTool            ← executor.py _execute_pivot
                    ├─ GenerateFormulasTool ← excel_generator.py
                    ├─ ExportExcelTool      ← oss.py 文件写入 + download URL
                    └─ ClarifyTool          ← 向用户提问（内置，无需外部实现）

  SSE Stream ← each tool invocation yields streaming events
  ThreadTurn ← memory auto-persists after each turn
```

### 核心组件映射

| 旧组件 | 旧职责 | LangChain 等价 |
|--------|--------|----------------|
| `IntentService` + `IntentClassifier` | 意图识别 + 上下文构建 | `ConversationBufferMemory` + Agent 的 ReAct 推理 |
| `ContextService` + `ContextBuilder` | 历史转文本 | `ChatPromptTemplate` + `MessagesPlaceholder` |
| `ExcelProcessor` + 线性 stages | 固定处理管线 | Agent 自主规划的工具调用序列 |
| `StepTracker` | 处理步骤记录 | LangChain `CallbackManager` + `trace` |
| `TurnRepository` | 持久化 | 不变，新增 `save_agent_memory` / `load_agent_memory` |
| `llm_client.py` | LLM 调用封装 | `langchain.chat_models` 封装 |

### 关键设计决策

#### 1. Agent 类型：Tool-calling Agent vs ReAct Agent

**选择：`ConversableAgent`（基于 tool-calling）+ 强制结构化输出**

原因：
- Tool-calling Agent 有强制 schema，LLM 直接输出 `{"tool": "FilterTool", "args": {...}}`，比 ReAct 的文本推理更可靠
- 项目已有明确的操作类型（filter/sort/group_by），适合用 function calling 格式
- LangChain 支持 stream JSON schema，减少解析错误

#### 2. Memory 持久化策略

保留现有 `ThreadTurn` 模型，新增字段存 LangChain message history：

```python
# ThreadTurn 表新增
messages_history: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
# 存 ConversationBufferMemory.to_messages() 的序列化结果
```

每个 `/chat` 请求：
1. 从 DB 加载 `ThreadTurn.messages_history` → `ConversationBufferMemory`
2. Agent 运行，memory 自动累积新消息
3. 请求结束时回写 `messages_history` 到 DB

#### 3. 工具返回格式

所有工具统一返回：
```python
@dataclass
class ToolResult:
    success: bool
    observation: str          # human-readable 摘要
    data: Optional[dict]      # 结构化数据（供后续工具使用）
    error: Optional[str]
    download_url: Optional[str]  # 特殊：ExportExcelTool 专用
```

#### 4. SSE 事件流

```
event=tool_start    { "tool": "FilterTool", "args": {...} }
event=tool_stream   { "delta": "正在按销量列降序排序..." }
event=tool_end      { "tool": "FilterTool", "observation": "...", "data": {...} }
...（多个工具调用）
event=agent_end     { "response": "已完成，按销量排序后标红了前10行" }
event=complete      { "download_url": "..." }
```

#### 5. 澄清（Clarify）机制

`ClarifyTool` 不做真实操作，直接返回一条 `Observation` 要求用户确认：

```python
# 工具返回
ToolResult(
    success=False,
    observation="需要澄清：您想按哪一列排序？可选：销量、金额、日期",
    data={"requires_clarification": True, "options": ["销量", "金额", "日期"]}
)
```

Agent 检测到 `requires_clarification=True`，暂停执行，等待用户下一轮输入。

---

## 升级阶段划分

### Phase 1：基础设施层（Foundation）

**目标：** 搭建 LangChain Agent 核心依赖和基础框架，不改变任何业务逻辑。

| 任务 | 负责人 | 输入 | 输出 |
|------|--------|------|------|
| 1.1 依赖引入 | Agent-Scaffolder | `pyproject.toml` | 添加 `langchain >= 0.3`, `langchain-core`, `langchain-community`, `tiktoken` |
| 1.2 LLM 适配器对齐 | Agent-Scaffolder | `llm_client.py`, `llm_providers/` | `app/engine/llm_adapters/langchain_adapter.py` — 将现有 Provider Registry 适配为 LangChain `ChatModel` |
| 1.3 Memory 持久化模型 | Persistence-Architect | `models/thread.py` | 新增 `ThreadTurn.messages_history: JSONB` 字段 + alembic migration |
| 1.4 基础 Agent 入口 | Pipeline-Architect | `chat.py` | `app/agent/excel_agent.py` — `ExcelAgent` 类，`app/agent/agent_executor.py` — `run()` 方法，路由接入 |
| 1.5 Tool 基类定义 | Tool-Architect | `engine/models.py` | `app/agent/tools/base.py` — `ExcelBaseTool` + `ToolResult` dataclass |

**交付物：** `POST /chat` 路由接入 `ExcelAgent`，但只有一个 `HelloTool`，Agent 能跑通 SSE 流。

---

### Phase 2：工具层（Tooling）

**目标：** 将所有现有操作能力包装为 LangChain Tools，实现"能力不降级迁移"。

| 任务 | 负责人 | 输入 | 输出 |
|------|--------|------|------|
| 2.1 文件读取工具 | Tool-Architect | `excel_parser.py`, `FileCollection` | `app/agent/tools/read_excel.py` — `ReadExcelTool` |
| 2.2 Schema 提取工具 | Tool-Architect | `ReadExcelTool` 输出 | `app/agent/tools/schema.py` — `GetSchemaTool` |
| 2.3 Filter 工具 | Tool-Architect | `executor.py _execute_filter` | `app/agent/tools/filter.py` — `FilterTool` |
| 2.4 Sort 工具 | Tool-Architect | `executor.py _execute_sort` | `app/agent/tools/sort.py` — `SortTool` |
| 2.5 GroupBy 工具 | Tool-Architect | `executor.py _execute_group_by` | `app/agent/tools/group_by.py` — `GroupByTool` |
| 2.6 AddColumn 工具 | Tool-Architect | `executor.py _execute_add_column` | `app/agent/tools/add_column.py` — `AddColumnTool` |
| 2.7 UpdateColumn 工具 | Tool-Architect | `executor.py _execute_update_column` | `app/agent/tools/update_column.py` — `UpdateColumnTool` |
| 2.8 Aggregate 工具 | Tool-Architect | `executor.py _execute_aggregate` | `app/agent/tools/aggregate.py` — `AggregateTool` |
| 2.9 Compute 工具 | Tool-Architect | `executor.py _execute_compute` | `app/agent/tools/compute.py` — `ComputeTool` |
| 2.10 Pivot 工具 | Tool-Architect | `executor.py _execute_pivot` | `app/agent/tools/pivot.py` — `PivotTool` |
| 2.11 Formula 生成工具 | Tool-Architect | `excel_generator.py` | `app/agent/tools/generate_formulas.py` — `GenerateFormulasTool` |
| 2.12 Export 工具 | Tool-Architect | `oss.py` | `app/agent/tools/export.py` — `ExportExcelTool` |
| 2.13 Clarify 工具 | Tool-Architect | 澄清需求 | `app/agent/tools/clarify.py` — `ClarifyTool` |
| 2.14 工具注册表 | Tool-Architect | 以上所有工具 | `app/agent/tools/registry.py` — `ExcelToolRegistry` |

**交付物：** 所有工具独立可测试，Agent 可以调用完整工具链。

---

### Phase 3：上下文与记忆层（Memory）

**目标：** 替换文本拼接式上下文，实现 LangChain 原生记忆管理。

| 任务 | 负责人 | 输入 | 输出 |
|------|--------|------|------|
| 3.1 Memory 加载/保存 | Context-Architect | `turn_repository.py`, `ThreadTurn.messages_history` | `app/agent/memory/buffer.py` — `ConversationBufferMemory` 的 DB 序列化/反序列化 |
| 3.2 Prompt 模板重构 | Context-Architect | `prompt.py` 巨型 prompt | `app/agent/prompts/system.py` — LangChain `ChatPromptTemplate`，按 tool instruction 分块 |
| 3.3 Schema 信息注入 | Context-Architect | `GetSchemaTool` 输出 | `app/agent/prompts/schema_injector.py` — 动态注入表结构到 system prompt |
| 3.4 Token 控制 | Context-Architect | `context_builder.py` | `app/agent/memory/token_manager.py` — 基于 tiktoken 的 context window 管理，自动截断/摘要超长历史 |
| 3.5 上下文连贯性 | Context-Architect | `context_service.py` | 废弃 `_analyze_topic_continuity()` 等脆弱逻辑，由 Agent 自动判断 |

**交付物：** 历史消息正确累积，Agent 能感知前几轮对话内容。

---

### Phase 4：流式与观测层（Streaming & Observability）

**目标：** 让 SSE 事件流准确反映 Agent 推理过程。

| 任务 | 负责人 | 输入 | 输出 |
|------|--------|------|------|
| 4.1 Agent 回调系统 | Pipeline-Architect | LangChain `CallbackManager` | `app/agent/callbacks/sse.py` — `SSEAgentCallback` 实现 `on_tool_start/_end` 等，上报 SSE |
| 4.2 流式输出适配 | Pipeline-Architect | `llm_client.py` async streaming | `app/agent/streaming.py` — Agent 的 `astream_events()` 包装为 SSE `EventSourceResponse` |
| 4.3 step_tracker 对齐 | Pipeline-Architect | `step_tracker.py` | `app/agent/callbacks/step_tracker_adapter.py` — LangChain callback → `ThreadTurn.steps` 的写入适配 |

**交付物：** 前端可实时看到 Agent 在调用哪个工具、输出了什么。

---

### Phase 5：Prompt 工程与调优（Prompt Engineering）

**目标：** 编写清晰、无歧义的 tool description，使 Agent 稳定选中正确工具。

| 任务 | 负责人 | 输入 | 输出 |
|------|--------|------|------|
| 5.1 System Prompt 重写 | Prompt-Engineer | `prompt.py` | `app/agent/prompts/excel_assistant.py` — 简洁的 assistant description + tool instructions |
| 5.2 Tool Examples | Prompt-Engineer | `prompt.py` 内的海量 examples | `app/agent/prompts/examples.py` — 每个 tool 的 `I/O example`，通过 `ExamplesQueryRegistry` 按场景注入 |
| 5.3 拒绝/安全 Prompt | Prompt-Engineer | `parser.py` `LLM_INTENTIONAL_REFUSAL` 逻辑 | 整合为 `app/agent/prompts/safety.py` — 安全边界指令 |
| 5.4 多语言适配 | Prompt-Engineer | 中文项目背景 | System prompt 支持中英文双语，tool observation 输出中文 |

**交付物：** Agent 工具选错率 < 5%，能正确拒绝恶意请求。

---

### Phase 6：集成测试与上线（Integration & Launch）

**目标：** 确保升级后功能完整、性能不降。

| 任务 | 负责人 | 输入 | 输出 |
|------|--------|------|------|
| 6.1 路由切换 | Pipeline-Architect | `chat.py` | 旧路由加 feature flag `USE_AGENT=true`，新路由并行运行，对比输出 |
| 6.2 回归测试套件 | Test-Engineer | 现有 `processor/stages/` 测试 | `tests/agent/` — Agent 端到端测试，覆盖 filter+sort+group_by 等常见组合 |
| 6.3 性能基准 | Test-Engineer | 压测脚本 | 对比：意图分类耗时 + 管线耗时 vs Agent 单次调用耗时 |
| 6.4 前端适配 | Frontend-Architect | `apps/web/app/routes/_auth._app._index.tsx` | SSE 事件类型兼容，`tool_start/end` 等新事件展示 |
| 6.5 灰度上线 | Pipeline-Architect | feature flag | 5% → 20% → 50% → 100% 流量切换 |
| 6.6 旧代码归档 | All | 所有待删除文件 | `archive/` 目录暂存，不直接删除，便于回滚 |

---

## 文件清单

### 新增文件

```
apps/api/app/agent/
├── __init__.py
├── excel_agent.py              # ExcelAgent 主类
├── agent_executor.py           # run() 异步生成器，SSE 事件发射
├── memory/
│   ├── __init__.py
│   ├── buffer.py               # DB 序列化 ConversationBufferMemory
│   └── token_manager.py        # tiktoken-based context window 管理
├── prompts/
│   ├── __init__.py
│   ├── system.py                # ChatPromptTemplate 入口
│   ├── schema_injector.py       # 动态注入表结构
│   ├── excel_assistant.py       # System prompt 主模板
│   ├── examples.py              # Tool examples 注册表
│   └── safety.py                # 安全边界指令
├── tools/
│   ├── __init__.py
│   ├── base.py                  # ExcelBaseTool + ToolResult dataclass
│   ├── registry.py              # ExcelToolRegistry
│   ├── read_excel.py             # ReadExcelTool
│   ├── schema.py                 # GetSchemaTool
│   ├── filter.py                 # FilterTool
│   ├── sort.py                   # SortTool
│   ├── group_by.py               # GroupByTool
│   ├── add_column.py             # AddColumnTool
│   ├── update_column.py          # UpdateColumnTool
│   ├── aggregate.py               # AggregateTool
│   ├── compute.py                 # ComputeTool
│   ├── pivot.py                   # PivotTool
│   ├── generate_formulas.py       # GenerateFormulasTool
│   ├── export.py                  # ExportExcelTool
│   └── clarify.py                 # ClarifyTool
├── callbacks/
│   ├── __init__.py
│   ├── sse.py                     # SSEAgentCallback
│   └── step_tracker_adapter.py   # step_tracker 兼容层
└── llm_adapters/
    ├── __init__.py
    └── langchain_adapter.py      # 现有 Provider Registry → LangChain ChatModel

apps/api/tests/agent/
├── __init__.py
├── conftest.py
├── test_tools/
│   ├── test_filter_tool.py
│   ├── test_sort_tool.py
│   └── ...
├── test_memory/
│   └── test_buffer_memory.py
└── test_excel_agent.py
```

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `apps/api/app/models/thread.py` | `ThreadTurn` 新增 `messages_history: JSONB` 字段 |
| `apps/api/app/api/routes/chat.py` | 路由接入 `agent_executor.run()`，feature flag 控制新旧逻辑 |
| `apps/api/app/engine/llm_client.py` | 保留，新增 `langchain_adapt()` 方法返回 LangChain ChatModel |
| `apps/api/app/engine/excel_parser.py` | 新增 `FileCollection.to_schema_dict()` 供 `GetSchemaTool` 调用 |
| `apps/api/app/engine/executor.py` | 各 `_execute_*` 方法提取为独立函数，供 Tool 调用（不去除原方法） |
| `apps/api/app/engine/excel_generator.py` | `ExcelFormulaGenerator` 提取为可导入函数 |
| `apps/api/app/persistence/turn_repository.py` | 新增 `save_messages_history()`, `load_messages_history()` |
| `apps/api/app/api/main.py` | 可选：新增 `/agent/chat` 路由用于并行测试 |
| `apps/api/app/main.py` | 可选：LangChain 全局 callback handler 注册 |
| `apps/api/pyproject.toml` | 新增 `langchain`, `langchain-core`, `langchain-community`, `tiktoken` 依赖 |
| `apps/api/app/services/intent_service.py` | Phase 6 后可删除，或降级为非必须服务 |
| `apps/api/app/services/context_service.py` | Phase 6 后可删除 |
| `apps/api/app/engine/context_builder.py` | Phase 6 后可删除 |
| `apps/api/app/engine/intent_classifier.py` | Phase 6 后可删除 |
| `apps/api/app/processor/excel_processor.py` | Phase 6 后可删除（工具化后不再需要线性管线） |
| `apps/api/app/processor/stages/generate_validate.py` | 同上 |
| `apps/api/app/processor/stages/execute.py` | 同上 |
| `apps/api/app/processor/stages/analysis.py` | 同上 |
| `apps/api/app/services/chat_service.py` | Phase 6 后可删除 |
| `apps/api/app/services/chat_stream.py` | Phase 6 后可删除 |
| `apps/api/app/services/processing_pipeline.py` | Phase 6 后可删除 |
| `apps/api/app/services/analysis_stream.py` | Phase 6 后可删除 |
| `apps/web/app/routes/_auth._app._index.tsx` | SSE 事件类型扩展（`tool_start`, `tool_end`, `agent_thought`） |
| `apps/api/app/engine/prompt.py` | 大幅精简，废弃巨型 prompt 模板 |
| `apps/api/app/engine/models.py` | 新增 `ToolResult` dataclass 复用给工具层 |

### 删除文件（Phase 6 结束后归档）

- `apps/api/app/engine/intent_classifier.py`
- `apps/api/app/services/intent_service.py`
- `apps/api/app/services/context_service.py`
- `apps/api/app/engine/context_builder.py`
- `apps/api/app/services/chat_service.py`
- `apps/api/app/services/chat_stream.py`
- `apps/api/app/services/processing_pipeline.py`
- `apps/api/app/services/analysis_stream.py`
- `apps/api/app/processor/excel_processor.py`
- `apps/api/app/processor/stages/generate_validate.py`
- `apps/api/app/processor/stages/execute.py`
- `apps/api/app/processor/stages/analysis.py`
- `apps/api/app/engine/prompt.py`（内容迁移到 `app/agent/prompts/`）

---

## Agent Team 角色定义

| 角色 | 职责 | 技能要求 |
|------|------|----------|
| **Agent-Scaffolder** | Phase 1 — 搭建 LangChain 基础：依赖安装、LLM 适配器、Agent 入口、Memory 模型变更、路由接入 | 熟悉 LangChain 核心概念（Agent、Tool、Memory、Callback）、FastAPI 依赖注入 |
| **Tool-Architect** | Phase 2 — 负责所有 Tools 的设计与实现：每个工具对应一个文件，核心是调用现有 executor 函数并包装 ToolResult | 熟悉 `executor.py` 各 `_execute_*` 方法的签名和副作用，以及 LangChain `@tool` 装饰器或 `BaseTool` 基类 |
| **Context-Architect** | Phase 3 — 负责 Memory 持久化和 Token 控制：DB ↔ ConversationBufferMemory 互转、tiktoken 截断策略 | 熟悉 LangChain Memory 体系、tiktoken、SQLAlchemy JSONB |
| **Pipeline-Architect** | Phase 1 + Phase 4 — 负责 Agent 执行层和 SSE 流式：ExcelAgent 主类、SSE 回调适配、step_tracker 对齐、路由 feature flag | 熟悉 LangChain AgentExecutor、SSE (sse-starlette)、async generator |
| **Prompt-Engineer** | Phase 5 — 负责所有 Prompt 工程：system prompt 重写、tool description 撰写、examples 管理、安全指令 | 熟悉 LangChain PromptTemplate、有 LLM tool-calling 调优经验、懂 Excel 数据处理领域知识 |
| **Test-Engineer** | Phase 6 — 负责测试：端到端测试套件、性能基准、回归对比 | 熟悉 pytest、异步测试、httpx |

---

## 关键风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Agent 工具选错 | 处理结果错误 | Phase 5 大量 examples + Phase 6 回归测试覆盖每个 tool |
| Token 超出限制 | 内存爆炸/请求失败 | Phase 3 token_manager 自动截断 + 摘要模式 |
| LangChain 版本升级破坏 | 维护成本 | 锁定 `langchain >= 0.3, < 0.4` 版本范围 |
| 现有 Provider 不兼容 | Agent 无法调用 | Phase 1 先做适配器验证，不兼容则换用 LangChain OpenAI 官方 adapter |
| 澄清循环死锁 | Agent 反复要求澄清 | `ClarifyTool` 最多触发 2 次，超时强制用默认项 |
| 性能下降 | 响应变慢 | Phase 6 性能基准测试，若超标则启用 intent pre-classification 优化 |

---

## 依赖安装（Phase 1 首步）

```bash
# apps/api/pyproject.toml 新增
langchain >= 0.3.0
langchain-core >= 0.3.0
langchain-community >= 0.3.0
tiktoken >= 0.7.0
```

LangChain 版本选 0.3.x（截至 2025 Q4 为稳定版），优先使用 `langchain-openai` 若使用 OpenAI 模型，若用自定义 provider 用 `langchain-community` 中对应 adapter。
