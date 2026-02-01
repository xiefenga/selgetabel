# ExcelProcessor 设计文档

## 概述

`ExcelProcessor` 是 LLM Excel 系统的核心处理器，封装了所有 LLM + Excel 处理逻辑。设计目标是实现核心逻辑与外围关注点的分离，使 Fixture 测试和 Chat API 能够共用同一套处理流程。

## 设计目标

1. **核心逻辑独立**：处理逻辑不依赖文件存储、数据库、网络等外部基础设施
2. **中间过程可观察**：通过生成器模式输出每个阶段的事件，便于调试和 SSE 推送
3. **灵活配置**：LLM 流式/非流式调用可独立配置
4. **易于测试**：输入输出都是普通 Python 对象，无需 mock 外部依赖

## 架构分层

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Layer 1: Adapters                           │
│                         （适配层 - 外围关注点）                       │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  Chat API    │  │ Fixture API  │  │    CLI       │              │
│  │              │  │              │  │              │              │
│  │ - SSE 推送   │  │ - 直接返回   │  │ - 控制台输出 │              │
│  │ - 会话管理   │  │ - 无会话     │  │ - 无会话     │              │
│  │ - DB 持久化  │  │ - 本地文件   │  │ - 本地文件   │              │
│  │ - OSS 存储   │  │ - 本地存储   │  │ - 本地存储   │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 调用
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Layer 2: Processor                          │
│                         （处理器 - 核心流程）                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ExcelProcessor.process(tables, query, config)                    │
│                                                                     │
│   ┌─────────┐    ┌────────────────────────────┐    ┌─────────┐    │
│   │ analyze │ → │   GenerateValidateStage    │ → │ execute │    │
│   └─────────┘    │  ┌────────┐  ┌──────────┐ │    └─────────┘    │
│                  │  │generate│→│ validate │ │                    │
│                  │  └────────┘  └──────────┘ │                    │
│                  │       ↑           │       │                    │
│                  │       └── 重试 ───┘       │                    │
│                  └────────────────────────────┘                    │
│                                                                     │
│   输入: FileCollection, query, ProcessConfig                       │
│   输出: Generator[ProcessEvent] → ProcessResult                    │
│   特点: 线性 stages 结构，复杂逻辑封装在复合阶段内部                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 使用
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Layer 3: Engine                             │
│                         （引擎层 - 原子操作）                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌────────────────┐  ┌────────────────┐  ┌────────────────┐       │
│   │  llm_client    │  │    parser      │  │   executor     │       │
│   │  .analyze()    │  │  .parse()      │  │  .execute()    │       │
│   │  .generate()   │  │  .validate()   │  │               │       │
│   └────────────────┘  └────────────────┘  └────────────────┘       │
│                                                                     │
│   ┌────────────────┐  ┌────────────────┐                           │
│   │excel_generator │  │  excel_parser  │                           │
│   │.generate_      │  │  .parse_file() │                           │
│   │  formulas()    │  │               │                           │
│   └────────────────┘  └────────────────┘                           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## 核心类型定义

### ProcessStage - 处理阶段

```python
class ProcessStage(str, Enum):
    ANALYZE = "analyze"    # LLM 需求分析
    GENERATE = "generate"  # LLM 生成操作
    VALIDATE = "validate"  # 验证操作
    EXECUTE = "execute"    # 执行操作
```

### EventType - 事件类型

```python
class EventType(str, Enum):
    STAGE_START = "start"    # 阶段开始
    STAGE_STREAM = "stream"  # 流式增量（仅 stream_llm=True）
    STAGE_DONE = "done"      # 阶段完成
    STAGE_ERROR = "error"    # 阶段错误
```

### ProcessEvent - 处理事件

统一的中间过程输出格式，Fixture 测试和 Chat SSE 都使用此结构。

```python
@dataclass
class ProcessEvent:
    stage: ProcessStage       # 当前阶段
    event_type: EventType     # 事件类型
    output: Optional[Any]     # 阶段输出（DONE 时）
    delta: Optional[str]      # 流式增量（STREAM 时）
    error: Optional[str]      # 错误信息（ERROR 时）
```

### ProcessConfig - 处理配置

```python
@dataclass
class ProcessConfig:
    stream_llm: bool = False           # LLM 调用是否流式
    max_validation_retries: int = 2    # 验证失败后最大重试次数
```

### ProcessResult - 处理结果

