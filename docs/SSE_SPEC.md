# SSE 事件协议规范

本文档定义了 `/chat` 接口的 SSE (Server-Sent Events) 事件协议。

## 一、协议概述

### 1.1 设计原则

1. **分类清晰**：使用 SSE 的 `event` 字段区分事件类型
2. **语义化**：事件和状态命名直观易懂
3. **扩展性强**：支持流式输出、错误分类等场景
4. **关注点分离**：会话元数据、业务流程、错误各自独立

### 1.2 事件类型

| event 字段  | 用途              | 触发时机                                          |
| ----------- | ----------------- | ------------------------------------------------- |
| `session`   | 会话元数据        | 会话/消息创建完成后                               |
| `error`     | 会话级/系统级错误 | 会话创建失败、系统异常                            |
| _(default)_ | 业务流程步骤      | 处理过程中（不指定 event，使用默认 message 事件） |

---

## 二、事件详细定义

### 2.1 Session 事件

会话和消息数据创建完成后发送，表示"聊天已开始"。

```
event: session
data: {
  "thread_id": "uuid-string",
  "turn_id": "uuid-string",
  "title": "自动生成的会话标题",
  "is_new_thread": true
}
```

| 字段            | 类型    | 说明                         |
| --------------- | ------- | ---------------------------- |
| `thread_id`     | string  | 会话 ID                      |
| `turn_id`       | string  | 当前轮次 ID                  |
| `title`         | string  | 会话标题（新会话时自动生成） |
| `is_new_thread` | boolean | 是否为新创建的会话           |

---

### 2.2 业务流程事件（默认 message）

业务处理步骤的状态更新，不指定 `event` 字段（使用 SSE 默认的 message 事件）。

#### 数据结构

```json
{
  "step": "load | analyze | generate | validate | execute",
  "status": "running | streaming | done | error",
  "stage_id": "uuid-string",
  "delta": "增量内容（streaming 时）",
  "output": { ... },
  "error": { "code": "...", "message": "..." }
}
```

| 字段       | 类型   | 说明                                           |
| ---------- | ------ | ---------------------------------------------- |
| `step`     | string | 当前步骤名称                                   |
| `status`   | string | 步骤状态                                       |
| `stage_id` | string | 阶段实例唯一标识（重试时每次生成新 id）        |
| `delta`    | string | 增量内容（仅 `streaming` 状态）                |
| `output`   | object | 完整输出（仅 `done` 状态）                     |
| `error`    | object | 错误信息（仅 `error` 状态）                    |

**关于 stage_id**：
- 每个阶段实例都有唯一的 `stage_id`
- 同一 `stage_id` 的事件属于同一次执行（running → streaming → done/error）
- 验证失败重试时，会生成新的 `stage_id`，前端可据此区分不同尝试

#### 步骤定义

| step       | 说明     | output 内容                                              |
| ---------- | -------- | -------------------------------------------------------- |
| `load`     | 加载文件 | `{ "schemas": [...] }`                                   |
| `analyze`  | 需求分析 | `{ "content": "分析结果" }`                              |
| `generate` | 生成操作 | `{ "operations": [...] }`                                |
| `validate` | 验证操作 | `{ "valid": true, "operation_count": 3, "errors": [] }`  |
| `execute`  | 执行操作 | `{ "formulas": [...], "output_file": "..." }`            |

#### 状态流转

```
running → streaming → done    (正常流程，有流式输出)
running → done                (正常流程，无流式输出)
running → error               (步骤失败)
running → streaming → error   (流式输出中失败)
```

#### 状态说明

| status      | 说明         | 包含字段         |
| ----------- | ------------ | ---------------- |
| `running`   | 步骤开始执行 | `step`           |
| `streaming` | 流式输出中   | `step`, `delta`  |
| `done`      | 步骤完成     | `step`, `output` |
| `error`     | 步骤失败     | `step`, `error`  |

#### 示例事件序列

