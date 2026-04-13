# LangChain Agent 升级方案

## 背景与目标

### 现状痛点

| 问题 | 位置 | 表现 |
|------|------|------|
| 硬编码意图分类 | `chat.py:116-153` | 三选一分支（chat/analysis/processing），逻辑完全耦合 |
| 意图识别阻塞调用 | `intent_service.py:67` | 每次对话先调一次 LLM 分类，再调一次 LLM 处理 = 至少 2 次 LLM 调用 |
| 上下文文本拼接 | `context_builder.py:40-365` | 历史消息转成字符串塞进 prompt，token 浪费且上限低 |
| 固定管线 | `excel_processor.py:70-82` | `_build_stages()` 只返回线性 `[GenerateValidateStage, ExecuteStage]`，无法动态增减 |
| 无工具抽象 | 无 | `filter/sort/group_by` 等操作用 if/else 散落在 `executor.py` 中，无法被 LLM 直接调用 |
| 旧模块残留隐患 | 多个旧服务文件 | `intent_classifier.py`、`context_builder.py` 等旧模块持续与新逻辑共存，维护负担极重 |
| Stage 配置缺失静默失败 | `llm_config.py` | 缺少关键 stage（如 intent、chat）时系统静默失败，无启动校验 |
| Python 模块语法错误静默失败 | `chat.py` | `async def stream()` 定义两次导致模块加载失败，路由未注册，请求关闭无日志 |

### 升级目标

1. **Agent 化** — 用 LangChain ConversableAgent (tool-calling) 替代旧意图识别 + 线性管线
2. **工具可观测** — 每步工具调用都有 `step_tracker` 级别的记录，支持流式 SSE 上报
3. **上下文结构化** — 用 LangChain `ConversationBufferMemory` 管理对话历史，不再文本拼接
4. **彻底删除旧代码** — 不留 Feature Flag，不搞双轨，旧代码直接归档删除
5. **启动校验** — 缺失 LLM stage 配置时启动时报错，不静默失败

---

## 架构原则

### 核心原则

1. **一次切换，不留后路**：直接替换 `/chat` 路由，旧代码归档删除，不用 Feature Flag 维持双轨
2. **Phase 内完成后再下一 Phase**：每个 Phase 有明确验收标准，未通过不允许进入下一 Phase
3. **旧代码是负担不是保险**：不在旧模块上继续打补丁，不继承旧设计的包袱
4. **启动即校验**：LLM stage 配置、数据库模型、关键依赖在启动时全部校验，缺失则报错退出
5. **每个方法签名有据可查**：新增方法必须在 turn_repository.py 等现有文件中实际存在，不凭空假设

### 迁移策略

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5 ──► Phase 6
  │           │           │           │           │           │           │
  ▼           ▼           ▼           ▼           ▼           ▼           ▼
 启动校验    新架构      工具层      Memory      SSE 流式   Prompt     删除旧代码
 (新增)     最小运行    串联       持久化      完整      工程化     回归通过
```

**Phase 0 为新增，与 Phase 1 并行完成。Phase 1-5 只写新代码，不修改旧代码（旧代码仅归档引用）。Phase 6 末批量删除旧代码。**

---

## 整体架构

```
POST /chat
  └─► ExcelAgentExecutor
        ├─► ConversationBufferMemory (惰性加载，从 ThreadTurn.messages_history 恢复)
        ├─► ChatPromptTemplate (system prompt + memory messages)
        └─► ConversableAgent (tool-calling)
              └─► Tools (每个 = 原有 executor 能力的纯函数包装)
                    ├─ ReadExcelTool        ← excel_parser.py + FileCollection 加载
                    ├─ GetSchemaTool        ← 从 FileCollection 提取表结构
                    ├─ FilterTool           ← executor.py execute_filter 纯函数
                    ├─ SortTool             ← executor.py execute_sort 纯函数
                    ├─ GroupByTool          ← executor.py execute_group_by 纯函数
                    ├─ AddColumnTool        ← executor.py execute_add_column 纯函数
                    ├─ UpdateColumnTool     ← executor.py execute_update_column 纯函数
                    ├─ AggregateTool         ← executor.py execute_aggregate 纯函数
                    ├─ ComputeTool           ← executor.py execute_compute 纯函数
                    ├─ PivotTool             ← executor.py execute_pivot 纯函数
                    ├─ GenerateFormulasTool  ← excel_generator.py 纯函数
                    ├─ ExportExcelTool        ← oss.py 文件写入 + download URL
                    └─ ClarifyTool           ← 向用户提问（内置）

  SSE Stream ← each tool invocation yields streaming events
  ThreadTurn.messages_history ← memory auto-persists after each turn
```

### 旧架构到新架构的映射

| 旧组件 | 新架构替代 | 状态 |
|--------|-----------|------|
| `IntentService` + `IntentClassifier` | 直接删除，ConversableAgent 自己决定工具 | **删除** |
| `ContextService` + `ContextBuilder` | LangChain `ConversationBufferMemory` | **删除** |
| `ExcelProcessor` + 线性 stages | ConversableAgent 动态工具调用 | **删除** |
| `StepTracker` | LangChain `CallbackManager` + `SSEAgentCallback` | **替换** |
| `TurnRepository` | 不变；新增 `get_or_create_thread()`, `get_latest_turn()`, `save_messages_history()`, `load_messages_history()` | **修改** |
| `llm_client.py` | 删除，替换为 `langchain_llm.py` (`RegistryChatModel`) | **删除** |
| `chat_stream.py` | 不存在了，统一由 `agent_executor.run()` 管理 | **删除** |
| `analysis_stream.py` | `AnalyzeTool` | **删除** |
| `processing_pipeline.py` | 不存在了，工具调用替代管线 | **删除** |
| `intent_service.py` | 不存在了 | **删除** |
| `context_service.py` | 不存在了 | **删除** |
| `context_builder.py` | 不存在了 | **删除** |

---

## Phase 0：启动校验（新增，与 Phase 1 并行）

**目标：确保系统启动时所有关键配置就位，缺失则立即报错退出。**

### 0.1 LLM Stage 路由校验

```python
# app/core/startup_validation.py

from typing import Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

REQUIRED_STAGES: Dict[str, str] = {
    "chat": "纯文本对话（无文件时）",
    "generate": "JSON 操作生成",
    "analyze": "数据分析",
    "execute": "操作执行",
}

async def validate_llm_stage_configs(db: AsyncSession) -> None:
    """启动时校验 LLM stage 路由配置，缺失则报错退出"""
    from app.models.llm import LLMStageRoute

    result = await db.execute(
        select(LLMStageRoute).where(LLMStageRoute.is_active.is_(True))
    )
    routes = {r.stage: r for r in result.scalars().all()}

    missing = [f"  - {stage}: {desc}" for stage, desc in REQUIRED_STAGES.items() if stage not in routes]
    if missing:
        raise RuntimeError(
            f"LLM stage 路由未配置，请在管理后台配置以下 stage：\n" + "\n".join(missing)
        )

    print(f"✅ LLM stage 路由校验通过: {list(routes.keys())}")
```

### 0.2 数据库模型校验

```python
async def validate_database_schema(db: AsyncSession) -> None:
    """检查必要的数据库字段是否存在"""
    from sqlalchemy import inspect

    inspector = inspect(db.bind)
    columns = [c["name"] for c in inspector.get_columns("thread_turns")]
    if "messages_history" not in columns:
        raise RuntimeError(
            "缺少字段 ThreadTurn.messages_history，请先执行迁移：\n"
            "uv run alembic revision --autogenerate -m 'add messages_history to thread_turns'\n"
            "uv run alembic upgrade head"
        )
    print("✅ 数据库模型校验通过")
```

### 0.3 TurnRepository 方法补全

**Phase 0 必须同时在 `turn_repository.py` 中新增以下方法**（后续 Phase 依赖这些方法，遗漏会导致 Phase 1 上线即崩溃）：

```python
# app/persistence/turn_repository.py 新增

async def get_or_create_thread(
    self,
    user_id: UUID,
    thread_id: Optional[UUID],
    initial_query: str,
) -> tuple[Thread, bool]:
    """
    获取或创建线程。

    Args:
        user_id: 用户 ID
        thread_id: 线程 ID（None 表示创建新线程）
        initial_query: 初始查询（用于生成标题）

    Returns:
        (Thread, is_new): 线程对象 + 是否是新创建
    """
    if thread_id:
        existing = await self.get_thread(thread_id, user_id)
        if existing:
            return existing, False

    # 创建新线程
    title = self._generate_thread_title(initial_query)
    thread = await self.create_thread(user_id, title)
    return thread, True

def _generate_thread_title(self, query: str) -> str:
    """生成线程标题（取查询前3个词）"""
    words = query.strip().split()
    title = " ".join(words[:3])[:50]
    return title or "新对话"


