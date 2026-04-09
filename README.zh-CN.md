# Selgetabel

[English](README.md)

基于大模型的 Excel 数据处理系统。用自然语言描述需求，自动生成结构化操作、公式，并导出可下载的 Excel 文件。

## 工作原理

1. 上传 Excel 文件
2. 用自然语言描述数据处理需求
3. 大模型生成结构化 JSON 操作（非直接生成公式）
4. 引擎执行操作，产出带有真实公式的 Excel 文件

所有公式 100% 可复现 —— 不直接执行 LLM 生成的代码。

## 技术栈

| 层级 | 技术                                            |
| ---- | ----------------------------------------------- |
| 前端 | React Router v7、Vite、TypeScript、Tailwind CSS |
| 后端 | Python FastAPI、多 LLM Provider 支持            |
| 存储 | PostgreSQL、MinIO（S3 兼容）                    |
| 基建 | pnpm workspace、Turborepo、Docker Compose       |

## 快速开始（Docker 部署）

### 前置要求

- Docker & Docker Compose

### 部署步骤

```bash
# 克隆并进入项目
git clone https://github.com/xiefenga/selgetabel.git
cd selgetabel/docker

# 创建环境配置
cp .env.example .env
```

编辑 `.env`，配置以下必要变量：

```bash
# 必须配置
POSTGRES_PASSWORD=strong_password   # 数据库密码
MINIO_ROOT_PASSWORD=strong_password # 对象存储密码
JWT_SECRET_KEY=xxx                  # 生成命令：openssl rand -hex 32
```

启动服务：

```bash
docker compose up -d

# 访问应用：http://localhost:8080
```

