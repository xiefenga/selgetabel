# LLM Excel API

LLM 辅助 Excel 数据处理系统的 API 服务。

## 核心特点

- **两步 LLM 流程**：需求分析 → 生成操作，提高准确性
- **结构化 JSON 操作**：公式表达式使用 JSON 对象，避免字符串解析问题
- **100% Excel 可复现**：所有结果可用 Excel 公式验证
- **RESTful API**：支持分步调用或一键处理

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境变量

```bash
cp env.example .env
# 编辑 .env，设置 OPENAI_API_KEY
```

### 3. 启动服务

```bash
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

或从项目根目录：

```bash
pnpm dev:api
```

## API 端点

### 基础

| 方法 | 路径    | 说明         |
| ---- | ------- | ------------ |
| GET  | `/`     | 健康检查     |
| GET  | `/docs` | Swagger 文档 |

### 核心流程

| 方法 | 路径        | 说明                             |
| ---- | ----------- | -------------------------------- |
| POST | `/upload`   | 上传 Excel 文件，返回 session_id |
| POST | `/analyze`  | 第一步：LLM 需求分析             |
| POST | `/generate` | 第二步：生成 JSON 操作描述       |
| POST | `/execute`  | 第三步：执行操作并导出           |
| POST | `/process`  | 一键处理（包含以上全部）         |

### 辅助

| 方法   | 路径                    | 说明               |
| ------ | ----------------------- | ------------------ |
| GET    | `/download/{filename}`  | 下载结果文件       |
| DELETE | `/session/{session_id}` | 删除会话           |
| GET    | `/sessions`             | 列出会话（调试用） |

## 使用示例

### 一键处理

```bash
# 1. 上传文件
curl -X POST http://localhost:8000/upload \
  -F "files=@data/贴现发生额明细.xlsx" \
  -F "files=@data/卖断发生额明细.xlsx"

# 响应: {"session_id": "abc123", "tables": {...}, "message": "..."}

# 2. 一键处理
curl -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc123",
    "requirement": "检查贴现表中的票据是否在卖断表中存在，新增卖断列"
  }'

# 3. 下载结果
curl -O http://localhost:8000/download/output_abc123_20260115.xlsx
```

### 分步调用（可干预）

```bash
# 1. 上传文件（同上）

# 2. 需求分析
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"session_id": "abc123", "requirement": "..."}'

# 3. 生成操作（可添加用户反馈）
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc123",
    "requirement": "...",
    "analysis": "...",
    "user_feedback": "请使用 COUNTIFS 进行匹配"
  }'

# 4. 执行
curl -X POST http://localhost:8000/execute \
  -H "Content-Type: application/json" \
  -d '{"session_id": "abc123", "operations_json": "..."}'
```

## 支持的操作类型

### aggregate - 整列聚合

```json
{
  "type": "aggregate",
  "function": "SUMIF",
  "table": "orders",
  "column": "amount",
  "condition_column": "status",
  "condition": "已完成",
  "as": "total"
}
```

### add_column - 新增计算列

```json
{
  "type": "add_column",
  "table": "orders",
  "name": "折扣价",
  "formula": {
    "op": "*",
    "left": { "col": "price" },
    "right": { "value": 0.9 }
  }
}
```

### compute - 标量运算

```json
{
  "type": "compute",
  "expression": {
    "op": "-",
    "left": { "var": "income" },
    "right": { "var": "expense" }
  },
  "as": "profit"
}
```

## 表达式对象格式

| 类型     | 格式                                         | 说明           |
| -------- | -------------------------------------------- | -------------- |
| 字面量   | `{"value": 100}`                             | 常量值         |
| 列引用   | `{"col": "price"}`                           | 当前行的列值   |
| 跨表引用 | `{"ref": "table.column"}`                    | 另一表的整列   |
| 变量引用 | `{"var": "total"}`                           | 前面定义的变量 |
| 函数调用 | `{"func": "IF", "args": [...]}`              | 函数调用       |
| 二元运算 | `{"op": ">", "left": {...}, "right": {...}}` | 二元运算       |

## 支持的函数

### 聚合函数

SUM, COUNT, COUNTA, AVERAGE, MIN, MAX, SUMIF, COUNTIF, AVERAGEIF

### 行级函数

IF, AND, OR, NOT, COUNTIFS, VLOOKUP, IFERROR, ROUND, ABS, LEFT, RIGHT, MID, LEN, TRIM, UPPER, LOWER, TEXT, VALUE

### 标量函数

ROUND, ABS, MAX, MIN

## 项目结构

```
apps/api/
├── main.py             # FastAPI 应用入口
├── models.py           # 数据模型
├── executor.py         # 执行引擎 + JSON 表达式求值
├── parser.py           # JSON 解析器
├── functions.py        # 函数实现
├── excel_parser.py     # Excel 解析
├── excel_generator.py  # Excel 公式生成
├── llm_client.py       # LLM 客户端（两步调用）
├── prompt.py           # 需求分析 + 生成操作提示词
├── pyproject.toml      # 依赖配置
└── data/               # 示例数据
```

## 技术规范

详见 [OPERATION_SPEC.md](../../docs/OPERATION_SPEC.md)
