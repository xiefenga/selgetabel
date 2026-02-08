# Selgetabel 数据处理系统

用自然语言描述 Excel 数据处理需求，由后端调用大模型生成可执行的结构化操作，并返回预览、公式与导出的 Excel 文件。

## 项目结构

```
Selgetabel/
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

## 部署与运行（Docker Compose）

```bash
# 在你想要部署的目录下执行
curl -fsSL https://raw.githubusercontent.com/xiefenga/selgetabel/main/install.sh | bash
```

脚本会自动：

1. 下载 `docker` 目录中的部署文件到**当前目录**
2. 从 `.env.example` 创建 `.env` 配置文件
3. 显示详细的后续配置步骤

完成后，按照提示：

```bash
# 1. 配置环境变量（注意：所有文件都在当前目录）
vi .env

# 必须修改的配置：
# - OPENAI_API_KEY=xxx                  # OpenAI API 密钥
# - POSTGRES_PASSWORD=strong_password   # 数据库密码
# - MINIO_ROOT_PASSWORD=strong_password # MinIO 密码
# - JWT_SECRET_KEY=xxx                  # 使用 openssl rand -hex 32 生成

# 2. 启动服务
docker compose up -d

# 3. 访问应用
# http://localhost:8080
```

---

## 相关文档

- **版本管理**: [VERSION.md](VERSION.md) - 版本号规则和发布流程
- **环境变量**: [ENV.md](ENV.md) - 环境变量配置说明
- **后端 API**: [apps/api/README.md](apps/api/README.md) - 后端 API 详细文档
- **操作规范**: [docs/OPERATION_SPEC.md](docs/OPERATION_SPEC.md) - JSON 操作规范说明