```
data: { "step": "load", "stage_id": "a1b2c3...", "status": "running" }
data: { "step": "load", "stage_id": "a1b2c3...", "status": "done", "output": { "schemas": [...] } }

data: { "step": "analyze", "stage_id": "d4e5f6...", "status": "running" }
data: { "step": "analyze", "stage_id": "d4e5f6...", "status": "streaming", "delta": "首先" }
data: { "step": "analyze", "stage_id": "d4e5f6...", "status": "streaming", "delta": "，我们需要" }
data: { "step": "analyze", "stage_id": "d4e5f6...", "status": "done", "output": { "content": "完整分析内容" } }

data: { "step": "generate", "stage_id": "g7h8i9...", "status": "running" }
data: { "step": "generate", "stage_id": "g7h8i9...", "status": "done", "output": { "operations": [...] } }

data: { "step": "validate", "stage_id": "j1k2l3...", "status": "running" }
data: { "step": "validate", "stage_id": "j1k2l3...", "status": "done", "output": { "valid": true, "operation_count": 3 } }

data: { "step": "execute", "stage_id": "m4n5o6...", "status": "running" }
data: { "step": "execute", "stage_id": "m4n5o6...", "status": "done", "output": { "formulas": [...], "output_file": "result.xlsx" } }

data: { "step": "complete", "status": "done" }
```

#### 验证重试示例

当验证失败时，会重新生成操作，每次生成新的 `stage_id`：

```
// 第一次尝试
data: { "step": "generate", "stage_id": "gen-001...", "status": "running" }
data: { "step": "generate", "stage_id": "gen-001...", "status": "done", "output": { "operations": [...] } }
data: { "step": "validate", "stage_id": "val-001...", "status": "running" }
data: { "step": "validate", "stage_id": "val-001...", "status": "done", "output": { "valid": false, "errors": ["列名不存在: Age"] } }

// 第二次尝试（重试）
data: { "step": "generate", "stage_id": "gen-002...", "status": "running" }
data: { "step": "generate", "stage_id": "gen-002...", "status": "done", "output": { "operations": [...] } }
data: { "step": "validate", "stage_id": "val-002...", "status": "running" }
data: { "step": "validate", "stage_id": "val-002...", "status": "done", "output": { "valid": true, "operation_count": 3 } }

// 继续执行
data: { "step": "execute", "stage_id": "exec-001...", "status": "running" }
data: { "step": "execute", "stage_id": "exec-001...", "status": "done", "output": { ... } }
```

---

### 2.3 Complete 事件

整个流程结束的显式信号。

```json
{
  "step": "complete",
  "status": "done",
  "output": {
    "thread_id": "uuid",
    "turn_id": "uuid"
  }
}
```

**注意**：`complete` 是一个特殊的 step，表示所有业务步骤已完成。

---

### 2.4 Error 事件

会话级或系统级错误，使用 `event: error`。

```
event: error
data: {
  "code": "FILE_NOT_FOUND",
  "message": "文件不存在或无权访问"
}
```

| 字段      | 类型   | 说明     |
| --------- | ------ | -------- |
| `code`    | string | 错误码   |
| `message` | string | 错误描述 |

#### 错误码定义

| code               | 说明       | 触发场景                          |
| ------------------ | ---------- | --------------------------------- |
| `THREAD_NOT_FOUND` | 会话不存在 | 指定的 thread_id 不存在或无权访问 |
| `FILE_NOT_FOUND`   | 文件不存在 | 指定的 file_id 不存在或无权访问   |
| `INVALID_PARAMS`   | 参数错误   | 请求参数格式错误                  |
| `INTERNAL_ERROR`   | 内部错误   | 未捕获的系统异常                  |

---

## 三、错误处理策略

### 3.1 错误分类

| 类型           | 处理方式        | 示例                    |
| -------------- | --------------- | ----------------------- |
| **会话级错误** | `event: error`  | 会话不存在、文件无权限  |
| **步骤级错误** | `status: error` | LLM 超时、JSON 解析失败 |
| **系统级错误** | `event: error`  | 数据库异常、未捕获错误  |

### 3.2 步骤失败处理