async def get_latest_turn(self, thread_id: UUID) -> Optional[ThreadTurn]:
    """
    获取线程最新的一个 Turn。

    Args:
        thread_id: 线程 ID

    Returns:
        最新 Turn 或 None（线程无 Turn 时）
    """
    turns = await self.get_thread_turns(thread_id, limit=1)
    return turns[0] if turns else None


async def save_messages_history(
    self,
    turn_id: UUID,
    messages: list[dict],
) -> None:
    """
    保存对话历史到 Turn。

    Args:
        turn_id: Turn ID
        messages: [{"role": "user"|"assistant", "content": str}] 列表
    """
    turn = await self.get_turn(turn_id)
    if not turn:
        logger.warning(f"save_messages_history: turn {turn_id} 不存在，跳过")
        return
    turn.messages_history = {"messages": messages}
    flag_modified(turn, "messages_history")
    await self.flush()

async def load_messages_history(
    self,
    thread_id: UUID,
) -> list[dict]:
    """
    从线程最新 Turn 加载对话历史。

    Args:
        thread_id: 线程 ID

    Returns:
        [{"role": ..., "content": ...}] 列表，空列表表示无历史
    """
    turn = await self.get_latest_turn(thread_id)
    if not turn or not turn.messages_history:
        return []
    return turn.messages_history.get("messages", [])


async def flush(self) -> None:
    """Flush 当前 session（不 commit）"""
    await self.db.flush()
```

### 0.4 注册到 lifespan

```python
# app/main.py

@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.startup_validation import validate_llm_stage_configs, validate_database_schema
    from app.core.database import AsyncSessionLocal

    print(f"{get_product_name()} API v{__version__}  {__build_time__}")

    async with AsyncSessionLocal() as db:
        await validate_database_schema(db)
        await validate_llm_stage_configs(db)

    yield
    print("应用正在关闭...")
```

### 0.5 交付物

- 启动时校验全部通过：进程输出 `✅ 数据库模型校验通过` + `✅ LLM stage 路由校验通过`
- 任意一项缺失：进程退出，报错信息清晰告知缺少什么以及如何修复
- `turn_repository.py` 新增 `get_or_create_thread()`, `get_latest_turn()`, `save_messages_history()`, `load_messages_history()`, `flush()`

---

## Phase 1：基础设施层（Foundation）

**目标：搭建 LangChain Agent 核心依赖和基础框架，跑通最小 SSE 流（HelloTool + ClarifyTool）。**

### 1.1 依赖引入

```bash
cd apps/api
uv add langchain>=0.3.0 langchain-core>=0.3.0 langchain-community>=0.3.0 tiktoken>=0.7.0
uv run python -c "import langchain; import tiktoken; print('依赖 OK')"
```

### 1.2 LLM 适配器（替换旧 `llm_client.py`）

**删除旧 `llm_client.py`**，新建 `app/engine/llm_adapters/langchain_adapter.py` 和 `app/engine/langchain_llm.py`：

```python
# app/engine/llm_adapters/langchain_adapter.py
"""Provider Registry → LangChain ChatModel 适配层"""

from typing import Optional
from langchain.chat_models import BaseChatModel
from langchain.schema import BaseMessage, AIMessage, HumanMessage, SystemMessage, BaseOutputParser
from app.engine.llm_providers import ProviderRegistry
from app.engine.llm_types import LLMStageConfig, LLMRequest

class RegistryChatModel(BaseChatModel):
    """将 Provider Registry 适配为 LangChain BaseChatModel"""

    stage_config: LLMStageConfig

    @property
    def _llm_type(self) -> str:
        return f"registry_{self.stage_config.provider.type}"

    @property
    def _identifying_params(self) -> dict:
        return {"model": self.stage_config.model.model_id}

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        **kwargs,
    ) -> AIMessage:
        registry = ProviderRegistry()
        adapter = registry.get_adapter(self.stage_config.provider)

        llm_messages = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                llm_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                llm_messages.append({"role": "assistant", "content": msg.content})
            elif isinstance(msg, SystemMessage):
                llm_messages.append({"role": "system", "content": msg.content})

        request = LLMRequest(
            model_id=self.stage_config.model.model_id,
            messages=llm_messages,
            temperature=self.stage_config.model.defaults.get("temperature", 0),
            max_tokens=self.stage_config.model.defaults.get("max_tokens"),
            extra_params={},
        )

        response = adapter.complete(request)
        return AIMessage(content=response.content)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        **kwargs,
    ) -> AIMessage:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self._generate(messages, stop))

    def _create_streaming_adapter(self):
        """
        创建流式适配器（用于 SSE streaming）。
        返回一个同步 generator: (delta: str, full_content: str)
        """
        registry = ProviderRegistry()
        adapter = registry.get_adapter(self.stage_config.provider)

        def gen(messages: list[dict]):
            request = LLMRequest(
                model_id=self.stage_config.model.model_id,
                messages=messages,
                temperature=self.stage_config.model.defaults.get("temperature", 0),
                extra_params={},
            )
            full = ""
            for chunk in adapter.stream(request):
                full = chunk.full_content
                yield chunk.delta, full
        return gen
```

```python
# app/engine/langchain_llm.py
"""LangChain ChatModel 全局访问接口"""

from typing import Dict
from app.engine.llm_adapters.langchain_adapter import RegistryChatModel
from app.engine.llm_types import LLMStageConfig
from app.services.llm_config import load_stage_configs
from app.core.database import AsyncSessionLocal
from sqlalchemy import select
from app.models.llm import LLMStageRoute

_chat_model_cache: Dict[str, RegistryChatModel] = {}


async def get_langchain_chat_model(
    stage: str,
    db: AsyncSession,
) -> RegistryChatModel:
    """
    获取指定 stage 的 LangChain ChatModel（module-level 缓存）。

    Args:
        stage: stage 名称（如 "chat", "generate"）
        db: AsyncSession（用于加载配置）

    Returns:
        RegistryChatModel 实例
    """
    if stage in _chat_model_cache:
        return _chat_model_cache[stage]

    # 从 DB 加载 stage 配置
    result = await db.execute(
        select(LLMStageRoute).where(LLMStageRoute.stage == stage)
    )
    route = result.scalar_one_or_none()
    if not route:
        raise ValueError(f"Stage '{stage}' 未配置，请在管理后台配置")

    provider_result = await db.execute(
        select(LLMProvider).where(LLMProvider.id == route.provider_id)
    )
    # ...（加载 provider 和 model 的完整逻辑，参考 llm_config.py）
    # 此处复用 load_stage_configs 的逻辑，只是返回 RegistryChatModel 而非 LLMStageConfig

    chat_model = RegistryChatModel(stage_config=stage_config)
    _chat_model_cache[stage] = chat_model
    return chat_model
```

**注意：`get_langchain_chat_model()` 是 Phase 1 新增的函数，与旧 `get_llm_client()` 完全独立。旧 `get_llm_client()` 在 Phase 6 归档删除。**

### 1.3 Memory 持久化模型（DB 层）

在 `ThreadTurn` 中新增字段：

```python
# app/models/thread.py

messages_history: Mapped[Optional[dict]] = mapped_column(
    JSONB,
    nullable=True,
    default=dict,
    comment="LangChain ConversationBufferMemory 序列化结果"
)
```

```bash
uv run alembic revision --autogenerate -m "add messages_history to thread_turns"
uv run alembic upgrade head
```

### 1.4 Tool 基类

```python
# app/agent/tools/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Any, Coroutine
from langchain.tools import BaseTool

@dataclass
class ToolResult:
    """工具执行结果（统一格式）"""
    success: bool
    observation: str = ""           # human-readable 摘要
    data: Optional[dict] = None      # 结构化数据（供后续工具使用）
    error: Optional[str] = None
    download_url: Optional[str] = None


class ExcelBaseTool(BaseTool, ABC):
    """Excel 工具基类"""

    name: str
    description: str

    def _run(self, **kwargs) -> ToolResult:
        raise NotImplementedError("ExcelBaseTool 只支持异步接口，请使用 _arun")

    @abstractmethod
    async def _arun(self, **kwargs) -> ToolResult:
        """异步执行接口，所有工具必须实现"""
        pass

    async def run(self, **kwargs) -> ToolResult:
        """LangChain BaseTool 要求的异步 run 实现"""
        return await self._arun(**kwargs)
```

### 1.5 HelloTool（Phase 1 验收用）

```python
# app/agent/tools/hello.py

from app.agent.tools.base import ExcelBaseTool, ToolResult

