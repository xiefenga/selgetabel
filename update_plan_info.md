# Update Plan Info — LangChain 升级避雷与铺垫信息

> 本文件为后续构建新升级方案提供铺垫、补充与避雷指导。**不是**升级方案本身。

---

## 一、当前系统状态（升级后）

### 1.1 成功保留下来的旧代码

| 组件 | 路径 | 状态 |
|------|------|------|
| ExcelExecutor | `app/engine/executor.py` | ✅ 完整保留，所有 Operation 类（FilterOp、SortOp 等）和 execute() 方法均在 |
| JSON 解析器 | `app/engine/parser.py` | ✅ 完整保留 |
| 公式生成器 | `app/engine/excel_generator.py` | ✅ 完整保留 |
| LLM Prompt | `app/engine/prompt.py` | ✅ 完整保留 |
| SSE 流式处理 | `app/services/processor_stream.py` | ✅ 完整保留 |

**关键结论：旧的 processor/ 管线（generate_validate、execute 等 stage）虽已删除，但核心执行逻辑 `ExcelExecutor` 完好无损。这是最重要的资产，新方案应直接复用。**

### 1.2 已升级为 LangChain 架构的部分

| 组件 | 路径 | 说明 |
|------|------|------|
| ExcelAgent | `app/agent/excel_agent.py` | Agent 主类，调用 AgentExecutor |
| AgentExecutor | `app/agent/agent_executor.py` | 包含 run()（LangGraph）和 run_simple()（Phase 1 fallback） |
| 工具注册表 | `app/agent/tools/registry.py` | 当前注册了 17 个独立工具 |
| 工具基类 | `app/agent/tools/base.py` | `arun()` 返回 `ToolMessage`（LangGraph 兼容） |
| Memory | `app/agent/memory/db_buffer.py` | 使用 `langchain_classic.memory.ConversationBufferMemory` |

### 1.3 已删除的旧代码（不可恢复）

| 组件 | 路径 | 说明 |
|------|------|------|
| processor/ | `app/processor/` | 整个目录已删除（含 excel_processor.py、stages/） |
| services/ 部分 | `app/services/chat_service.py` 等 | 已删除 |
| intent_classifier | `app/engine/intent_classifier.py` | 已删除 |

---

## 二、已遇 Bug 与修复记录

以下每个 bug 都有完整的问题现象、根因和修复方案记录，建议在新方案中**预先规避**而非事后修复。

### Bug 1：LangGraph astream key 路径错误

**问题现象：** LLM 回复时，SSE 流式事件正常发出，但前端始终显示"处理中"无法结束。

**根因：** LangGraph 的 `astream()` yield 的不是 `{"messages": [...]}`，而是 `{"model": {"messages": [...]}}`。代码中错误地使用：

```python
# ❌ 错误写法
messages = state_event.get("messages", [])

# ✅ 正确写法
model_state = state_event.get("model", {})
messages = model_state.get("messages", [])
```

**遇到位置：** `agent_executor.py` 的 `consume_agent()` 函数内。

**避雷：** 任何使用 LangGraph `astream()` 的代码，都需要从 `state_event.get("model", {})` 取 messages，不要直接从 state_event 顶层取。

---

### Bug 2：直接 LLM 回复缺少 tool_start 事件

**问题现象：** LLM 直接回复文本（无工具调用）时，SSE 流开始，但前端"处理中"步骤卡住无法结束。

**根因：** SSE 前端根据 `tool_start` 事件确定当前正在运行哪个步骤并渲染 UI。若 LLM 直接回复，只有 `tool_stream` 没有 `tool_start`，前端无法匹配运行中的步骤。

**修复：** 在检测到 LLM 最终回复（无 tool_calls 的 AIMessage）时，手动发送 `tool_start` 事件：

```python
await self._event_queue.put(StreamEvent(
    event="tool_start",
    data={"tool": "chat", "args": {}}  # tool 名 "chat" 会被前端当作纯文本渲染
))
```

**避雷：** 所有 Agent 回复路径（包括纯文本回复）都需要先发 `tool_start`，再发 `tool_stream`，最后发 `tool_end`。

---

### Bug 3：turn.response_text SSE 结束后未持久化

**问题现象：** 对话刷新后聊天记录消失，只剩用户问题。

**根因：** SSE 完成后，`turn.response_text` 未被更新，导致前端读取的是空值或旧值。

**修复：** 在 `chat.py` 的 SSE consumer 循环结束后，更新持久化：

```python
current_turn.response_text = response_text
await db.commit()
```

**避雷：** 任何 SSE 流式响应，响应文本需要在 SSE 完成后显式持久化，不能依赖流式过程自动保存。

---

### Bug 4：流式输出速度过快（10ms/字符）

