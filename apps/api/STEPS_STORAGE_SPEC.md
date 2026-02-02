# ThreadTurn Steps 存储方案

本文档定义了 `ThreadTurn` 表中 `steps` 字段的存储结构，用于记录聊天处理流程的执行历史。

## 一、设计目标

1. **结构清晰**：与 SSE 事件协议对齐，便于理解
2. **扩展性强**：流程变更无需修改表结构
3. **支持重试**：同一步骤可多次执行，保留完整历史
4. **便于回填**：前端可直接使用数据渲染历史消息

## 二、数据结构

### 2.1 ThreadTurn.steps 字段

类型：`JSONB`（数组）

```json
[
  {
    "step": "load",
    "status": "done",
    "output": { "files": [...] },
    "started_at": "2025-01-28T10:00:00Z",
    "completed_at": "2025-01-28T10:00:01Z"
  },
  {
    "step": "generate",
    "status": "error",
    "error": { "code": "LLM_TIMEOUT", "message": "请求超时" },
    "started_at": "2025-01-28T10:00:01Z",
    "completed_at": "2025-01-28T10:00:31Z"
  },
  {
    "step": "generate",
    "status": "done",
    "output": { "operations": [...] },
    "started_at": "2025-01-28T10:00:32Z",
    "completed_at": "2025-01-28T10:00:40Z"
  },
  {
    "step": "validate",
    "status": "done",
    "output": { "valid": true },
    "started_at": "...",
    "completed_at": "..."
  },
  {
    "step": "execute",
    "status": "done",
    "output": {
      "strategy": "...",
      "manual_steps": "...",
      "variables": {...},
      "new_columns": {...}
    },
    "started_at": "...",
    "completed_at": "..."
  },
  {
    "step": "export",
    "status": "done",
    "output": { "output_files": [...] },
    "started_at": "...",
    "completed_at": "..."
  }
]
```

### 2.2 字段说明

| 字段           | 类型   | 必填 | 说明                                                |
| -------------- | ------ | ---- | --------------------------------------------------- |
| `step`         | string | 是   | 步骤名称：load, generate, validate, execute, export |
| `status`       | string | 是   | 状态：running, done, error                          |
| `output`       | object | 否   | 步骤输出（仅 status=done 时）                       |
| `error`        | object | 否   | 错误信息（仅 status=error 时）                      |
| `started_at`   | string | 是   | 开始时间（ISO 8601）                                |
| `completed_at` | string | 否   | 完成时间（ISO 8601）                                |

### 2.3 各步骤 output 结构

| step       | output 内容                                                                         |
| ---------- | ----------------------------------------------------------------------------------- |
| `load`     | `{ "files": [...] }`                                                                |
| `generate` | `{ "operations": [...] }`                                                           |
| `validate` | `{ "valid": true }`                                                                 |
| `execute`  | `{ "strategy": "...", "manual_steps": "...", "variables": {...}, "errors": [...] }` |
| `export`   | `{ "output_files": [...] }`                                                         |

### 2.4 error 结构

```json
{
  "code": "LLM_TIMEOUT",
  "message": "请求超时，请重试"
}
```

错误码参见 `SSE_SPEC.md`。

## 三、状态流转

### 3.1 单步骤生命周期

```
running → done    (成功)
running → error   (失败)
```

### 3.2 重试场景

同一步骤可出现多次，按执行顺序追加：

```json
[
  { "step": "generate", "status": "error", ... },
  { "step": "generate", "status": "done", ... }
]
```

前端回填时取最后一条记录作为最终状态。

## 四、与 SSE 事件的对应关系

| SSE 事件                                             | steps 记录                                                          |
| ---------------------------------------------------- | ------------------------------------------------------------------- |
| `{ "step": "X", "status": "running" }`               | 追加 `{ "step": "X", "status": "running", "started_at": "..." }`    |
| `{ "step": "X", "status": "done", "output": {...} }` | 更新最后一条 X 记录：`status="done"`, 添加 `output`, `completed_at` |
| `{ "step": "X", "status": "error", "error": {...} }` | 更新最后一条 X 记录：`status="error"`, 添加 `error`, `completed_at` |

注意：`streaming` 状态不持久化，仅用于实时传输增量内容。

## 五、前端回填逻辑

### 5.1 获取每个步骤的最终状态

```typescript
function getLatestSteps(steps: StepRecord[]): Record<string, StepRecord> {
  return steps.reduce(
    (acc, step) => {
      acc[step.step] = step; // 后来的覆盖先前的
      return acc;
    },
    {} as Record<string, StepRecord>
  );
}

// 使用
const latest = getLatestSteps(turn.steps);
if (latest.load?.status === "done") {
  setFiles(latest.load.output.files);
}
if (latest.generate?.status === "done") {
  setOperations(latest.generate.output.operations);
}
```

### 5.2 展示重试历史（可选）

```typescript
const generateAttempts = steps.filter((s) => s.step === "generate");
// 可展示 "尝试了 N 次"
```

## 六、数据库模型变更

### 6.1 简化后的 ThreadTurn

```python
class ThreadTurn(Base):
    __tablename__ = "thread_turns"

    id: Mapped[UUID]
    thread_id: Mapped[UUID]
    turn_number: Mapped[int]

    user_query: Mapped[str]           # 用户输入
    status: Mapped[str]               # pending | processing | completed | failed
    steps: Mapped[list]               # JSONB - 步骤数组（核心字段）

    created_at: Mapped[datetime]
    started_at: Mapped[Optional[datetime]]
    completed_at: Mapped[Optional[datetime]]
```

### 6.2 删除的内容

- **TurnResult 表**：合并到 `steps[execute].output`
- **ThreadTurn.operations_json**：移入 `steps[generate].output.operations`
- **ThreadTurn.error_message**：移入 `steps[].error.message`

## 七、版本历史

| 版本 | 日期       | 变更     |
| ---- | ---------- | -------- |
| 1.0  | 2025-01-28 | 初始版本 |