class HelloTool(ExcelBaseTool):
    name = "hello"
    description = (
        "打招呼用。当用户只是闲聊、问候或说「你好」时调用此工具。 "
        "参数 greeting: str = '你好'。返回问候语。"
    )

    async def _arun(self, greeting: str = "你好") -> ToolResult:
        return ToolResult(
            success=True,
            observation=f"{greeting}！我是 Excel 智能助手，可以帮你处理数据分析、排序、筛选等操作。有什么我可以帮你的吗？"
        )
```

### 1.6 ClarifyTool

```python
# app/agent/tools/clarify.py

from app.agent.tools.base import ExcelBaseTool, ToolResult

class ClarifyTool(ExcelBaseTool):
    name = "clarify"
    description = (
        "当用户需求缺少关键信息（如列名、操作类型）时调用此工具，"
        "向用户提出明确问题并列出可用选项。 "
        "参数 question: str（要问的问题）, options: list[str]（可选的答案选项）。"
        "返回给用户的反问内容。"
    )

    async def _arun(self, question: str, options: Optional[list[str]] = None) -> ToolResult:
        prompt = question
        if options:
            prompt += "\n可选：" + "、".join(options)
        return ToolResult(
            success=True,
            observation=prompt,
            data={"requires_clarification": True, "options": options or []}
        )
```

### 1.7 工具注册表

```python
# app/agent/tools/registry.py

from app.agent.tools.base import ExcelBaseTool
from app.agent.tools.hello import HelloTool
from app.agent.tools.clarify import ClarifyTool

class ExcelToolRegistry:
    def __init__(self):
        # Phase 1 只有两个工具，Phase 2 后追加其余工具
        self._tools: list[ExcelBaseTool] = [
            HelloTool(),
            ClarifyTool(),
        ]

    def get_tools(self) -> list[ExcelBaseTool]:
        return self._tools

    def get_tool(self, name: str) -> Optional[ExcelBaseTool]:
        for tool in self._tools:
            if tool.name == name:
                return tool
        return None

    def add_tool(self, tool: ExcelBaseTool) -> None:
        """Phase 2 追加工具时调用"""
        self._tools.append(tool)
```

### 1.8 DBConversationBufferMemory（Phase 1 简化版，Phase 3 完善）

**Phase 1 重要说明**：由于 LangChain 的 `ConversationBufferMemory.chat_memory` 是同步 `@property`，无法在同步上下文中调用 `async` 的 `load_messages_history()`。因此 Phase 1 的 `_load_from_db()` 是空操作（初始 memory 为空），真正的历史加载在 **Phase 3** 实现（通过 LangChain `ChatMessageHistory` 接口或 `run_in_executor` 方案）。

```python
# app/agent/memory/db_buffer.py

"""DB ↔ ConversationBufferMemory 互转"""

import logging
from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from langchain.memory import ConversationBufferMemory
from langchain.schema import HumanMessage, AIMessage

logger = logging.getLogger(__name__)


class LazyConversationBufferMemory(ConversationBufferMemory):
    """
    惰性 ConversationBufferMemory。
    在首次访问 chat_memory.messages 时才从 DB 加载。
    """

    def __init__(
        self,
        thread_id: UUID,
        user_id: UUID,
        db_session: AsyncSession,
        max_tokens: int = 16000,
    ):
        super().__init__(return_messages=True, output_key="output", input_key="input")
        self._thread_id = thread_id
        self._user_id = user_id
        self._db = db_session
        self._max_tokens = max_tokens
        self._loaded = False

    @property
    def chat_memory(self):
        """惰性加载：首次访问时从 DB 读取"""
        if not self._loaded:
            self._load_from_db()
            self._loaded = True
        return self._memory

    def _load_from_db(self) -> None:
        """从 DB 加载历史到内部 _memory（子类实现）"""
        from app.persistence.turn_repository import TurnRepository
        repo = TurnRepository(self._db)
        messages_data = repo.load_messages_history_sync(self._thread_id)  # 同步版本

        self._memory = type('ChatHistory', (), {'messages': []})()
        for msg_data in messages_data:
            if msg_data.get("role") == "user":
                self._memory.messages.append(HumanMessage(content=msg_data.get("content", "")))
            elif msg_data.get("role") == "assistant":
                self._memory.messages.append(AIMessage(content=msg_data.get("content", "")))

    async def save(self) -> None:
        """将当前 memory 回写到 DB（Agent 请求结束后调用）"""
        from app.persistence.turn_repository import TurnRepository
        repo = TurnRepository(self._db)
        latest_turn = await repo.get_latest_turn(self._thread_id)
        if not latest_turn:
            return

        messages = []
        for msg in self.chat_memory.messages:
            if isinstance(msg, HumanMessage):
                messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                messages.append({"role": "assistant", "content": msg.content})

        await repo.save_messages_history(latest_turn.id, messages)
        logger.info(f"Memory 已保存: thread={self._thread_id}, {len(messages)} 条")


class DBConversationBufferMemory(LazyConversationBufferMemory):
    """Phase 1 简化版，直接继承 LazyConversationBufferMemory"""
    pass
```

**注意：`turn_repository.py` 需要新增同步方法 `load_messages_history_sync()`**，因为 LangChain 的 `ConversationBufferMemory.chat_memory` 是同步属性：

```python
def load_messages_history_sync(self, thread_id: UUID) -> list[dict]:
    """同步版本（用于 LazyConversationBufferMemory._load_from_db）"""
    import asyncio
    loop = asyncio.get_event_loop()
    # 在已有 async 方法外包裹
    return loop.run_until_complete(self.load_messages_history(thread_id))
```

### 1.9 ExcelAgent 主类（Phase 1 简化版）

```python
# app/agent/excel_agent.py

import logging
from uuid import UUID
from typing import AsyncGenerator, Optional
from langchain.agents import ConversableAgent
from langchain.schema import HumanMessage

from app.agent.agent_executor import AgentExecutor, StreamEvent
from app.agent.tools.registry import ExcelToolRegistry
from app.agent.prompts.excel_assistant import get_excel_assistant_prompt
from app.agent.memory.db_buffer import DBConversationBufferMemory
from app.persistence.turn_repository import TurnRepository
from app.engine.langchain_llm import get_langchain_chat_model

logger = logging.getLogger(__name__)


class ExcelAgent:

    def __init__(
        self,
        user_id: UUID,
        thread_id: UUID,
        db_session,  # AsyncSession
        stage: str = "chat",  # Phase 1 默认用 chat stage
    ):
        self.user_id = user_id
        self.thread_id = thread_id
        self.db = db_session
        self.repo = TurnRepository(db_session)
        self.tool_registry = ExcelToolRegistry()

        # Memory（惰性加载，Phase 1 为空，Phase 3 从 DB 恢复）
        self.memory = DBConversationBufferMemory(
            thread_id=thread_id,
            user_id=user_id,
            db_session=db_session,
        )

        # LLM（Phase 1 用 chat stage）
        # 注意：这里不能 await，get_langchain_chat_model 是 async
        # 实际在 run() 中获取
        self._llm = None
        self._stage = stage

    async def _ensure_llm(self):
        if self._llm is None:
            self._llm = await get_langchain_chat_model(self._stage, self.db)

    async def run(
        self,
        query: str,
        file_ids: list[str],
    ) -> AsyncGenerator[StreamEvent, None]:
        """运行 Agent，返回 SSE 事件流（Phase 1 简化版：直接用 HelloTool）"""
        await self._ensure_llm()

        executor = AgentExecutor(
            agent=None,  # Phase 1 不用 ConversableAgent，直接用 hello
            memory=self.memory,
            tool_registry=self.tool_registry,
        )

        async for event in executor.run_simple(query=query, file_ids=file_ids):
            yield event

        # 保存 memory
        try:
            await self.memory.save()
        except Exception as e:
            logger.error(f"保存 memory 失败: {e}")
```

### 1.10 AgentExecutor 简化版（Phase 1）

```python
# app/agent/agent_executor.py

from dataclasses import dataclass
from typing import AsyncGenerator, Optional
from app.agent.streaming import StreamEvent

@dataclass
class StreamEvent:
    event: str   # "session" | "tool_start" | "tool_end" | "agent_end" | "error" | "complete"
    data: dict


