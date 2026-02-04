# 数据库设置指南

## 1. 安装依赖

```bash
cd apps/api
uv sync
```

## 2. 配置数据库

复制 `.env.example` 为 `.env` 并配置数据库连接：

```bash
cp .env.example .env
```

编辑 `.env` 文件，设置数据库连接：

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/selgetabel
```

## 3. 创建数据库

```bash
# 使用 psql 创建数据库
createdb selgetabel

# 或使用 SQL
psql -U postgres -c "CREATE DATABASE selgetabel;"
```

## 4. 初始化 Alembic（如果还没有）

如果 `alembic` 目录不存在，运行：

```bash
cd apps/api
alembic init alembic
```

然后更新 `alembic/env.py` 中的配置（已包含在项目中）。

## 5. 创建初始迁移

```bash
cd apps/api
alembic revision --autogenerate -m "Initial migration"
```

## 6. 执行迁移

```bash
alembic upgrade head
```

## 7. 验证

检查表是否创建成功：

```bash
psql -U postgres -d selgetabel -c "\dt"
```

应该看到以下表：
- users
- accounts
- roles
- permissions
- user_roles
- role_permissions
- refresh_tokens
- files
- threads
- thread_turns
- turn_results
- turn_files

## 模型文件结构

```
app/models/
├── __init__.py          # 导出所有模型
├── user.py              # User, Account
├── role.py              # Role, Permission, UserRole, RolePermission
├── auth.py              # RefreshToken
├── file.py              # File
└── thread.py            # Thread, ThreadTurn, TurnResult, TurnFile
```

## 使用数据库会话

在 FastAPI 路由中使用：

```python
from app.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

@router.get("/")
async def endpoint(db: AsyncSession = Depends(get_db)):
    # 使用 db 进行数据库操作
    result = await db.execute(select(User))
    users = result.scalars().all()
    return users
```

## 常用 Alembic 命令

```bash
# 创建新迁移
alembic revision --autogenerate -m "描述"

# 执行迁移
alembic upgrade head

# 回滚到上一个版本
alembic downgrade -1

# 查看当前版本
alembic current

# 查看迁移历史
alembic history
```
