FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# uv (Python 包管理/运行器)
RUN pip install --no-cache-dir uv

FROM base AS deps

# 先拷贝依赖清单以利用缓存
COPY apps/api/pyproject.toml apps/api/uv.lock /app/

# 安装依赖（锁定版本）
RUN uv sync --frozen

FROM base AS runner

WORKDIR /app

# 拷贝已安装的虚拟环境与应用代码
COPY --from=deps /app/.venv /app/.venv
COPY apps/api/ /app/

# FastAPI 默认端口
EXPOSE 8000

# 运行 API（SSE 需要关闭代理缓冲，见 nginx 配置）
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