步骤失败后，流程立即停止，不会继续执行后续步骤。

```
data: { "step": "analyze", "status": "running" }
data: { "step": "analyze", "status": "error", "error": { "code": "LLM_TIMEOUT", "message": "LLM 请求超时" } }
// 流程结束，不会有 generate/execute 步骤
```

### 3.3 步骤错误码

| code                | 说明          |
| ------------------- | ------------- |
| `LOAD_FAILED`       | 文件加载失败  |
| `LLM_TIMEOUT`       | LLM 请求超时  |
| `LLM_ERROR`         | LLM 调用失败  |
| `PARSE_FAILED`      | JSON 解析失败 |
| `VALIDATION_FAILED` | 操作校验失败  |
| `EXECUTE_FAILED`    | 执行失败      |

---

## 四、完整事件流示例

### 4.1 成功流程

```
event: session
data: { "thread_id": "abc", "turn_id": "def", "title": "计算订单总额", "is_new_thread": true }

data: { "step": "load", "stage_id": "load-001", "status": "running" }
data: { "step": "load", "stage_id": "load-001", "status": "done", "output": { "schemas": [...] } }

data: { "step": "analyze", "stage_id": "ana-001", "status": "running" }
data: { "step": "analyze", "stage_id": "ana-001", "status": "streaming", "delta": "根据需求..." }
data: { "step": "analyze", "stage_id": "ana-001", "status": "done", "output": { "content": "完整分析" } }

data: { "step": "generate", "stage_id": "gen-001", "status": "running" }
data: { "step": "generate", "stage_id": "gen-001", "status": "done", "output": { "operations": [...] } }

data: { "step": "validate", "stage_id": "val-001", "status": "running" }
data: { "step": "validate", "stage_id": "val-001", "status": "done", "output": { "valid": true, "operation_count": 3 } }

data: { "step": "execute", "stage_id": "exec-001", "status": "running" }
data: { "step": "execute", "stage_id": "exec-001", "status": "done", "output": { "formulas": [...], "output_file": "result.xlsx" } }

data: { "step": "complete", "status": "done", "output": { "thread_id": "abc", "turn_id": "def" } }
```

### 4.2 步骤失败

```
event: session
data: { "thread_id": "abc", "turn_id": "def", "title": "...", "is_new_thread": false }

data: { "step": "load", "status": "running" }
data: { "step": "load", "status": "done", "output": { "schemas": [...] } }

data: { "step": "analyze", "status": "running" }
data: { "step": "analyze", "status": "error", "error": { "code": "LLM_TIMEOUT", "message": "LLM 请求超时，请重试" } }
// 流程结束
```

### 4.3 会话级错误

```
event: error
data: { "code": "FILE_NOT_FOUND", "message": "文件不存在或无权访问: abc-123" }
// 流程结束
```

---

## 五、前端处理建议

### 5.1 事件订阅

```javascript
const eventSource = new EventSource("/chat");

// 会话创建
eventSource.addEventListener("session", (e) => {
  const data = JSON.parse(e.data);
  updateThreadInfo(data.thread_id, data.title);
});

// 业务流程（默认 message 事件）
eventSource.onmessage = (e) => {
  const data = JSON.parse(e.data);
  handleStep(data.step, data.status, data);
};

// 错误
eventSource.addEventListener("error", (e) => {
  const data = JSON.parse(e.data);
  showError(data.code, data.message);
});
```

### 5.2 步骤状态处理

```javascript
function handleStep(step, status, data) {
  switch (status) {
    case "running":
      showLoading(step);
      break;
    case "streaming":
      appendContent(step, data.delta);
      break;
    case "done":
      if (step === "complete") {
        onComplete(data.output);
      } else {
        setContent(step, data.output);
        hideLoading(step);
      }
      break;
    case "error":
      showStepError(step, data.error);
      break;
  }
}
```

---

## 六、版本历史

| 版本 | 日期       | 变更     |
| ---- | ---------- | -------- |
| 1.0  | 2025-01-28 | 初始版本 |