**问题现象：** 流式输出几乎瞬间完成，用户感觉不到逐字输出效果。

**根因：** 逐字符发送，10ms/字符，对短回复几乎无延迟感知。

**修复：** 改为 10 字符一块，50ms 间隔：

```python
chunk_size = 10
delay_per_chunk = 0.05
for start in range(0, len(content), chunk_size):
    chunk = content[start:start + chunk_size]
    await self._event_queue.put(StreamEvent(...))
    if start + chunk_size < len(content):
        await asyncio.sleep(delay_per_chunk)
```

**避雷：** 流式渲染需要平衡延迟和实时性，单纯逐字发送对短回复无意义。

---

### Bug 5：ReadExcelTool._arun() 缺少 user_id

**问题现象：** LLM 调用 `read_excel(file_ids=[...])` 但文件加载失败，提示"文件不存在或无权访问"。

**根因：** LLM 不知道传递 `user_id`，且 `_arun()` 需要 `user_id` 查询 DB 中的文件记录。直接传递会导致权限验证失败。

**修复：** 通过 `registry.set_context()` 注入 user_id 到工具实例，工具从 `self._context_user_id` 读取：

```python
# registry.set_context(user_id=..., db=..., file_collection=...)
# 工具内部：
user_id = user_id or getattr(self, "_context_user_id", "") or ""
```

**避雷：** 工具的隐式参数（user_id、db session）不要依赖 LLM 传递，通过 context 注入是更可靠的方式。

---

### Bug 6：Table.__getattr__ 拦截了所有属性访问

**问题现象：** 调用 `table.get_sample_rows(3)` 报 AttributeError 或返回意外结果。

**根因：** `Table` 类的 `__getattr__` 拦截了所有属性访问（包括方法调用），将列名访问作为数据访问处理。当 LLM 或代码尝试调用 `get_sample_rows()` 方法时，被误解析为列访问。

**修复：** 绕过 `__getattr__`，直接访问底层数据：

```python
# ❌ 被 __getattr__ 拦截
samples = table.get_sample_rows(3)

# ✅ 直接访问 _data
samples = table._data.head(3).values.tolist()
```

**避雷：** `Table` 对象的方法调用需要小心，所有数据访问都应通过 `table._data`（pandas DataFrame）进行。

---

### Bug 7：LLM"看不见"上传的文件

**问题现象：** 上传了 Excel 文件后，LLM 回复"请先上传文件"或无法操作数据。

**根因：** `file_ids` 只存在于 Python 参数中，未传递给 LLM 的上下文。LLM 无法知道当前对话有哪些文件可用。

**修复：** 在 SystemMessage 中显式告知 LLM：

```python
if file_collection:
    system_parts.append(
        f"【重要】当前对话已上传 {len(file_ids)} 个文件。"
        "文件已加载到内存，你可以直接调用 filter/sort/drop_columns 等工具操作数据。"
    )
else:
    system_parts.append(
        f"【重要】当前对话已上传 {len(file_ids)} 个文件，file_ids: {file_ids}。"
        "在执行任何数据操作之前，你必须先调用 read_excel 工具读取文件。"
    )
```

**避雷：** 任何上传的文件、上下文状态都需要在 SystemMessage 中显式告知 LLM，不能依赖隐式状态。

---

### Bug 8：LLM"无法引用"对话历史

**问题现象：** 多轮对话中，LLM 不知道之前的对话内容，无法引用历史信息。

**根因：** 历史消息虽然传入了，但 LLM 不知道这些消息代表对话历史。

**修复：** 添加说明：

```python
if historical_messages:
    system_parts.append("以下是我们之前的对话历史，你可以引用其中的信息。")
```

**避雷：** 历史消息传入时需要配合说明性 SystemMessage，让 LLM 理解上下文。

---

### Bug 9：FileCollection 无法通过 tool_call 参数传递

**问题现象：** 当 17 个工具链式调用时，每个工具都需要 `file_collection`，但 LLM 只能传递文本，无法传递 Python 对象。

**根因：** LangChain Agent 的 tool_call 机制是基于文本的（LLM 输出 JSON 格式的工具名和参数），无法序列化传递复杂的 FileCollection 对象。

**修复：** 采用 per-turn 预加载模式：

```python
# 在每个请求开始时预加载 FileCollection
file_collection = await self._load_file_collection(file_ids, user_id, db)

# 通过 registry.set_context() 注入到所有工具
self.tool_registry.set_context(
    user_id=user_id,
    db=db,
    file_collection=file_collection,  # 所有工具共享同一个实例
)
```

**避雷：** 不要依赖 LLM 通过 tool_call 参数传递 FileCollection 等复杂对象。通过注册表 context 注入是唯一可靠方案。

---