启动后，通过管理后台（设置 > LLM 供应商）配置大模型。详见 [LLM 多供应商](#llm-多供应商)。

### 版本升级

```bash
cd docker
./scripts/upgrade.sh <版本号>
```

## 本地开发

### 前置要求

- Node.js 22+ / pnpm 10+
- Python 3.11+
- PostgreSQL & MinIO（或使用 `docker compose -f docker/docker-compose.dev.yml up -d`）

### 安装与启动

```bash
# 安装前端依赖
pnpm install

# 安装后端依赖
pnpm --filter @selgetabel/api install

# 启动全部服务
pnpm dev
```

| 服务     | 地址                       |
| -------- | -------------------------- |
| 前端     | http://localhost:5173      |
| API      | http://localhost:8000      |
| API 文档 | http://localhost:8000/docs |

### 常用命令

```bash
pnpm dev          # 启动前端 + API
pnpm dev:api      # 仅启动 API
pnpm build        # 构建所有包
pnpm format       # 代码格式化（Prettier）
pnpm check-types  # 类型检查
```

## 项目架构

```
selgetabel/
├── apps/
│   ├── api/           # Python FastAPI 后端
│   │   ├── app/
│   │   │   ├── main.py        # 应用入口
│   │   │   ├── api/routes/    # 路由处理
│   │   │   ├── engine/        # 核心：解析器、执行器、公式生成、意图分类器
│   │   │   ├── processor/     # 处理流水线阶段
│   │   │   ├── services/      # 业务逻辑：聊天、意图、上下文、文件 I/O、认证
│   │   │   ├── persistence/   # 数据访问层
│   │   │   ├── models/        # SQLAlchemy ORM 模型
│   │   │   └── core/          # 配置、数据库、JWT
│   │   └── pyproject.toml
│   └── web/           # React Router v7 前端
│       ├── app/
│       │   ├── routes/        # 基于文件的路由
│       │   ├── components/    # 共享 UI 组件
│       │   ├── features/      # 功能模块
│       │   └── lib/           # 工具函数 & API 客户端
│       └── vite.config.ts
├── docker/            # Docker Compose 部署
├── docs/              # 技术文档
│   ├── design/        # 系统设计与架构
│   ├── specs/         # 协议与格式规范
│   ├── conventions/   # 编码规范与工作流
│   └── guides/        # 操作指南
├── package.json
├── pnpm-workspace.yaml
└── turbo.json
```

**核心引擎组件：**
- `intent_classifier.py` — 基于 LLM 的意图分类（CHAT/ANALYSIS/PROCESSING/UNCLEAR）
- `context_builder.py` — 根据意图类型格式化 LLM 提示词上下文
- `excel_generator.py` — 将 JSON 表达式转换为 Excel 公式
- `llm_client.py` — 统一的 LLM API 接口，支持多供应商

**核心服务：**
- `intent_service.py` — 编排意图识别和路由决策
- `context_service.py` — 管理多轮对话上下文
- `chat_stream.py` — 为非处理类意图流式返回聊天响应

### LLM 多供应商

系统支持多 LLM 供应商，配置存储在数据库中。通过管理 API（`/llm/*`）管理供应商、模型和凭证。

**已支持的供应商：**

| 供应商           | 类型标识            | 状态   |
| ---------------- | ------------------- | ------ |
| OpenAI           | `openai`            | 可用   |
| OpenAI 兼容      | `openai_compatible` | 可用   |
| Anthropic        | `anthropic`         | 规划中 |
| Azure OpenAI     | `azure_openai`      | 规划中 |
| DeepSeek         | `deepseek`          | 规划中 |
| Qwen（通义千问） | `qwen`              | 规划中 |
| Ollama           | `ollama`            | 规划中 |

**阶段级路由** —— 不同处理阶段（intent、generate、title）可使用不同的供应商/模型组合。

详见 [LLM Provider 设计文档](docs/design/LLM_PROVIDER_DESIGN.md)。

### 意图分类

系统使用基于 LLM 的意图分类来理解用户查询并合理路由：

| 意图        | 说明                                         |
| ----------- | -------------------------------------------- |
| `chat`      | 纯对话，不涉及文件处理（如打招呼、功能咨询等） |
| `analysis`  | 数据分析/总结，不修改数据                     |
| `processing`| 数据处理，修改/转换/导出数据                 |
| `unclear`   | 需求不明确或缺少参数，需要进一步澄清          |

**分类规则：**
- 未上传文件时，意图不能为 `analysis` 或 `processing`，必须为 `chat`
- 如果用户指令模糊（如只说了"分组"但没说按哪列分组），系统返回 `unclear` 并附带澄清问题
- 如果用户给出简短回复如"是"、"对"或仅提供一个列名，系统继承上一轮对话的意图

**澄清流程：** 当意图为 `unclear` 或需要澄清时，系统会先友好地提出追问，再继续执行。

### 多轮对话

系统通过 **Thread/Turn** 模型维护对话上下文：

- **Thread**：包含多个 Turn 的会话
- **Turn**：一次交互（用户查询 → 系统响应）
- **上下文快照**：每个 Turn 可以保存其上下文状态供后续参考
- **文件继承**：当用户在新的 Turn 中未上传文件时，系统自动继承之前的文件

**上下文类型** 根据意图类型构建：
- `chat`：对话历史、话题连续性分析
- `analysis`：历史分析记录、数据洞察、文件分析历史
- `processing`：操作历史、数据状态、可用文件、文件依赖关系

### 处理流水线

后端通过 SSE 事件流推送多阶段处理进度：

```
意图识别 → 生成 + 验证（LLM，带自动重试）→ 执行 → 导出
```

- **意图识别**：LLM 分类用户意图（chat/analysis/processing/unclear）
- **生成**：LLM 将自然语言转换为结构化 JSON 操作
- **验证**：解析器校验格式并检查函数白名单（验证失败时自动重试）
- **执行**：引擎运行操作并生成 Excel 公式
- **导出**：输出带有嵌入公式的 `.xlsx` 文件

### 支持的操作

| 操作             | 说明                             |
| ---------------- | -------------------------------- |
| `aggregate`      | 列聚合（SUM、AVERAGE、SUMIF 等） |
| `add_column`     | 添加带公式的计算列               |
| `update_column`  | 更新已有列的值                   |
| `compute`        | 基于变量的标量计算               |
| `filter`         | 按条件筛选行                     |
| `sort`           | 按列排序                         |
| `group_by`       | 分组聚合                         |
| `take`           | 限制行数                         |
| `select_columns` | 选择特定列                       |
| `drop_columns`   | 删除列                           |
| `create_sheet`   | 创建新工作表                     |
| `pivot`          | 数据透视表（交叉表）             |

### 数据分析

上传 Excel 文件后，可用自然语言提出分析需求。系统提取数据画像、检测质量问题，并通过 LLM 生成洞察报告。

**分析场景**：

| 层次 | 场景 | 示例 |
| ---- | ---- | ---- |
| L1：信息提取 | 基本概况 | "这份数据大概是什么？" |
| L1：信息提取 | 数据质量 | "这份数据有什么问题吗？" |
| L2：通用分析 | 开放分析 | "分析一下这份数据" |
| L2：通用分析 | 指定维度 | "各地区的销售情况怎么样？" |
| L2：通用分析 | 多表联合 | "结合客户表分析订单" |
| L3：专项分析 | 相关性 | "销售额和销量有什么关系？" |
| L3：专项分析 | 对比分析 | "华东和华南有什么差异？" |
| L3：专项分析 | 趋势分析 | "销售额有什么变化趋势？" |
| L3：专项分析 | 分布描述 | "各产品销售分布怎么样？" |
| L4：智能推断 | 原因归因 | "为什么 C 地区销售额最高？" |
| L4：智能推断 | 关系发现 | "这些列之间有什么关系？" |

## 相关文档

- [操作规范](docs/specs/OPERATION_SPEC.md) — JSON 操作格式说明
- [SSE 协议](docs/specs/SSE_SPEC.md) — Server-Sent Events 协议
- [步骤存储](docs/specs/STEPS_STORAGE_SPEC.md) — ThreadTurn 步骤格式
- [LLM Provider 设计](docs/design/LLM_PROVIDER_DESIGN.md) — 多供应商架构
- [引擎架构](docs/design/ENGINE_ARCHITECTURE.md) — 核心引擎设计
- [数据库设计](docs/design/DATABASE_DESIGN.md) — 数据模型
- [Docker 脚本](docs/guides/DOCKER_SCRIPTS.md) — 部署脚本指南

## 许可证

[Apache-2.0](LICENSE)