```python
@dataclass
class ProcessResult:
    analysis: Optional[str]                    # 需求分析结果
    operations: Optional[Dict]                 # 生成的操作
    formulas: Optional[str]                    # Excel 公式
    variables: Dict[str, Any]                  # 聚合变量
    new_columns: Dict[str, Dict[str, List]]   # 新增列（预览）
    modified_tables: Optional[FileCollection]  # 修改后的表
    errors: List[str]                          # 错误列表
```

## ExcelProcessor API

### 主方法：process()

生成器方法，yield 每个处理事件，最终 return 处理结果。

```python
def process(
    self,
    tables: FileCollection,
    query: str,
    config: Optional[ProcessConfig] = None,
) -> Generator[ProcessEvent, None, ProcessResult]:
    """
    处理 Excel 数据

    Args:
        tables: 已加载的表集合（FileCollection）
        query: 用户查询（自然语言）
        config: 处理配置

    Yields:
        ProcessEvent: 处理事件

    Returns:
        ProcessResult: 最终结果
    """
```

### 便捷方法

```python
def process_sync(tables, query, config) -> ProcessResult:
    """同步处理，忽略中间事件，直接返回结果"""

def process_with_events(tables, query, config) -> tuple[List[ProcessEvent], ProcessResult]:
    """处理并收集所有事件"""
```

## 使用示例

### Fixture 测试

```python
# 快速测试 - 只关心结果
tables = ExcelParser.parse_file_all_sheets(Path("fixtures/01-titanic/datasets/titanic.xlsx"))
processor = ExcelProcessor(llm_client)
result = processor.process_sync(tables, query, ProcessConfig(stream_llm=False))
assert not result.has_errors()

# 调试测试 - 查看中间过程
events, result = processor.process_with_events(tables, query, ProcessConfig(stream_llm=False))
for event in events:
    print(f"[{event.stage}] {event.event_type}: {event.output}")
```

### Chat API (SSE)

```python
processor = ExcelProcessor(llm_client)
gen = processor.process(tables, query, ProcessConfig(stream_llm=True))

for event in gen:
    if event.event_type == EventType.STAGE_START:
        yield sse_step_running(event.stage.value)
    elif event.event_type == EventType.STAGE_STREAM:
        yield sse_step_streaming(event.stage.value, event.delta)
    elif event.event_type == EventType.STAGE_DONE:
        yield sse_step_done(event.stage.value, event.output)
```

## 配置组合

| 场景             | stream_llm | 使用方式                 | 效果             |
| ---------------- | ---------- | ------------------------ | ---------------- |
| Fixture 快速测试 | False      | `process_sync()`         | 直接返回结果     |
| Fixture 调试     | False      | `process_with_events()`  | 收集所有阶段输出 |
| Chat SSE 流式    | True       | `for event in process()` | 实时推送增量     |
| Chat SSE 非流式  | False      | `for event in process()` | 推送开始/完成    |

## 文件结构

```
apps/api/app/
├── processor/                    # 处理器模块（Layer 2）
│   ├── __init__.py
│   ├── types.py                  # ProcessStage, EventType, ProcessEvent, etc.
│   ├── excel_processor.py        # ExcelProcessor 实现
│   └── stages/                   # 各阶段实现
│       ├── __init__.py
│       ├── analyze.py            # AnalyzeStage
│       ├── generate.py           # GenerateStage（单独使用）
│       ├── validate.py           # ValidateStage（单独使用）
│       ├── generate_validate.py  # GenerateValidateStage（复合阶段）
│       └── execute.py            # ExecuteStage
├── engine/                       # 引擎层（Layer 3）：核心原子操作
│   ├── __init__.py
│   ├── models.py                 # 数据模型定义
│   ├── llm_client.py             # LLM 客户端
│   ├── parser.py                 # JSON 操作解析器
│   ├── executor.py               # 操作执行引擎
│   ├── excel_generator.py        # Excel 公式生成器
│   ├── excel_parser.py           # Excel 文件解析器
│   ├── functions.py              # Excel 函数实现
│   ├── prompt.py                 # LLM 提示词
│   └── step_tracker.py           # 步骤追踪器
├── core/                         # 基础设施层：通用配置和工具
│   ├── config.py                 # 配置
│   ├── database.py               # 数据库
│   ├── base.py                   # ORM 基类
│   └── jwt.py                    # JWT 认证
└── api/routes/
    ├── chat.py                   # Chat API：使用 ExcelProcessor
    └── fixture.py                # Fixture API
```