## 三、设计错误回顾

### 错误 1（核心）：17 个独立工具 vs JSON 操作数组

**问题：** 将每个 Excel 操作（filter、sort、drop_columns 等）都实现为独立工具。

**弊端：**
1. LLM 需要在多轮对话中多次调用工具，FileCollection 在工具间无法共享（每个工具独立创建）
2. 工具链过长导致错误累积
3. LLM 需要理解"先 read_excel 再 filter 再 sort"的操作顺序，增加 prompt 负担
4. 丢失了旧管线的"JSON 操作数组"优势：一次生成、一次验证、执行端完整控制

**正确方向：**
- `process_table` 工具接受 JSON 操作数组（与旧管线完全兼容）
- 底层直接调用现有的 `ExcelExecutor.execute(operations)`
- 旧管线的 generate_validate stage 本质是"LLM 生成 + 验证"，这在 tool 内部实现即可

### 错误 2：丢弃了 processor/ 管线的思路

**问题：** 删除 processor/ 时，连带丢弃了"分阶段处理"的思想。

**保留价值：**
- generate_validate stage 的"生成 + 验证"分离设计是有意义的
- 可以在 tool 内部实现：先用 LLM 生成 JSON 操作，再用 parser 验证格式
- ExcelExecutor.execute() 是完整保留的，无需重建

### 错误 3：未充分利用 ExcelExecutor

**现状：** `ExcelExecutor` 及其所有 `Operation` 类完全保留，但新工具链完全未使用它们。每个新工具（如 filter.py、sort.py）都自己实现了一套逻辑。

**正确方向：** 所有表格操作工具应委托给 `ExcelExecutor`，而不是自己实现。

---

## 四、关键架构决策（经验证可行）

以下决策已通过实际验证，建议在新方案中继承：

### 4.1 arun() 必须返回 ToolMessage

LangGraph 的 ToolNode 调用 `tool.ainvoke()` → `tool.arun()` → 期望返回 `ToolMessage`。

```python
# app/agent/tools/base.py
def arun(self, **kwargs) -> ToolMessage:
    result = self._arun(**kwargs)
    return ToolMessage(content=str(result.observation), name=self.name)
```

### 4.2 langchain_classic 的 Memory

项目使用 `langchain_classic.memory.ConversationBufferMemory`（v1.0.3），不是 `langchain.memory`。

```python
from langchain_classic.memory import ConversationBufferMemory
```

### 4.3 SystemMessage 注入关键上下文

以下信息**必须**通过 SystemMessage 告知 LLM，不能依赖隐式推断：
- 当前对话上传的文件（file_ids）
- 文件是否已预加载到内存
- 对话历史的存在和含义
- 工具调用约束（如"文件已预加载，请直接调用操作工具"）

### 4.4 SSE 事件序列规范

每个工具调用必须严格按顺序发送：

```
tool_start → tool_stream(多次) → tool_end
```

直接 LLM 回复也需要 `tool_start`（tool 名用 "chat"），让前端能匹配步骤。

### 4.5 registry.set_context() 模式

这是解决"LLM 无法传递复杂对象"问题的标准方式：

```python
tool_registry.set_context(
    user_id=user_id,
    db=db_session,
    file_collection=file_collection,
)
# 每个工具通过 self._context_* 访问
```

---

## 五、新升级方案建议方向

> 以下不是具体方案，仅指出正确方向，避免再走弯路。

1. **工具数量控制在 5-6 个**：hello、clarify、read_excel、analyze_data、process_table、export_excel
2. **process_table 内部调用 ExcelExecutor**：复用所有现有 Operation 类
3. **保留 generate_validate 思想**：在 process_table 内部，LLM 生成 JSON → parser 验证 → executor 执行
4. **analyze_data 单独处理 L1-L4 分析**：按 README.zh-CN.md 的四级分析体系实现
5. **不丢弃任何旧 processor/ 代码思路**：ExcelExecutor 是核心资产，必须保留
6. **Phase 1 fallback 保留**：use_full_agent=False 时走简化流程，兼容无 LLM 场景

---

## 六、需要补充的信息

以下信息需要根据新方案进一步确认：

1. **clarify tool 的具体边界**：当用户意图不明确时，clarify 应询问哪些维度？表格选择？操作类型？分析目标？
2. **analyze_data 的 L1-L4 实现细节**：每个 level 的 prompt 策略、是否需要单独的 validation stage
3. **export_excel 的触发条件**：是 process_table 完成后自动触发，还是需要用户确认？
4. **多文件场景**：当用户上传多个文件时，read_excel 是否需要支持指定文件？还是总是全部加载？
5. **phase 分界**：use_full_agent=False 的场景具体有哪些？是否保留完整的手动工具链作为 fallback？
