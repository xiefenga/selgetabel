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
| `step`         | string | 是   | 步骤名称：load, generate, validate, execute, export, chat, analyze |
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
| `chat`     | `{ "content": "..." }` 或直接文本                                                  |
| `analyze`  | `{ "content": "...", "profile": {...}, "quality_report": [...], "analysis_type": "..." }` |

### 2.4 error 结构

```json
{
  "code": "LLM_TIMEOUT",
  "message": "请求超时，请重试"
}
```

错误码参见 [SSE_SPEC.md](./SSE_SPEC.md)。

## 三、状态流转

### 单步骤生命周期

```
running → done    (成功)
running → error   (失败)
```

### 重试场景

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

`streaming` 状态不持久化，仅用于实时传输增量内容。

## 五、前端回填

加载历史消息时，遍历 `steps` 数组，同一 `step` 取最后一条作为最终状态。可选展示重试次数。