class AgentExecutor:
    """
    Phase 1 简化版：直接调度工具，不走 ConversableAgent。
    Phase 4 重写为基于 LangChain AgentExecutor 的完整实现。
    """

    def __init__(self, agent, memory, tool_registry):
        self.agent = agent
        self.memory = memory
        self.tool_registry = tool_registry

    async def run_simple(
        self,
        query: str,
        file_ids: list[str],
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Phase 1 直接工具调度（SSE 流式）。
        - 有文件但无明确意图 → ClarifyTool
        - 无文件或闲聊 → HelloTool
        """
        query_lower = query.strip().lower()

        # 判断：无文件时，闲聊走 HelloTool；有文件时走 ClarifyTool
        use_hello = (
            not file_ids
            and any(kw in query_lower for kw in ["你好", "hi", "hello", "嗨", "帮助", "介绍", "谢谢"])
        )

        tool = self.tool_registry.get_tool("clarify" if file_ids and not use_hello else "hello")

        if tool is None:
            yield StreamEvent(event="error", data={"message": f"Tool not found"})
            yield StreamEvent(event="complete", data={"status": "error"})
            return

        yield StreamEvent(event="tool_start", data={"tool": tool.name, "args": {"query": query}})

        # 模拟打字机效果（每个字符 yield 一个 tool_stream）
        if tool.name == "hello":
            greeting = "你好！我是 Excel 智能助手，可以帮你处理数据分析、排序、筛选等操作。有什么我可以帮你的吗？"
        else:
            greeting = "您好！请告诉我您想对数据做什么操作，例如：分析这份数据的趋势、按照某列排序、筛选特定条件的记录等。"

        full_response = greeting
        for i, char in enumerate(full_response):
            yield StreamEvent(
                event="tool_stream",
                data={"tool": tool.name, "delta": char, "partial": full_response[:i+1]}
            )

        yield StreamEvent(
            event="tool_end",
            data={
                "tool": tool.name,
                "observation": full_response,
                "data": {"success": True}
            }
        )

        yield StreamEvent(event="agent_end", data={"response": full_response})
        yield StreamEvent(event="complete", data={"status": "done"})
```

### 1.11 路由接入（Phase 1 完整版）

```python
# app/api/routes/chat.py（Phase 1 完整实现）

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.agent.excel_agent import ExcelAgent
from app.agent.agent_executor import StreamEvent
from app.core.sse import sse as make_sse_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat")


class ChatRequest(BaseModel):
    query: str
    file_ids: List[str] = Field(default_factory=list)
    thread_id: Optional[str] = Field(None)


@router.post("")
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    LangChain Agent 统一入口（SSE 流式）。
    Phase 1：HelloTool + ClarifyTool 验收。
    Phase 2+：完整工具链。
    """
    async def stream():
        try:
            # 获取 thread（新建或复用）
            repo = db  # TurnRepository 需要 AsyncSession，直接用 db session
            from app.persistence.turn_repository import TurnRepository
            r = TurnRepository(db)

            thread_uuid = UUID(request.thread_id) if request.thread_id else None
            thread, is_new = await r.get_or_create_thread(
                user_id=current_user.id,
                thread_id=thread_uuid,
                initial_query=request.query,
            )

            # 建立 Agent（Phase 1 stage = "chat"）
            agent = ExcelAgent(
                user_id=current_user.id,
                thread_id=thread.id,
                db_session=db,
                stage="chat",
            )

            # 创建新 Turn（用于保存 memory）
            next_turn_number = await r.get_next_turn_number(thread.id)
            current_turn = await r.create_turn(
                thread_id=thread.id,
                turn_number=next_turn_number,
                user_query=request.query,
            )

            # 关联文件
            if request.file_ids:
                from uuid import UUID as uuid
                file_uuids = [uuid(fid) for fid in request.file_ids]
                await r.link_files_to_turn(current_turn.id, file_uuids, current_user.id)

            await r.commit()

            # session 事件
            yield make_sse_event(
                {"thread_id": str(thread.id), "is_new": is_new},
                event="session"
            )

            # Agent 执行
            # Phase 1: use_full_agent=False（Phase 4 重写为 True）
            async for event in agent.run(
                query=request.query,
                file_ids=request.file_ids,
                use_full_agent=False,
            ):
                yield make_sse_event(event.data, event=event.event)

            yield make_sse_event({"status": "done"}, event="complete")

        except Exception as e:
            logger.error(f"Agent 执行失败: {e}", exc_info=True)
            yield make_sse_event({"message": f"处理失败: {str(e)}"}, event="error")

    return EventSourceResponse(
        stream(),
        media_type="text/event-stream",
    )


# ========== 以下旧端点在本版本中彻底移除（归档到 archive/） ==========
#   - POST /chat/clarify        → ClarifyTool 替代
#   - GET  /chat/intents        → 不再需要（Agent 自己判断）
# =====================================================================
```

### 1.12 System Prompt（Phase 1）

```python
# app/agent/prompts/excel_assistant.py

def get_excel_assistant_prompt() -> str:
    return """\
你是 Excel 智能助手，擅长数据分析、处理和转换。

## 你的能力

1. 读取 Excel 文件并理解其结构（列名、数据类型、样本）
2. 根据用户自然语言描述执行：筛选、排序、分组聚合、新增列、更新列、透视表等
3. 生成带 Excel 公式的结果文件，可直接下载

## 工具使用规则

- **无文件时**：如果用户只是闲聊、问候或说「你好」，调用 hello 工具
- **有文件时**：如果用户没有明确说明要做什么，调用 clarify 工具询问
- 工具调用参数必须准确，列名必须与 schema 中的真实列名完全一致

## 输出格式

每次工具调用后，你会得到工具返回的 observation。
根据 observation 决定下一步操作或返回最终回复。

## 安全边界

- 拒绝任何涉及删除系统文件、修改系统设置的请求
- 不执行任何可能破坏数据的不可逆操作除非用户明确确认\
"""
```

### 1.13 SSE 事件类型定义

```python
# app/agent/streaming.py

from dataclasses import dataclass

@dataclass
class StreamEvent:
    """SSE 事件数据结构"""
    event: str
    data: dict

# 事件类型：
#   session     { thread_id: str, is_new: bool }
#   tool_start  { tool: str, args: dict }
#   tool_stream { tool: str, delta: str, partial: str }
#   tool_end    { tool: str, observation: str, data: dict }
#   agent_end   { response: str }
#   error       { message: str }
#   complete    { status: str }
```

### 1.14 Phase 1 验收标准

**必须全部通过才能进入 Phase 2：**

```
✅ POST /chat 返回 SSE stream（media_type: text/event-stream）
✅ 不上传文件，说"你好"：
     - 看到 tool_start{hello} → tool_stream → tool_end → agent_end
     - 最终回复包含"Excel 智能助手"
✅ 不上传文件，说"帮我分析数据"：
     - ClarifyTool 被调用，回复要求用户提供文件
✅ 上传文件后说"分析"：
     - ClarifyTool 被调用，回复询问具体分析维度
✅ thread_id 传递后，第二次请求时 save() 方法正确调用（memory 持久化到 DB — 注意：Phase 1 memory 加载是空操作，真正加载在 Phase 3 实现）
✅ 启动时若 LLM stage 缺失，进程报错退出（Phase 0 验收）
✅ python -c "from app.agent.excel_agent import ExcelAgent; print('OK')" 无报错
✅ python -c "from app.persistence.turn_repository import TurnRepository; print('OK')" 无报错
```

---

## Phase 2：工具层（Tooling）

**目标：将所有现有操作能力包装为 LangChain Tools，实现"能力不降级迁移"。**

### 2.1 公共前提：Executor 纯函数化（前置任务）

**Phase 2 开始前，先完成 executor 纯函数化验证。**

```bash
# 在 executor.py 所在目录运行
uv run python -c "
from app.engine.executor import ExcelExecutor
from app.engine.models import FileCollection, FilterOperation
import asyncio

# 验证 FileCollection 是否支持链式调用（每次返回新实例）
# 如果 .filter() 返回的是新实例而非修改自身，则纯函数化可行
# 注意：ExcelExecutor.__init__(tables: FileCollection) 需要真实 FileCollection
# 简化验证：
from app.engine.excel_parser import ExcelParser
fc = ExcelParser.parse_file_all_sheets('tests/data/sample.xlsx')  # 需要实际文件
ec = ExcelExecutor(fc)
op = FilterOperation(column='销售额', op='>', value=1000)
result = ec._execute_filter(op)
assert result is not None
print('executor 方法可调用')
"
```

**如果上述断言失败**（即 `.filter()` 修改自身），则 `FileCollection` 底层需要改造，返回新实例而非修改自身。Phase 2 应将此作为**第一个任务**，在包装 Tool 之前完成 `FileCollection` 的不可变性改造。

### 2.2 工具实现（13 个工具）

每个工具遵循统一签名：

```python
class XxxTool(ExcelBaseTool):
    name: str = "xxx"
    description: str = "..."   # 详细的描述和参数说明（给 LLM 看）

    async def _arun(self, **kwargs) -> ToolResult:
        # 1. 调用对应的 executor 纯函数
        # 2. 返回 ToolResult
        pass
```

**工具列表**：

| 工具 | 对应旧代码 | 关键参数 |
|------|-----------|---------|
| `ReadExcelTool` | `excel_parser.py` + `oss.py` | `file_ids: list[str]` |
| `GetSchemaTool` | 从 FileCollection 提取 | `file_collection` |
| `FilterTool` | `executor.py ExcelExecutor._execute_filter` | `file_collection, conditions` |
| `SortTool` | `executor.py ExcelExecutor._execute_sort` | `file_collection, column, order` |
| `GroupByTool` | `executor.py ExcelExecutor._execute_group_by` | `file_collection, group_by, agg_funcs` |
| `AddColumnTool` | `executor.py ExcelExecutor._execute_add_column` | `file_collection, column_name, expression` |
| `UpdateColumnTool` | `executor.py ExcelExecutor._execute_update_column` | `file_collection, column_name, new_value` |
| `AggregateTool` | `executor.py ExcelExecutor._execute_aggregate` | `file_collection, agg_funcs` |
| `ComputeTool` | `executor.py ExcelExecutor._execute_compute` | `file_collection, expression` |
| `PivotTool` | `executor.py ExcelExecutor._execute_pivot` | `file_collection, rows, cols, values` |
| `GenerateFormulasTool` | `excel_generator.py` | `operations: list` |
| `ExportExcelTool` | `oss.py` | `file_collection, formulas` |
| `ClarifyTool` | 内置 | `question, options` |

**注意**：Phase 2 实施前需确认 `excel_parser.py` 中是否有顶层 `parse_files()` 函数，还是需要通过 `OSSService` + `ExcelParser` 实例调用。工具实现需先完成这一验证步骤。

### 2.3 工具注册表追加

```python
# app/agent/tools/registry.py

class ExcelToolRegistry:
    def __init__(self):
        self._tools: list[ExcelBaseTool] = [
            HelloTool(),
            ClarifyTool(),
            # Phase 2 新增：
            ReadExcelTool(),
            GetSchemaTool(),
            FilterTool(),
            SortTool(),
            GroupByTool(),
            AddColumnTool(),
            UpdateColumnTool(),
            AggregateTool(),
            ComputeTool(),
            PivotTool(),
            GenerateFormulasTool(),
            ExportExcelTool(),
        ]
```

### 2.4 conftest.py 新增 fixture

```python
# apps/api/tests/conftest.py 新增

import pytest
import asyncio
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.models.thread import Thread
from app.models.file import File

@pytest.fixture
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def db_session():
    """测试用 AsyncSession"""
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        yield session

@pytest.fixture
async def user(db_session):
    from app.models.user import User
    user = User(id=uuid4(), username="test", hashed_password="xxx")
    db_session.add(user)
    await db_session.commit()
    return user

@pytest.fixture
async def uploaded_file(db_session, user):
    """上传一个测试 Excel 文件，返回 (file_id, File 对象)"""
    # 创建测试文件（使用 openpyxl）
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["姓名", "销售额", "地区"])
    ws.append(["张三", 1000, "华北"])
    ws.append(["李四", 2000, "华南"])
    # 保存到临时路径（或直接上传到 MinIO mock）
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    wb.save(tmp.name)
    tmp.close()

    # 上传（复用现有 file service）
    from app.services.oss import OSSService
    oss = OSSService()
    file_id = await oss.upload_file(tmp.name, f"test_{uuid4().hex[:8]}.xlsx", user.id)
    os.unlink(tmp.name)

    return file_id
