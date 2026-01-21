# LLM Excel 数据处理系统

用自然语言描述 Excel 数据处理需求，由后端调用大模型生成可执行的结构化操作，并返回预览、公式与导出的 Excel 文件。

## 项目结构

```
llm-excel/
├── apps/
│   ├── api/                    # Python FastAPI 后端（SSE）
│   │   ├── app/
│   │   │   ├── main.py          # FastAPI 入口：app.main:app
│   │   │   ├── api/             # 路由（/excel/*）
│   │   │   ├── lib/             # JSON 解析/执行/公式生成等
│   │   │   └── services/        # Excel 读写与文件管理
│   │   └── pyproject.toml       # Python 依赖（uv）
│   └── web/                     # 前端（React Router v7 + Vite）
│       ├── app/                 # UI 与页面
│       └── vite.config.ts       # /api -> 后端代理
├── package.json                 # monorepo 脚本入口
├── pnpm-workspace.yaml          # pnpm workspace
└── turbo.json                   # turborepo 任务编排
```

## 环境要求

- **Node.js**：>= 22（仓库内有 Volta 版本约束）
- **pnpm**：>= 10
- **Python**：>= 3.11
- **uv**：用于安装/运行后端依赖

## 快速开始（本地开发）

### 1) 安装前端依赖

```bash
pnpm install
```

### 2) 安装后端依赖（apps/api）

```bash
pnpm --filter @llm-excel/api install
```

### 3) 配置后端环境变量

在 `apps/api` 下创建 `.env`（或直接在 shell 里导出环境变量），至少需要：

- `OPENAI_API_KEY`

（如果仓库里提供了 `.env.example`，可复制一份改名为 `.env`。）

### 4) 启动开发环境（Web + API 一起起）

```bash
pnpm dev
```

- Web：`http://localhost:5173`
- API：`http://localhost:8000`（Swagger：`http://localhost:8000/docs`）

## Web 与 API 的联调方式

前端代码里默认请求基路径为 `'/api'`，开发时由 `apps/web/vite.config.ts` 代理到后端：

- 默认后端地址：`http://localhost:8000`
- 如需自定义，启动前设置环境变量：`API_BASE_URL=http://your-api-host:8000`

## API 概要

当前核心接口为：

- `POST /excel/upload`：上传一个或多个 Excel 文件，返回 `file_id`（每个文件独立）。
- `POST /excel/chat`：传入 `query` 与 `file_ids`，以 **SSE** 流式返回 load / analysis / generate / execute 等阶段事件。

文件访问：

- API 会把文件写到 `storage/` 下，并在应用里挂载为静态目录：`/storage/*`
- 执行完成后返回的 `output_file` 一般形如 `storage/outputs/result_YYYYmmdd_HHMMSS.xlsx`，可通过 `http://localhost:8000/storage/outputs/...` 访问（也可直接从返回的路径拼出 URL）。

## 常用命令

```bash
# 启动全部（web + api）
pnpm dev

# 只启动后端
pnpm dev:api

# 构建
pnpm build

# 类型检查（若各包实现了对应脚本）
pnpm check-types

# 格式化（ts/tsx/md）
pnpm format
```

## 相关文档

- 后端更详细的说明在 `apps/api/README.md`、`apps/api/SPEC.md`、`apps/api/USAGE.md`