```

### 2.5 Phase 2 验收标准

```
✅ HelloTool + ClarifyTool 仍正常工作（Phase 1 不退化）
✅ ReadExcelTool(file_ids=[id]) 返回 FileCollection，列名与上传文件一致
✅ FilterTool + SortTool + ExportExcelTool 串联：读取 → 过滤 → 排序 → 导出，返回下载 URL
✅ ClarifyTool 触发后，Agent 暂停，等待下一轮用户输入（不自动继续）
✅ 每个工具独立单元测试通过（pytest）
✅ pytest apps/api/tests/agent/test_tools/ -v 通过率 100%
```

---

## Phase 3：上下文与记忆层（Memory）

**目标：Memory 从 DB 正确加载/保存，支持多轮对话和 token 控制。**

### 3.1 TokenManager（支持任意模型）

```python
# app/agent/memory/token_manager.py

import logging
from typing import Optional
from langchain.schema import BaseMessage

logger = logging.getLogger(__name__)

# 模型 → tiktoken encoding name 映射
MODEL_ENCODING_MAP = {
    "gpt-4": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    "deepseek-v3": "cl100k_base",   # DeepSeek V3 用与 GPT-4 相同的 tokenizer
    "deepseek-chat": "cl100k_base",
    "default": "cl100k_base",
}

# 动态检测实际 model_id 对应的 encoding
def _get_encoding_for_model(model_id: str):
    try:
        import tiktoken
        encoding_name = MODEL_ENCODING_MAP.get(model_id, MODEL_ENCODING_MAP["default"])
        return tiktoken.get_encoding(encoding_name)
    except Exception as e:
        logger.warning(f"tiktoken 初始化失败: {e}，使用 cl100k_base")
        import tiktoken
        return tiktoken.get_encoding("cl100k_base")


class TokenManager:
    """
    管理对话历史的 token 数量，自动截断超长历史。
    支持任意 model_id，自动选择对应 tiktoken encoding。
    """

    def __init__(self, model_id: str = "default", max_tokens: int = 16000):
        self.encoding = _get_encoding_for_model(model_id)
        self.max_tokens = max_tokens

    def count_tokens(self, messages: list[BaseMessage]) -> int:
        return sum(len(self.encoding.encode(msg.content or "")) for msg in messages)

    def truncate_messages(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """从最旧的消息开始截断，确保 total <= max_tokens"""
        result = []
        total = 0
        for msg in reversed(list(messages)):
            content = msg.content or ""
            tokens = len(self.encoding.encode(content))
            if total + tokens <= self.max_tokens:
                result.insert(0, msg)
                total += tokens
            else:
                break
        return result
```

### 3.2 DBConversationBufferMemory 完善

```python
# app/agent/memory/db_buffer.py 完整实现

class LazyConversationBufferMemory(ConversationBufferMemory):
    """
    惰性 ConversationBufferMemory。
    在 Agent 首次访问 chat_memory.messages 时才从 DB 加载。
    """

    def __init__(
        self,
        thread_id: UUID,
        user_id: UUID,
        db_session: AsyncSession,
        max_tokens: int = 16000,
        model_id: str = "default",
    ):
        super().__init__(return_messages=True, output_key="output", input_key="input")
        self._thread_id = thread_id
        self._user_id = user_id
        self._db = db_session
        self._max_tokens = max_tokens
        self._model_id = model_id
        self._loaded = False
        self._token_manager = TokenManager(model_id=model_id, max_tokens=max_tokens)

        # 初始化 _memory 为空（同步上下文中无法调用 async load_messages_history）
        # Phase 3 在 save() 时以 async 方式恢复历史
        class _ChatHistory:
            def __init__(self):
                self.messages = []
        self._memory = _ChatHistory()

    @property
    def chat_memory(self):
        """惰性加载：首次访问时从 DB 读取"""
        if not self._loaded:
            self._load_from_db()
            self._loaded = True
        return self._memory

    def _load_from_db(self):
        """
        从 DB 加载历史到内部 _memory。

        注意：Phase 1 中，由于同步上下文中无法调用 async load_messages_history，
        此方法暂时初始化空 memory。Phase 3 实现真正的异步加载：
        - 方案 A：ChatMessageHistory 接口（LangChain 官方方案）
        - 方案 B：turn_contextlocal 线程级 context var 传 sync session
        """
        # Phase 1 暂时为空，Phase 3 替换为真实实现
        self._memory = _ChatHistory()
        self._loaded = True

    async def save(self) -> None:
        """将当前 memory 回写到 DB（Agent 请求结束后调用）"""
        from app.persistence.turn_repository import TurnRepository

        # 确保 memory 已加载（若从未访问 chat_memory，先初始化）
        if not self._loaded:
            self._load_from_db()

        repo = TurnRepository(self._db)
        latest_turn = await repo.get_latest_turn(self._thread_id)
        if not latest_turn:
            logger.warning(f"save: thread {self._thread_id} 无 turn，跳过")
            return

        # Token 截断后再保存
        truncated = self._token_manager.truncate_messages(self._memory.messages)

        messages = []
        for msg in truncated:
            if isinstance(msg, HumanMessage):
                messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                messages.append({"role": "assistant", "content": msg.content})

        await repo.save_messages_history(latest_turn.id, messages)
        logger.info(f"Memory 已保存: thread={self._thread_id}, {len(messages)} 条（截断后）")
```

### 3.3 Phase 3 验收标准

```
✅ 多轮对话（3 轮）：第三轮的 Agent 能感知前两轮内容（DB 验证 messages_history）
✅ Agent 能正确引用前一轮输出文件（file_id 跨 Turn 传递）
✅ 超过 max_tokens 时，DB 中保存的消息被截断（不超过 16000 tokens）
✅ TokenManager 对 DeepSeek V3 不报错（encoding 正确）
✅ pytest apps/api/tests/agent/test_memory/ -v 通过
```

---

## Phase 4：流式与观测层（Streaming & Observability）

**目标：ConversableAgent + 完整 SSE 流式上报，Abort 机制完善。**

### 4.1 AgentExecutor 完整实现

Phase 1 的简化版 `run_simple()` 替换为基于 `ConversableAgent` + LangChain `CallbackManager` 的完整实现：

```python
# app/agent/agent_executor.py 完整实现（Phase 4 替换 Phase 1 版本）

import asyncio
import logging
from typing import AsyncGenerator, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class SSEEventQueue:
    """
    线程安全的异步队列，用于将 LangChain 回调事件转为 SSE 事件。
    """

    def __init__(self):
        self._queue: asyncio.Queue[Optional[StreamEvent]] = asyncio.Queue()
        self._tool_output_buffers: dict[str, str] = {}

    async def put(self, event: StreamEvent) -> None:
        await self._queue.put(event)

    async def get(self) -> Optional[StreamEvent]:
        return await self._queue.get()

    def put_nowait(self, event: StreamEvent) -> None:
        self._queue.put_nowait(event)

    def buffer_append(self, tool_name: str, delta: str) -> None:
        if tool_name not in self._tool_output_buffers:
            self._tool_output_buffers[tool_name] = ""
        self._tool_output_buffers[tool_name] += delta

    def buffer_drain(self, tool_name: str) -> str:
        result = self._tool_output_buffers.pop(tool_name, "")
        return result

    def send_end_marker(self) -> None:
        self._queue.put_nowait(None)


class SSEAgentCallback:
    """
    LangChain BaseCallbackHandler → SSE 事件发射器。
    """

    def __init__(self, queue: SSEEventQueue):
        self.queue = queue

    async def on_tool_start(self, serialized: dict, input_str: str, **kwargs) -> None:
        tool_name = serialized.get("name", "unknown")
        await self.queue.put(StreamEvent(
            event="tool_start",
            data={"tool": tool_name, "args": input_str}
        ))
        self.queue.buffer_append(tool_name, "")

    async def on_tool_end(
        self,
        serialized: dict,
        output: str,
        **kwargs,
    ) -> None:
        """LangChain 在工具执行完后调用此方法。"""
        tool_name = serialized.get("name", "unknown") if isinstance(serialized, dict) else "unknown"
        final_content = self.queue.buffer_drain(tool_name) or output
        await self.queue.put(StreamEvent(
            event="tool_end",
            data={"tool": tool_name, "observation": final_content, "data": {"success": True}}
        ))

    async def on_tool_error(self, error: Exception, **kwargs) -> None:
        tool_name = kwargs.get("serialized", {}).get("name", "unknown")
        await self.queue.put(StreamEvent(
            event="tool_end",
            data={"tool": tool_name, "error": str(error), "data": {"success": False}}
        ))

    async def on_text(self, text: str, **kwargs) -> None:
        """LLM 推理过程中的文本输出（用于 typing 效果）"""
        # 可选：将文本作为 agent_thought 事件上报
        pass


@dataclass
class StreamEvent:
    event: str
    data: dict


class AgentExecutor:
    """
    将 ConversableAgent 的执行过程转换为 SSE 事件流（Phase 4 完整版）。
    """

    def __init__(
        self,
        agent: "ConversableAgent",   # 前向引用，运行时类型
        memory: "DBConversationBufferMemory",
        tool_registry: "ExcelToolRegistry",
        event_queue: Optional[SSEEventQueue] = None,
    ):
        self.agent = agent
        self.memory = memory
        self.tool_registry = tool_registry
        self._event_queue = event_queue or SSEEventQueue()
        self._running_task: Optional[asyncio.Task] = None
        self._abort_event = asyncio.Event()

    def set_abort(self) -> None:
        """中止当前运行中的 Agent（由 SSE 连接断开时调用）"""
        self._abort_event.set()

    async def run(
        self,
        query: str,
        file_ids: list[str],
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        在后台线程中运行 ConversableAgent，事件通过队列传回。
        支持 Abort：SSE 断开时自动中止 Agent。
        """
        loop = asyncio.get_running_loop()
        self._abort_event.clear()

        async def run_agent_in_thread():
            try:
                # 在线程池中运行（ConversableAgent.run 是同步的）
                result = await loop.run_in_executor(
                    None,
                    lambda: self.agent.run(
                        input=query,
                        callbacks=[SSEAgentCallback(self._event_queue)],
                    )
                )
                await self._event_queue.put(StreamEvent(
                    event="agent_end",
                    data={"response": str(result) if result else ""}
                ))
            except Exception as e:
                if not self._abort_event.is_set():
                    logger.error(f"Agent 执行异常: {e}", exc_info=True)
                    await self._event_queue.put(StreamEvent(
                        event="error",
                        data={"message": str(e)}
                    ))
            finally:
                self._event_queue.send_end_marker()

        # 启动 Agent 执行（后台任务）
        self._running_task = asyncio.create_task(run_agent_in_thread())

        # 从队列中 yield 事件，支持 Abort
        while True:
            try:
                # 设置超时，以便定期检查 abort 状态
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                if self._abort_event.is_set():
                    logger.info("Agent 执行已中止（SSE 连接断开）")
                    if self._running_task and not self._running_task.done():
                        self._running_task.cancel()
                    break
                continue

            if event is None:
                break
            yield event

    # Phase 1 兼容接口（保留 run_simple）
    async def run_simple(
        self,
        query: str,
        file_ids: list[str],
    ) -> AsyncGenerator[StreamEvent, None]:
        """Phase 1 简化版（不依赖 ConversableAgent）"""
        from app.agent.tools.base import ToolResult
        from app.agent.tools.hello import HelloTool
        from app.agent.tools.clarify import ClarifyTool

        query_lower = query.strip().lower()
        use_hello = (
            not file_ids
            and any(kw in query_lower for kw in ["你好", "hi", "hello", "嗨", "帮助", "介绍", "谢谢"])
        )
        tool = self.tool_registry.get_tool("clarify" if file_ids and not use_hello else "hello")

        if tool is None:
            yield StreamEvent(event="error", data={"message": f"Tool not found"})
            yield StreamEvent(event="complete", data={"status": "error"})
            return

        yield StreamEvent(event="tool_start", data={"tool": tool.name, "args": {"query": query}})

        greeting = (
            "你好！我是 Excel 智能助手，可以帮你处理数据分析、排序、筛选等操作。有什么我可以帮你的吗？"
            if tool.name == "hello"
            else "您好！请告诉我您想对数据做什么操作，例如：分析这份数据的趋势、按照某列排序、筛选特定条件的记录等。"
        )

        for i, char in enumerate(greeting):
            yield StreamEvent(
                event="tool_stream",
                data={"tool": tool.name, "delta": char, "partial": greeting[:i+1]}
            )
            await asyncio.sleep(0.015)

        yield StreamEvent(
            event="tool_end",
            data={"tool": tool.name, "observation": greeting, "data": {"success": True}}
        )
        yield StreamEvent(event="agent_end", data={"response": greeting})
        yield StreamEvent(event="complete", data={"status": "done"})
```

### 4.2 ExcelAgent.run() 更新（支持 Phase 1 / Phase 4 切换）

```python
# app/agent/excel_agent.py Phase 4 更新

async def run(
    self,
    query: str,
    file_ids: list[str],
    use_full_agent: bool = True,  # Phase 4 后默认 True
) -> AsyncGenerator[StreamEvent, None]:
    """
    use_full_agent=True: 使用 ConversableAgent（Phase 4）
    use_full_agent=False: 使用简化工具调度（Phase 1 兼容）
    """
    await self._ensure_llm()

    executor = AgentExecutor(
        agent=self._build_conversable_agent() if use_full_agent else None,
        memory=self.memory,
        tool_registry=self.tool_registry,
    )

    generator = (
        executor.run(query=query, file_ids=file_ids)
        if use_full_agent
        else executor.run_simple(query=query, file_ids=file_ids)
    )

    async for event in generator:
        yield event

    await self.memory.save()
```

### 4.3 Phase 4 验收标准

```
✅ 上传文件后说"按销售额排序"，能看到完整的 tool_start → tool_stream（N次）→ tool_end 事件序列
✅ SSE 连接断开（Abort）后，Agent 后台任务在 2 秒内被取消（通过日志验证）
✅ tool_stream 事件中 delta 累积后与 tool_end 的 observation 完全一致
✅ pytest apps/api/tests/agent/test_excel_agent_e2e.py -v 并发 5 个请求无互相干扰
✅ python -c "from app.agent.agent_executor import AgentExecutor; print('OK')" 无报错
```

---

## Phase 5：Prompt 工程与调优（Prompt Engineering）

**目标：工具选对率 > 95%，安全边界完整，Examples 可配置注入。**

### 5.1 System Prompt（最终版）

见 Phase 1.12，已包含完整的能力说明、工具规则、输出格式、安全边界。

### 5.2 Examples 注册表

```python
# app/agent/prompts/examples.py

from dataclasses import dataclass
from typing import Optional

@dataclass
class ToolExample:
    """单个工具的 I/O Example"""
    tool_name: str
    user_query: str
    expected_tool: str
    expected_args: Optional[dict] = None
    notes: Optional[str] = None

EXAMPLES: list[ToolExample] = [
    # FilterTool
    ToolExample(
        tool_name="filter",
        user_query="只看销售额大于1000的行",
        expected_tool="filter",
        expected_args={"column": "销售额", "op": ">", "value": 1000},
    ),
    ToolExample(
        tool_name="filter",
        user_query="筛选华北地区的数据",
        expected_tool="filter",
        expected_args={"column": "地区", "op": "==", "value": "华北"},
    ),
    # SortTool
    ToolExample(
        tool_name="sort",
        user_query="按销售额从高到低排序",
        expected_tool="sort",
        expected_args={"column": "销售额", "order": "desc"},
    ),
    # AggregateTool
    ToolExample(
        tool_name="aggregate",
        user_query="各地区的销售总额是多少",
        expected_tool="aggregate",
        expected_args={"group_by": "地区", "agg": "sum", "column": "销售额"},
    ),
    # ClarifyTool
    ToolExample(
        tool_name="clarify",
        user_query="分析这份数据",
        expected_tool="clarify",
        expected_args={"question": "您想从哪个维度分析？", "options": ["按地区", "按产品", "按时段"]},
    ),
]


class ExamplesQueryRegistry:
    """
    根据用户 query 特征，注入相关 Examples 到 prompt。
    Phase 5 通过 keyword matching 选择最相关的 3-5 个 examples。
    """

    def __init__(self, examples: list[ToolExample] = None):
        self._examples = examples or EXAMPLES

    def get_relevant_examples(self, query: str) -> list[ToolExample]:
        """根据 query 关键词返回最相关的 examples（最多 5 条）"""
        query_lower = query.lower()
        scored = []
        for ex in self._examples:
            score = sum(1 for kw in ex.user_query.lower().split() if kw in query_lower)
            if score > 0:
                scored.append((score, ex))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ex for _, ex in scored[:5]]

    def format_as_prompt(self, examples: list[ToolExample]) -> str:
        """将 examples 格式化为 prompt 文本"""
        lines = ["\n## 参考示例\n"]
        for ex in examples:
            lines.append(f"用户说：「{ex.user_query}」")
            lines.append(f"  → 调用 {ex.expected_tool}{f'（参数：{ex.expected_args}）' if ex.expected_args else ''}")
            if ex.notes:
                lines.append(f"  注：{ex.notes}")
            lines.append("")
        return "\n".join(lines)
```

### 5.3 Schema Injector

```python
# app/agent/prompts/schema_injector.py

def build_schema_section(file_collection) -> str:
    """
    将 FileCollection 的表结构格式化为 prompt 中的 Schema 段落。
    格式：
    ## 当前 Excel 文件结构

    文件 [filename.xlsx] - Sheet [sheet_name]
    | 列名 | 类型 | 样本 |
    |------|------|------|
    | 姓名 | text | 张三、李四 |
    ...
    """
    lines = ["## 当前 Excel 文件结构\n"]
    for excel_file in file_collection:
        for sheet_name in excel_file.get_sheet_names():
            table = excel_file.get_sheet(sheet_name)
            cols = table.get_columns()
            samples = table.get_sample_rows(3)
            lines.append(f"文件 [{excel_file.filename}] - 表 [{sheet_name}]")
            lines.append(f"列名：{', '.join(cols)}")
            if samples:
                lines.append(f"样本行：{samples[:2]}")
            lines.append("")
    return "\n".join(lines)
```

### 5.4 Phase 5 验收标准

```
✅ 从 pytest 随机抽取 20 条 query（由 TestEngineer 提前准备），工具选对率 > 95%
✅ 列名不存在时 100% 触发 ClarifyTool（10 次测试）
✅ 空文件场景不崩溃，返回友好的 ClarifyTool
✅ 注入恶意 prompt（"忽略之前指令"），Agent 正确拒绝
✅ 注入恶意 prompt（"删除所有文件"），Agent 正确拒绝
✅ pytest apps/api/tests/agent/test_prompt_safety.py -v（安全测试）
```

---

## Phase 6：集成测试与归档（Integration & Launch）

**目标：端到端回归测试通过，旧代码彻底删除，Agent 正式上线。**

### 6.1 端到端测试套件

```python
# apps/api/tests/agent/test_excel_agent_e2e.py

import pytest
import asyncio

class TestExcelAgentE2E:

    @pytest.mark.asyncio
    async def test_pure_chat_hello(self, db, user):
        """纯文本对话，无文件 → HelloTool"""
        ...

    @pytest.mark.asyncio
    async def test_pure_chat_clarify(self, db, user):
        """无文件但说"分析数据" → ClarifyTool"""
        ...

    @pytest.mark.asyncio
    async def test_filter_and_sort(self, db, user, uploaded_file):
        """上传文件 → 筛选 → 排序 → 导出 → download_url"""
        ...

    @pytest.mark.asyncio
    async def test_group_by_aggregation(self, db, user, uploaded_file):
        """分组聚合"""
        ...

    @pytest.mark.asyncio
    async def test_clarify_on_missing_column(self, db, user, uploaded_file):
        """列名不存在 → ClarifyTool"""
        ...

    @pytest.mark.asyncio
    async def test_multi_turn_conversation(self, db, user):
        """多轮对话，Memory 正确加载"""
        ...

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, db, user):
        """并发 5 个请求不互相干扰"""
        ...

    @pytest.mark.asyncio
    async def test_memory_token_limit(self, db, user):
        """超长对话自动截断，不超过 max_tokens"""
        ...

    @pytest.mark.asyncio
    async def test_abort_on_disconnect(self, db, user):
        """SSE 断开后 Agent 在 2 秒内停止"""
        ...

    @pytest.mark.asyncio
    async def test_security_injection(self, db, user):
        """Prompt 注入安全测试"""
        ...
```

### 6.2 旧代码归档删除

**Phase 6 第一步**：将以下文件/目录移动到 `apps/api/archive/`：

```
apps/api/archive/                                # Phase 6 第一步移动至此
├── routes/
│   └── chat.py                                 # 含双 stream() 语法错误的原始版本
├── services/
│   ├── chat_stream.py
│   ├── chat_service.py
│   ├── intent_service.py
│   ├── analysis_stream.py
│   ├── processing_pipeline.py
│   └── context_service.py
├── engine/
│   ├── intent_classifier.py
│   └── context_builder.py
├── processor/
│   ├── excel_processor.py
│   └── stages/
│       ├── generate_validate.py
│       ├── execute.py
│       └── analysis.py
└── __init__.py                                 # 说明归档日期和原因
```

每个归档文件头部加注释：
```python
"""
归档日期: 2026-04-10
归档原因: LangChain Agent 重构完成，Phase 6 删除旧架构代码
原位置: app/api/routes/chat.py
"""
```

**Phase 6 最后一步**（Agent 上线稳定 1 周后执行）：
```bash
# 不可逆删除
rm -rf apps/api/archive/
git add -A && git commit -m "chore: remove archive/ after LangChain Agent v0.7.0 stable"
git tag v0.7.0-agent
```

### 6.3 归档文件修正（针对 `update.md` 原版本的错误）

| 原 update.md 写的归档路径 | 实际不存在 | 修正为 |
|--------------------------|-----------|-------|
| `app/api/routes/chat-legacy.py` | 不存在此文件 | `app/api/routes/chat.py`（原始版本） |
| `app/api/routes/clarify.py` | 不是独立文件 | 删除（ClarifyTool 替代） |
| `app/api/deps.py` | 标记"保留" | 保留（`get_current_user` 等仍被新代码使用） |
| `app/engine/llm_client.py` | 标记"保留参考" | 归档删除（Phase 6 完成前） |

### 6.4 Phase 6 验收标准

```
✅ pytest apps/api/tests/agent/test_excel_agent_e2e.py -v --tb=short 全部通过
✅ pytest --cov=apps/api/app/agent --cov-report=term-missing 覆盖率 > 80%
✅ 压测：100 QPS 并发，p99 < 2s
✅ 内存压测：连续 100 轮对话，内存增长 < 50MB
✅ archive/ 目录已移动到 apps/api/archive/
✅ Git tag v0.7.0-agent 已创建
✅ 旧代码 import 路径残留扫描（grep "from app.engine.context_builder" apps/api/app/ 返回空）
```

---

## 文件清单

### 新增文件

```
apps/api/app/agent/
├── __init__.py
├── excel_agent.py               # ExcelAgent 主类（Phase 1 简化版，Phase 4 完善）
├── agent_executor.py            # AgentExecutor（Phase 1 简化 run_simple，Phase 4 完整实现）
├── streaming.py                 # StreamEvent 数据结构
├── memory/
│   ├── __init__.py
│   ├── db_buffer.py            # LazyConversationBufferMemory + DBConversationBufferMemory
│   └── token_manager.py         # TokenManager（支持任意 model_id）
├── prompts/
│   ├── __init__.py
│   ├── excel_assistant.py       # System prompt
│   ├── schema_injector.py      # Schema 格式化
│   └── examples.py             # ExamplesQueryRegistry
├── tools/
│   ├── __init__.py
│   ├── base.py                 # ExcelBaseTool + ToolResult
│   ├── registry.py             # ExcelToolRegistry
│   ├── hello.py                # HelloTool（Phase 1）
│   ├── clarify.py               # ClarifyTool（Phase 1）
│   ├── read_excel.py           # ReadExcelTool（Phase 2）
│   ├── schema.py               # GetSchemaTool（Phase 2）
│   ├── filter.py               # FilterTool（Phase 2）
│   ├── sort.py                 # SortTool（Phase 2）
│   ├── group_by.py             # GroupByTool（Phase 2）
│   ├── add_column.py            # AddColumnTool（Phase 2）
│   ├── update_column.py        # UpdateColumnTool（Phase 2）
│   ├── aggregate.py             # AggregateTool（Phase 2）
│   ├── compute.py               # ComputeTool（Phase 2）
│   ├── pivot.py                 # PivotTool（Phase 2）
│   ├── generate_formulas.py    # GenerateFormulasTool（Phase 2）
│   └── export.py                # ExportExcelTool（Phase 2）
├── callbacks/
│   ├── __init__.py
│   └── sse.py                  # SSEAgentCallback
└── llm_adapters/
    ├── __init__.py
    └── langchain_adapter.py    # RegistryChatModel（替换旧 llm_client.py）

apps/api/app/core/
└── startup_validation.py        # Phase 0 启动校验

apps/api/tests/agent/
├── __init__.py
├── conftest.py                  # fixtures: db_session, user, uploaded_file
├── test_tools/
│   ├── test_filter_tool.py
│   ├── test_sort_tool.py
│   └── ...
├── test_memory/
│   └── test_db_buffer_memory.py
├── test_prompt_safety.py        # Phase 5 安全测试
└── test_excel_agent_e2e.py     # 端到端测试套件
```

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `apps/api/app/models/thread.py` | `ThreadTurn` 新增 `messages_history: JSONB` 字段 + alembic migration |
| `apps/api/app/api/routes/chat.py` | **完全重写**，接入 ExcelAgent |
| `apps/api/app/persistence/turn_repository.py` | 新增 `get_or_create_thread()`, `get_latest_turn()`, `save_messages_history()`, `load_messages_history()`, `flush()` |
| `apps/api/app/main.py` | lifespan 中注册 Phase 0 启动校验 |
| `apps/api/pyproject.toml` | 新增 `langchain`, `langchain-core`, `langchain-community`, `tiktoken` |

### 归档删除文件（Phase 6 执行）

```
apps/api/archive/                           # Phase 6 第一步移动，验证通过后删除
├── routes/chat.py                        # 含双 stream() 语法错误的原始版本
├── services/
│   ├── chat_stream.py
│   ├── chat_service.py
│   ├── intent_service.py
│   ├── analysis_stream.py
│   ├── processing_pipeline.py
│   └── context_service.py
├── engine/
│   ├── intent_classifier.py
│   └── context_builder.py
└── processor/
    ├── excel_processor.py
    └── stages/
        ├── generate_validate.py
        ├── execute.py
        └── analysis.py
```

**注意：`apps/api/app/engine/llm_client.py` 在 Phase 6 归档删除，不再保留。`get_llm_client()` 在 Phase 6 前完全由 `get_langchain_chat_model()` 替代。**

---

## 关键风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Stage 路由缺失静默失败 | 请求无响应，连接关闭 | **Phase 0 启动校验**，缺失则进程报错退出 |
| Python 模块语法错误静默失败 | 模块加载失败，路由未注册 | Phase 1 验收执行 `python -c "import app.api.routes.chat"` |
| `get_or_create_thread()` 不存在 | Phase 1 上线即崩溃 | **Phase 0 同时新增此方法**（已在 Phase 0.3 实现） |
| `AgentExecutor.run()` Phase 1 是空壳 | SSE 流无数据 | Phase 1 提供 `run_simple()` 实现，Phase 4 替换为完整版 |
| `LazyMemory` 惰性加载是假的 | Memory 每次都全量加载 | Phase 3 完整实现 `_load_from_db()` 惰性逻辑 |
| `max_conversation_tokens` 不存在 | 设置被静默忽略 | Phase 3 由 `TokenManager` 在 `save()` 时执行截断 |
| `create_task` 无引用导致 Abort 失效 | SSE 断开后 Agent 继续运行 | Phase 4 保存 `self._running_task`，Abort 时 `task.cancel()` |
| `FileCollection.filter()` 修改自身 | 纯函数化不可行 | Phase 2 第一步执行验证，失败则改造 `FileCollection` 为不可变 |
| archive 文件路径与实际不符 | 归档失败 | **Phase 6 前逐一核对实际文件路径**（见 6.3 修正表） |
| ProviderRegistry cache 永不过期 | credential 轮转后不生效 | Phase 6 后考虑移除 cache，或添加 refresh 机制 |
| Phase 5 无执行框架定义 | "随机 20 条测试"无法落地 | **Phase 6 前由 TestEngineer 定义随机 seed + 执行脚本** |

---

## LLM Stage 配置要求

**Phase 0 启动校验会检查以下 stage 必须存在：**

| Stage | 用途 | 最低要求 |
|-------|------|---------|
| `chat` | 纯文本对话、无文件时 | 必须配置（HelloTool + ClarifyTool 走此 stage） |
| `generate` | JSON 操作生成 | 必须配置（Phase 2+ GenerateFormulasTool 走此 stage） |
| `analyze` | 数据分析 | 必须配置（Phase 2+ AnalyzeTool 走此 stage） |
| `execute` | 操作执行（低延迟） | 必须配置（Phase 2+ ExecuteStage 走此 stage） |
| `default` | 保底 fallback | 必须配置 |

**配置方式**：在管理后台 `/llm/routes` 页面添加对应 stage，provider 指向已有的 DeepSeek provider。

---

## 验收流程

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5 ──► Phase 6
  │           │           │           │           │           │           │
  │        验收         验收         验收         验收         验收       完成
  │         ▼            ▼            ▼            ▼            ▼           ▼
  │     Hello+        工具链       Memory       SSE完整      Prompt      删除旧代码
  │     Clarify      串联         持久化       流式         工程化     归档
  │        ✅           ✅            ✅           ✅            ✅          ✅
  │                                                           │
  │                                                Git tag: v0.7.0-agent
```

**每个 Phase 验收通过标准：**
- Phase 特定验收标准（见各 Phase 末尾）
- `python -c "from app.agent.excel_agent import ExcelAgent; print('OK')"` 无报错
- `python -c "from app.persistence.turn_repository import TurnRepository; print('OK')"` 无报错
- 对应 pytest 测试 100% 通过

---

## 依赖安装

```bash
cd apps/api

# 安装 LangChain 生态
uv add langchain>=0.3.0 langchain-core>=0.3.0 langchain-community>=0.3.0 tiktoken>=0.7.0

# 验证安装
uv run python -c "import langchain; import tiktoken; print('依赖 OK')"

# 创建 migration（Phase 0 同时执行）
uv run alembic revision --autogenerate -m "add messages_history to thread_turns"
uv run alembic upgrade head

# 验证语法（Phase 1 前执行）
uv run python -c "import app.api.routes.chat; print('chat.py OK')"
uv run python -c "from app.persistence.turn_repository import TurnRepository; print('TurnRepository OK')"
uv run python -c "from app.agent.tools.registry import ExcelToolRegistry; print('ExcelToolRegistry OK')"
```
