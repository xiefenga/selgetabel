# 数据库设计方案

## 技术栈

- **数据库**: PostgreSQL 15+
- **ORM**: SQLAlchemy 2.0+ (异步)
- **驱动**: asyncpg
- **迁移工具**: Alembic
- **认证**: JWT (JSON Web Token)
- **密码加密**: bcrypt (通过 passlib)
- **JWT 库**: python-jose[cryptography]

## 数据模型设计

### 1. User（用户表）

存储用户基础信息，不包含登录凭证。

```python
class User(Base):
    __tablename__ = "users"

    # ========== 数据库实际存储的字段（Column）==========
    id: UUID (PK)               # 用户 ID
    username: str (unique)        # 用户名（唯一，用于显示）
    avatar: str (nullable)        # 头像 URL
    status: int                  # 状态: 0 正常, 1 禁用（默认 0）

    # 时间戳
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime (nullable)  # 最后登录时间

    # ========== Python 层面的关系定义（relationship，不存储在数据库）==========
    # - accounts: 通过 Account.user_id 外键关联（一对多）
    # - roles: 通过 UserRole 关联表关联到 Role（多对多）
    # - files: 通过 File.user_id 外键关联（一对多）
    # - threads: 通过 Thread.user_id 外键关联（一对多）
    # - refresh_tokens: 通过 RefreshToken.user_id 外键关联（一对多）
    accounts: List[Account]      # 用户的登录账户（关系定义，不存储）
    roles: List[Role]           # 用户的角色（关系定义，不存储）
    files: List[File]            # 用户上传的文件（关系定义，不存储）
    threads: List[Thread]       # 用户创建的线程（关系定义，不存储）
    refresh_tokens: List[RefreshToken]  # 用户的刷新令牌（关系定义，不存储）
```

**数据库表结构**（实际存储）:

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    username VARCHAR UNIQUE NOT NULL,
    avatar VARCHAR,
    status SMALLINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    last_login_at TIMESTAMP
);
```

**索引**:

- `idx_users_username`: `username` (唯一索引)
- `idx_users_created_at`: `created_at DESC`
- `idx_users_status`: `status`

**状态枚举**:

- `0`: 正常
- `1`: 禁用

**字段说明**:

- `username`: 必填，唯一，用于显示和标识用户
- `avatar`: 可选，头像 URL
- `status`: 用户状态，0 正常 / 1 禁用

**关系说明**:

- `User.accounts` 关系：通过 `Account` 表中的 `user_id` 外键字段关联，**不存储在 users 表中**
- `User.roles` 关系：通过 `UserRole` 关联表关联到 `Role`，**不存储在 users 表中**
- `User.files` 关系：通过 `File` 表中的 `user_id` 外键字段关联，**不存储在 users 表中**
- `User.threads` 关系：通过 `Thread` 表中的 `user_id` 外键字段关联，**不存储在 users 表中**
- `User.refresh_tokens` 关系：通过 `RefreshToken` 表中的 `user_id` 外键字段关联，**不存储在 users 表中**

### 2. Account（用户登录账户表）

存储用户的登录方式，支持多种登录方式（邮箱、手机、第三方 OAuth 等）。设计参考 [better-auth](https://www.better-auth.com/)。

```python
class Account(Base):
    __tablename__ = "accounts"

    # ========== 数据库实际存储的字段（Column）==========
    id: UUID (PK)               # 账户 ID
    account_id: str             # 第三方账户唯一标识（OAuth 为 provider 的 user id；credentials 为邮箱等）
    provider_id: str            # 登录方式: credentials, github, google, wechat 等
    user_id: UUID (FK -> User.id)  # 关联用户（外键）

    # OAuth 相关（第三方登录时使用）
    access_token: str (nullable)       # OAuth access token
    refresh_token: str (nullable)      # OAuth refresh token
    id_token: str (nullable)           # OIDC id token
    access_token_expires_at: datetime (nullable)   # access token 过期时间
    refresh_token_expires_at: datetime (nullable)  # refresh token 过期时间
    scope: str (nullable)              # OAuth scope

    # 本地账户（credentials）登录时使用
    password: str (nullable)    # 加密后的密码（bcrypt）

    # 时间戳
    created_at: datetime
    updated_at: datetime

    # ========== Python 层面的关系定义（relationship，不存储在数据库）==========
    # - user: 通过 user_id 外键反向关联到 User（多对一）
    user: User                   # 所属用户（关系定义，不存储）
```

**数据库表结构**（实际存储）:

```sql
CREATE TABLE accounts (
    id UUID PRIMARY KEY,
    account_id VARCHAR NOT NULL,
    provider_id VARCHAR NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    access_token TEXT,
    refresh_token TEXT,
    id_token TEXT,
    access_token_expires_at TIMESTAMP,
    refresh_token_expires_at TIMESTAMP,
    scope VARCHAR,
    password VARCHAR,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    UNIQUE(provider_id, account_id)  -- 同一 provider 下 account_id 唯一
);
```

**索引**:

- `idx_accounts_user_id`: `user_id`
- `idx_accounts_provider_account`: `(provider_id, account_id)` (唯一索引)
- `idx_accounts_provider_id`: `provider_id`

**provider_id 枚举**:

- `credentials`: 邮箱/用户名+密码登录
- `github`: GitHub OAuth
- `google`: Google OAuth
- `wechat`: 微信登录
- `qq`: QQ 登录
- 等等...

**字段说明**:

- `account_id`: 在该 provider 下的唯一标识。credentials 时为邮箱/用户名；OAuth 时为第三方 user id
- `provider_id`: 登录方式（credentials / github / google 等）
- `access_token` / `refresh_token` / `id_token`: OAuth 令牌，仅第三方登录时使用
- `access_token_expires_at` / `refresh_token_expires_at`: 令牌过期时间，用于刷新
- `scope`: OAuth 申请的 scope
- `password`: 仅 `credentials` 时使用，bcrypt 加密

**关系说明**:

- `Account.user_id`：**实际存储在 accounts 表中的外键字段**，关联到 `users.id`
- 一个用户可有多个账户（多种登录方式）
- 同一 `(provider_id, account_id)` 唯一，如邮箱不能重复注册

### 3. Role（角色表）

存储系统角色定义。

```python
class Role(Base):
    __tablename__ = "roles"

    # ========== 数据库实际存储的字段（Column）==========
    id: UUID (PK)               # 角色 ID
    name: str (unique)           # 角色名称（唯一）
    code: str (unique)           # 角色代码（唯一，用于程序识别）
    description: str (nullable)  # 角色描述
    is_system: bool             # 是否为系统角色（默认 False，系统角色不可删除）

    # 时间戳
    created_at: datetime
    updated_at: datetime

    # ========== Python 层面的关系定义（relationship，不存储在数据库）==========
    # - users: 通过 UserRole 关联表关联到 User（多对多）
    # - permissions: 通过 RolePermission 关联表关联到 Permission（多对多）
    users: List[User]           # 拥有该角色的用户（关系定义，不存储）
    permissions: List[Permission]  # 该角色的权限（关系定义，不存储）
```

**数据库表结构**（实际存储）:

```sql
CREATE TABLE roles (
    id UUID PRIMARY KEY,
    name VARCHAR UNIQUE NOT NULL,
    code VARCHAR UNIQUE NOT NULL,
    description TEXT,
    is_system BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

**索引**:

- `idx_roles_name`: `name` (唯一索引)
- `idx_roles_code`: `code` (唯一索引)
- `idx_roles_is_system`: `is_system`

**预定义角色**:

- `admin`: 管理员（系统角色）
- `user`: 普通用户（系统角色）
- `premium`: 高级用户（可选）
- 等等...

**字段说明**:

- `name`: 角色名称，用于显示
- `code`: 角色代码，用于程序识别（如 "admin", "user"）
- `description`: 角色描述
- `is_system`: 系统角色不可删除，用于保护核心角色

**关系说明**:

- `Role.users` 关系：通过 `UserRole` 关联表关联到 `User`（多对多关系）
- `Role.permissions` 关系：通过 `RolePermission` 关联表关联到 `Permission`（多对多关系）

### 4. Permission（权限表）

存储系统权限定义。

```python
class Permission(Base):
    __tablename__ = "permissions"

    # ========== 数据库实际存储的字段（Column）==========
    id: UUID (PK)               # 权限 ID
    name: str                   # 权限名称
    code: str (unique)           # 权限代码（唯一，用于程序识别）
    description: str (nullable)  # 权限描述

    # 时间戳
    created_at: datetime
    updated_at: datetime

    # ========== Python 层面的关系定义（relationship，不存储在数据库）==========
    # - roles: 通过 RolePermission 关联表关联到 Role（多对多）
    roles: List[Role]           # 拥有该权限的角色（关系定义，不存储）
```

**数据库表结构**（实际存储）:

```sql
CREATE TABLE permissions (
    id UUID PRIMARY KEY,
    name VARCHAR NOT NULL,
    code VARCHAR UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

**索引**:

- `idx_permissions_code`: `code` (唯一索引)

**权限代码示例**:

- `file:create`: 创建文件
- `file:read`: 读取文件
- `file:update`: 更新文件
- `file:delete`: 删除文件
- `thread:create`: 创建线程
- `thread:read`: 读取线程
- `thread:update`: 更新线程
- `thread:delete`: 删除线程
- `user:manage`: 管理用户
- `system:admin`: 系统管理
- 等等...

**字段说明**:

- `name`: 权限名称，用于显示
- `code`: 权限代码，格式通常为 `resource:action`（如 `file:read`），用于程序识别
- `description`: 权限描述

**关系说明**:

- `Permission.roles` 关系：通过 `RolePermission` 关联表关联到 `Role`（多对多关系）

### 5. UserRole（用户-角色关联表）

多对多关系表，关联用户和角色。

```python
class UserRole(Base):
    __tablename__ = "user_roles"

    id: UUID (PK)
    user_id: UUID (FK -> User.id)
    role_id: UUID (FK -> Role.id)

    created_at: datetime

    # 唯一约束：一个用户不能重复关联同一个角色
    __table_args__ = (
        UniqueConstraint('user_id', 'role_id', name='uq_user_role'),
    )
```

**数据库表结构**（实际存储）:

```sql
CREATE TABLE user_roles (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL,
    UNIQUE(user_id, role_id)  -- 确保一个用户不会重复关联同一个角色
);
```

**索引**:

- `idx_user_roles_user_id`: `user_id`
- `idx_user_roles_role_id`: `role_id`

### 6. RolePermission（角色-权限关联表）

多对多关系表，关联角色和权限。

```python
class RolePermission(Base):
    __tablename__ = "role_permissions"

    id: UUID (PK)
    role_id: UUID (FK -> Role.id)
    permission_id: UUID (FK -> Permission.id)

    created_at: datetime

    # 唯一约束：一个角色不能重复关联同一个权限
    __table_args__ = (
        UniqueConstraint('role_id', 'permission_id', name='uq_role_permission'),
    )
```

**数据库表结构**（实际存储）:

```sql
CREATE TABLE role_permissions (
    id UUID PRIMARY KEY,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL,
    UNIQUE(role_id, permission_id)  -- 确保一个角色不会重复关联同一个权限
);
```

**索引**:

- `idx_role_permissions_role_id`: `role_id`
- `idx_role_permissions_permission_id`: `permission_id`

### 7. RefreshToken（刷新令牌表）

存储 JWT 刷新令牌，用于实现 token 刷新机制。

```python
class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: UUID (PK)
    user_id: UUID (FK -> User.id)  # 关联用户
    token: str (unique)             # 刷新令牌（JWT）
    expires_at: datetime           # 过期时间
    is_revoked: bool               # 是否已撤销（默认 False）

    # 设备/客户端信息（可选）
    device_info: str (nullable)     # 设备信息（浏览器、IP等）
    user_agent: str (nullable)      # User-Agent

    created_at: datetime
    updated_at: datetime
```

**索引**:

- `idx_refresh_tokens_user_id`: `user_id`
- `idx_refresh_tokens_token`: `token` (唯一索引)
- `idx_refresh_tokens_expires_at`: `expires_at` (用于清理过期令牌)

**说明**:

- 刷新令牌有效期通常较长（如 7-30 天）
- 用户登出时可以撤销令牌（设置 `is_revoked = True`）
- 定期清理过期的令牌

### 8. File（文件表）

存储用户上传的 Excel 文件信息。

```python
class File(Base):
    __tablename__ = "files"

    # ========== 数据库实际存储的字段（Column）==========
    id: UUID (PK)              # file_id，对应现有的 UUID
    user_id: UUID (FK -> User.id)  # 文件所有者（外键，存储在 files 表中）
    filename: str               # 原始文件名
    file_path: str           # 文件存储路径（相对路径）
    file_size: int              # 文件大小（字节）
    md5: str (unique)            # 文件 MD5 哈希值（用于去重和校验）
    mime_type: str              # MIME 类型
    uploaded_at: datetime       # 上传时间
    created_at: datetime         # 创建时间
    updated_at: datetime         # 更新时间

    # ========== Python 层面的关系定义（relationship，不存储在数据库）==========
    # - user: 通过 user_id 外键反向关联到 User（多对一）
    # - turns: 通过 TurnFile 关联表关联到 ThreadTurn（多对多）
    user: User                  # 文件所有者（关系定义，不存储）
    turns: List[ThreadTurn]    # 使用该文件的消息列表（关系定义，不存储）
```

**数据库表结构**（实际存储）:

```sql
CREATE TABLE files (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR NOT NULL,
    file_path VARCHAR NOT NULL,
    file_size INTEGER NOT NULL,
    md5 VARCHAR(32) UNIQUE NOT NULL,
    mime_type VARCHAR,
    uploaded_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

**索引**:

- `idx_files_user_id`: `user_id` (外键索引，用于关联查询)
- `idx_files_md5`: `md5` (唯一索引，用于文件去重和校验)
- `idx_files_uploaded_at`: `uploaded_at DESC` (查询最近上传的文件)

**字段说明**:

- `md5`: 文件的 MD5 哈希值（32 位十六进制字符串），用于：
- 文件去重：相同内容的文件可以共享存储
- 文件校验：验证文件完整性
- 快速查找：通过 MD5 快速定位文件

**关系说明**:

- `File.user_id`：**实际存储在 files 表中的外键字段**，关联到 `users.id`
- `File.user`：Python 关系定义，通过 `user_id` 反向查询 User 对象
- `File.turns`：Python 关系定义，通过 `TurnFile` 关联表查询关联的消息（多对多关系）

**权限控制**:

- 用户只能访问自己上传的文件（通过 `user_id` 过滤）
- 管理员可以访问所有文件

### 9. Thread（线程表）

存储多轮对话的线程信息。一个线程可以包含多轮对话，每轮对话可以使用不同的文件组合。

```python
class Thread(Base):
    __tablename__ = "threads"

    # ========== 数据库实际存储的字段（Column）==========
    id: UUID (PK)               # 线程 ID
    user_id: UUID (FK -> User.id)  # 线程创建者（外键）
    title: str (nullable)         # 线程标题（可选，可以自动生成或用户自定义）
    status: str                   # 线程状态: active, archived, deleted
    created_at: datetime          # 创建时间
    updated_at: datetime          # 最后更新时间（最后一条消息的时间）

    # ========== Python 层面的关系定义（relationship，不存储在数据库）==========
    # - user: 通过 user_id 外键反向关联到 User（多对一）
    # - turns: 通过 ThreadTurn.thread_id 外键关联（一对多）
    # 注意：文件不是直接关联到线程，而是关联到每条消息（ThreadTurn）
    user: User                    # 线程创建者（关系定义，不存储）
    turns: List[ThreadTurn] # 线程的所有对话轮次（关系定义，不存储）
```

**数据库表结构**（实际存储）:

```sql
CREATE TABLE threads (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR,
    status VARCHAR NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

**索引**:

- `idx_threads_user_id`: `user_id`
- `idx_threads_status`: `status`
- `idx_threads_updated_at`: `updated_at DESC` (查询最近线程)

**状态枚举**:

- `active`: 活跃线程（默认）
- `archived`: 已归档
- `deleted`: 已删除（软删除）

**关系说明**:

- `Thread.user_id`：**实际存储在 threads 表中的外键字段**，关联到 `users.id`
- `Thread.turns`：通过 `ThreadTurn.thread_id` 外键关联对话轮次（一对多关系）
- **注意**：文件不是直接关联到线程，而是关联到每条消息（ThreadTurn），这样每轮对话可以使用不同的文件组合

### 10. ThreadTurn（线程消息表）

存储线程中的每条用户消息及其处理信息。每条消息包含一次完整的处理流程（用户输入 → LLM 分析 → 生成操作 → 执行结果）。

**说明**：虽然表名是 `thread_turns`，但在业务逻辑上更接近"消息"（message）的概念。每条记录代表用户发送的一条消息及其完整的处理结果。

```python
class ThreadTurn(Base):
    __tablename__ = "thread_turns"

    # ========== 数据库实际存储的字段（Column）==========
    id: UUID (PK)               # 消息 ID
    thread_id: UUID (FK -> Thread.id)  # 所属线程（外键）
    turn_number: int             # 消息序号（1, 2, 3...，在同一线程内递增，类似消息顺序）
    user_query: str              # 用户消息内容（自然语言需求）
    status: str                 # 处理状态: pending, processing, completed, failed
    analysis: str (nullable)     # LLM 第一步分析结果（文本）
    operations_json: JSONB (nullable)  # LLM 第二步生成的 operations JSON
    error_message: str (nullable) # 错误信息

    # 时间戳
    created_at: datetime         # 创建时间（用户发送消息的时间）
    started_at: datetime (nullable)  # 开始处理时间
    completed_at: datetime (nullable)  # 完成时间
    updated_at: datetime         # 更新时间

    # ========== Python 层面的关系定义（relationship，不存储在数据库）==========
    # - thread: 通过 thread_id 外键反向关联到 Thread（多对一）
    # - files: 通过 TurnFile 关联表关联到 File（多对多）
    # - result: 通过 TurnResult.turn_id 外键关联（一对一）
    thread: Thread   # 所属线程（关系定义，不存储）
    files: List[File]  # 该消息使用的文件（关系定义，不存储）
    result: TurnResult (1:1)     # 处理结果（关系定义，不存储）
```

**数据库表结构**（实际存储）:

```sql
CREATE TABLE thread_turns (
    id UUID PRIMARY KEY,
    thread_id UUID NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    turn_number INTEGER NOT NULL,
    user_query TEXT NOT NULL,
    status VARCHAR NOT NULL,
    analysis TEXT,
    operations_json JSONB,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL,
    UNIQUE(thread_id, turn_number)  -- 确保同一线程内轮次序号唯一
);
```

**索引**:

- `idx_turns_thread_id`: `thread_id`
- `idx_turns_thread_turn`: `(thread_id, turn_number)` (唯一索引，用于排序)
- `idx_turns_status`: `status`
- `idx_turns_created_at`: `created_at DESC`

**状态枚举**:

- `pending`: 已创建，等待处理
- `processing`: 正在处理中
- `completed`: 处理完成
- `failed`: 处理失败

**关系说明**:

- `ThreadTurn.thread_id`：**实际存储在 thread_turns 表中的外键字段**，关联到 `threads.id`
- `ThreadTurn.turn_number`：在同一线程内从 1 开始递增，用于排序和标识消息顺序（类似聊天消息的顺序）
- `ThreadTurn.files`：通过 `TurnFile` 关联表关联文件（多对多关系），每条消息可以使用不同的文件组合
- `ThreadTurn.result`：通过 `TurnResult.turn_id` 外键关联（一对一关系）

**业务概念**:

- 每条 `ThreadTurn` 记录代表用户发送的一条消息
- `turn_number` 表示消息在线程中的顺序（第1条、第2条...）
- 每条消息都会经过完整的处理流程：分析 → 生成 → 执行
- **重要**：文件关联到每条消息，而不是线程，这样每轮对话可以使用不同的文件组合，更灵活

### 11. TurnResult（轮次结果表）

存储每轮对话的执行结果。

```python
class TurnResult(Base):
    __tablename__ = "turn_results"

    # ========== 数据库实际存储的字段（Column）==========
    id: UUID (PK)
    turn_id: UUID (FK -> ConversationTurn.id, unique)  # 一对一关系

    # 执行结果
    variables: JSONB            # aggregate/compute 产生的变量值
    new_columns: JSONB          # add_column 产生的新列数据（前10行预览）
    formulas: JSONB             # Excel 公式列表
    output_file: str (nullable) # 输出文件名（如果有）
    output_file_path: str (nullable) # 输出文件路径

    # 错误信息
    errors: List[str] (JSONB)   # 执行过程中的错误列表

    created_at: datetime
    updated_at: datetime
```

**数据库表结构**（实际存储）:

```sql
CREATE TABLE turn_results (
    id UUID PRIMARY KEY,
    turn_id UUID UNIQUE NOT NULL REFERENCES thread_turns(id) ON DELETE CASCADE,
    variables JSONB,
    new_columns JSONB,
    formulas JSONB,
    output_file VARCHAR,
    output_file_path VARCHAR,
    errors JSONB,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

**索引**:

- `idx_results_turn_id`: `turn_id` (唯一索引，确保一对一)

**关系说明**:

- `TurnResult.turn_id`：**实际存储在 turn_results 表中的外键字段**，关联到 `thread_turns.id`（唯一约束确保一对一）

### 12. TurnFile（消息-文件关联表）

多对多关系表，关联消息（ThreadTurn）和文件。每条消息可以使用不同的文件组合。

```python
class TurnFile(Base):
    __tablename__ = "turn_files"

    id: UUID (PK)
    turn_id: UUID (FK -> ThreadTurn.id)
    file_id: UUID (FK -> File.id)

    created_at: datetime

    # 唯一约束：一条消息不能重复关联同一个文件
    __table_args__ = (
        UniqueConstraint('turn_id', 'file_id', name='uq_turn_file'),
    )
```

**数据库表结构**（实际存储）:

```sql
CREATE TABLE turn_files (
    id UUID PRIMARY KEY,
    turn_id UUID NOT NULL REFERENCES thread_turns(id) ON DELETE CASCADE,
    file_id UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL,
    UNIQUE(turn_id, file_id)  -- 确保一条消息不会重复关联同一个文件
);
```

**索引**:

- `idx_turn_files_turn_id`: `turn_id`
- `idx_turn_files_file_id`: `file_id`

**说明**:

- 一条消息可以使用多个文件
- 一个文件可以被多条消息使用
- **重要**：文件关联到每条消息，而不是线程，这样：
  - 每轮对话可以使用不同的文件组合
  - 用户可以在对话过程中添加新文件
  - 更灵活，符合实际使用场景

## 数据库关系图

```
User (1) ──< (N) Account                 [通过 Account.user_id 外键]
User (N) ──< UserRole >── (N) Role (N) ──< RolePermission >── (N) Permission
         [关联表]              [关联表]

User (1) ──< (N) File                    [通过 File.user_id 外键]
User (1) ──< (N) Thread                [通过 Thread.user_id 外键]
User (1) ──< (N) RefreshToken          [通过 RefreshToken.user_id 外键]

File (1) ──< TurnFile >── (N) ThreadTurn (N) ──< (1) Thread (1) ── (1) TurnResult
         [关联表]              [通过 ThreadTurn.thread_id 外键]  [通过 TurnResult.turn_id 外键]
```

````

**关系说明**:

### 一对多关系（通过外键实现）

1. **User → Account**（一对多）
   - 存储方式：`Account` 表中有 `user_id` 外键字段
   - 一个用户可以有多个登录账户（邮箱、手机、第三方等）
   - 查询：`SELECT * FROM accounts WHERE user_id = :user_id`

2. **User → File**（一对多）
   - 存储方式：`File` 表中有 `user_id` 外键字段
   - 一个用户可以有多个文件
   - 查询：`SELECT * FROM files WHERE user_id = :user_id`

3. **User → Thread**（一对多）
   - 存储方式：`Thread` 表中有 `user_id` 外键字段
   - 一个用户可以有多个线程
   - 查询：`SELECT * FROM threads WHERE user_id = :user_id`

4. **User → RefreshToken**（一对多）
   - 存储方式：`RefreshToken` 表中有 `user_id` 外键字段
   - 一个用户可以有多个刷新令牌（多设备登录）
   - 查询：`SELECT * FROM refresh_tokens WHERE user_id = :user_id`

5. **Thread → ThreadTurn**（一对多）
   - 存储方式：`ThreadTurn` 表中有 `thread_id` 外键字段
   - 一个线程可以有多条消息（类似聊天线程中的多条消息）
   - 查询：`SELECT * FROM thread_turns WHERE thread_id = :thread_id ORDER BY turn_number`

### 多对多关系（通过关联表实现）

6. **User ↔ Role**（多对多）
   - 存储方式：通过 `UserRole` 关联表存储
   - `UserRole` 表中有 `user_id` 和 `role_id` 两个外键
   - 一个用户可以有多个角色
   - 一个角色可以分配给多个用户
   - 查询：通过 JOIN `user_roles` 表

7. **Role ↔ Permission**（多对多）
   - 存储方式：通过 `RolePermission` 关联表存储
   - `RolePermission` 表中有 `role_id` 和 `permission_id` 两个外键
   - 一个角色可以有多个权限
   - 一个权限可以分配给多个角色
   - 查询：通过 JOIN `role_permissions` 表

8. **File ↔ ThreadTurn**（多对多）
   - 存储方式：通过 `TurnFile` 关联表存储
   - `TurnFile` 表中有 `file_id` 和 `turn_id` 两个外键
   - 一个文件可以被多条消息使用
   - 一条消息可以使用多个文件
   - 查询：通过 JOIN `turn_files` 表
   - **优势**：每条消息可以使用不同的文件组合，更灵活

### 一对一关系（通过外键实现）

9. **ThreadTurn → TurnResult**（一对一）
   - 存储方式：`TurnResult` 表中有 `turn_id` 外键字段（唯一约束）
   - 一条消息对应一个处理结果
   - 查询：`SELECT * FROM turn_results WHERE turn_id = :turn_id`

**重要说明**:

- **外键字段**（如 `user_id`）是实际存储在数据库表中的列
- **关系定义**（如 `User.files`）只是 SQLAlchemy 的 Python 代码，用于方便查询，**不存储在数据库中**
- 多对多关系需要**关联表**（如 `TaskFile`）来存储关联信息

## SQLAlchemy 关系 vs 数据库存储

### 重要概念区分

在 SQLAlchemy 中，有两种不同的定义：

1. **Column（列）** - 实际存储在数据库中的字段
   - 例如：`user_id: UUID` 会创建一个实际的数据库列
   - 这些字段会出现在 `CREATE TABLE` 语句中

2. **Relationship（关系）** - Python 层面的关系定义，**不存储在数据库中**
   - 例如：`files: List[File]` 只是定义了一个 Python 属性
   - 用于方便地通过 `user.files` 访问关联数据
   - 实际查询时，SQLAlchemy 会通过外键字段自动 JOIN 查询

### 示例说明

```python
class User(Base):
    # ✅ 这些是数据库实际存储的字段
    id: UUID = Column(UUID, primary_key=True)
    email: str = Column(String, unique=True)
    user_id: UUID = Column(UUID, ForeignKey('users.id'))  # ❌ 这个不在 User 表中！

    # ❌ 这些关系定义不会存储在数据库中
    files: List[File] = relationship("File", back_populates="user")
    # 实际存储的是 File 表中的 user_id 字段
````

**实际数据库表结构**:

```sql
-- users 表（实际存储）
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    -- 注意：没有 files 字段！
);

-- files 表（实际存储）
CREATE TABLE files (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),  -- ✅ 这里才是实际存储的外键
    filename VARCHAR NOT NULL
);
```

### 关系类型总结

| 关系类型   | 存储方式                                     | 示例                                                      |
| ---------- | -------------------------------------------- | --------------------------------------------------------- |
| **一对多** | 在"多"的一方存储外键                         | `File.user_id` → `User.id`                                |
| **多对一** | 在"多"的一方存储外键                         | `ThreadTurn.thread_id` → `Thread.id`                      |
| **一对一** | 在任意一方存储外键（通常在有扩展信息的一方） | `TurnResult.turn_id` → `ThreadTurn.id`                    |
| **多对多** | 需要关联表存储两个外键                       | `TurnFile.file_id` + `TurnFile.turn_id`                   |
| **多对多** | 需要关联表存储两个外键                       | `UserRole.user_id` + `UserRole.role_id`                   |
| **多对多** | 需要关联表存储两个外键                       | `RolePermission.role_id` + `RolePermission.permission_id` |

### 查询时的区别

```python
# 方式1：直接通过外键查询（SQL）
session.query(File).filter(File.user_id == user_id).all()

# 方式2：通过关系定义查询（SQLAlchemy 会自动 JOIN）
user = session.get(User, user_id)
files = user.files  # SQLAlchemy 自动执行: SELECT * FROM files WHERE user_id = ?

# 两种方式生成的 SQL 是一样的，但方式2更简洁
```

## 字段类型说明

### JSONB 字段

PostgreSQL 的 JSONB 类型用于存储：

- `operations_json`: LLM 生成的 operations 数组
- `variables`: 执行后的变量值字典
- `new_columns`: 新列数据（嵌套字典结构）
- `formulas`: Excel 公式列表
- `errors`: 错误信息列表

**优势**:

- 支持 JSON 查询和索引
- 数据验证和约束
- 高效的存储和查询

### UUID 主键

所有表使用 UUID v4 作为主键：

- 分布式友好
- 避免 ID 冲突
- 安全性更好（不暴露自增 ID）

## 认证机制

### JWT Token 设计

系统使用 **JWT (JSON Web Token)** 进行认证，包含两种令牌：

1. **Access Token（访问令牌）**
   - 有效期短（如 15 分钟 - 1 小时）
   - 存储在客户端（内存或 localStorage）
   - 用于 API 请求认证
   - 过期后使用 Refresh Token 刷新

2. **Refresh Token（刷新令牌）**
   - 有效期长（如 7-30 天）
   - 存储在数据库（RefreshToken 表）
   - 用于获取新的 Access Token
   - 可以撤销（登出时）

### Token Payload 结构

**Access Token**:

```json
{
  "sub": "user_id (UUID)",
  "username": "username",
  "roles": ["user", "premium"], // 用户的角色代码列表
  "exp": 1234567890,
  "iat": 1234567890,
  "type": "access"
}
```

**Refresh Token**:

```json
{
  "sub": "user_id (UUID)",
  "token_id": "refresh_token_id (UUID)",
  "exp": 1234567890,
  "iat": 1234567890,
  "type": "refresh"
}
```

### 密码加密

使用 **bcrypt** 算法加密密码：

- 自动生成 salt
- 成本因子（rounds）建议设置为 12
- 使用 `passlib` 库的 `CryptContext`

### API 端点设计

```
POST   /api/auth/register      # 用户注册（创建 User + Account）
POST   /api/auth/login          # 用户登录（返回 access + refresh token）
POST   /api/auth/refresh        # 刷新 access token
POST   /api/auth/logout         # 登出（撤销 refresh token）
GET    /api/auth/me             # 获取当前用户信息（包含角色和权限）
PUT    /api/auth/me             # 更新用户信息
PUT    /api/auth/password       # 修改密码（更新 Account.password）
POST   /api/auth/bind-account   # 绑定新的登录账户（邮箱/手机/第三方）
```

### RBAC 系统说明

**角色和权限的关系**:

- 用户通过角色获得权限
- 一个用户可以有多个角色
- 一个角色可以有多个权限
- 权限通过 `resource:action` 格式定义

**权限检查示例**:

```python
# 检查用户是否有 file:read 权限
def check_permission(user_id: UUID, permission_code: str) -> bool:
    # 查询用户的所有权限
    # 检查是否包含目标权限
    pass

# 使用示例
if check_permission(user_id, "file:read"):
    # 允许读取文件
    pass
else:
    # 拒绝访问
    raise PermissionDenied()
```

**预定义角色和权限**:

**角色**:

- `admin`: 管理员（拥有所有权限）
- `user`: 普通用户（基础权限）
- `premium`: 高级用户（额外权限）

**权限示例**:

- `file:create` - 创建文件
- `file:read` - 读取自己的文件
- `file:read:all` - 读取所有文件（管理员）
- `file:update` - 更新自己的文件
- `file:delete` - 删除自己的文件
- `thread:create` - 创建线程
- `thread:read` - 读取自己的线程
- `thread:delete` - 删除自己的线程
- `user:manage` - 管理用户（管理员）
- `system:admin` - 系统管理（管理员）

## 查询场景

### 认证相关

#### 1. 用户登录验证

```sql
-- 方式1：邮箱+密码（credentials）
SELECT
    u.id,
    u.username,
    u.status,
    a.password
FROM users u
JOIN accounts a ON u.id = a.user_id
WHERE a.provider_id = 'credentials'
  AND a.account_id = :email  -- 邮箱作为 account_id
  AND u.status = 0;  -- 0 正常

-- 方式2：手机号+密码（若支持 phone 作为 credentials 的 account_id）
SELECT
    u.id,
    u.username,
    u.status,
    a.password
FROM users u
JOIN accounts a ON u.id = a.user_id
WHERE a.provider_id = 'credentials'
  AND a.account_id = :phone
  AND u.status = 0;

-- 方式3：第三方 OAuth（如 GitHub）
SELECT
    u.id,
    u.username,
    u.status,
    a.access_token,
    a.refresh_token
FROM users u
JOIN accounts a ON u.id = a.user_id
WHERE a.provider_id = :provider_id   -- 如 'github', 'google'
  AND a.account_id = :provider_user_id  -- 第三方平台的用户 ID
  AND u.status = 0;
```

#### 2. 获取用户的所有角色和权限

```sql
-- 获取用户的角色
SELECT r.*
FROM roles r
JOIN user_roles ur ON r.id = ur.role_id
WHERE ur.user_id = :user_id;

-- 获取用户的所有权限（通过角色）
SELECT DISTINCT p.*
FROM permissions p
JOIN role_permissions rp ON p.id = rp.permission_id
JOIN user_roles ur ON rp.role_id = ur.role_id
WHERE ur.user_id = :user_id;
```

#### 3. 检查用户是否有特定权限

```sql
SELECT COUNT(*) > 0 as has_permission
FROM permissions p
JOIN role_permissions rp ON p.id = rp.permission_id
JOIN user_roles ur ON rp.role_id = ur.role_id
WHERE ur.user_id = :user_id
  AND p.code = :permission_code;
```

#### 4. 创建刷新令牌

```sql
INSERT INTO refresh_tokens (id, user_id, token, expires_at, created_at)
VALUES (:id, :user_id, :token, :expires_at, NOW());
```

#### 5. 验证刷新令牌

```sql
SELECT
    rt.*,
    u.id as user_id,
    u.username,
    u.status
FROM refresh_tokens rt
JOIN users u ON rt.user_id = u.id
WHERE rt.token = :token
  AND rt.is_revoked = false
  AND rt.expires_at > NOW()
  AND u.status = 0;  -- 仅正常用户可刷新
```

#### 6. 撤销刷新令牌（登出）

```sql
UPDATE refresh_tokens
SET is_revoked = true, updated_at = NOW()
WHERE token = :token;
```

#### 7. 清理过期令牌

```sql
DELETE FROM refresh_tokens
WHERE expires_at < NOW() - INTERVAL '7 days';
```

### 业务相关

#### 1. 获取用户文件列表

```sql
SELECT * FROM files
WHERE user_id = :user_id
ORDER BY uploaded_at DESC
LIMIT 20;
```

#### 2. 获取用户线程列表（按时间倒序）

```sql
SELECT t.*, COUNT(tt.id) as turn_count
FROM threads t
LEFT JOIN thread_turns tt ON t.id = tt.thread_id
WHERE t.user_id = :user_id
  AND t.status = 'active'
GROUP BY t.id
ORDER BY t.updated_at DESC
LIMIT 20;
```

#### 3. 获取线程详情（包含所有消息）

```sql
SELECT
    t.*,
    tt.id as message_id,
    tt.turn_number,
    tt.user_query,
    tt.status as message_status,
    tt.analysis,
    tt.created_at as message_created_at
FROM threads t
LEFT JOIN thread_turns tt ON t.id = tt.thread_id
WHERE t.id = :thread_id
  AND t.user_id = :user_id  -- 权限验证
ORDER BY tt.turn_number ASC;
```

#### 4. 获取消息详情（包含结果，验证权限）

```sql
SELECT
    tt.*,
    tr.variables,
    tr.new_columns,
    tr.formulas,
    tr.output_file
FROM thread_turns tt
LEFT JOIN turn_results tr ON tt.id = tr.turn_id
JOIN threads t ON tt.thread_id = t.id
WHERE tt.id = :turn_id
  AND t.user_id = :user_id;  -- 权限验证
```

#### 5. 查询文件的所有消息（验证权限）

```sql
SELECT tt.*, t.title as thread_title
FROM thread_turns tt
JOIN turn_files tf ON tt.id = tf.turn_id
JOIN threads t ON tt.thread_id = t.id
WHERE tf.file_id = :file_id
  AND t.user_id = :user_id  -- 确保文件属于该用户
ORDER BY tt.created_at DESC;
```

#### 6. 创建新线程

```sql
-- 创建线程（不关联文件，文件在创建消息时关联）
INSERT INTO threads (id, user_id, title, status, created_at, updated_at)
VALUES (:thread_id, :user_id, :title, 'active', NOW(), NOW());
```

#### 7. 创建新消息（关联文件）

```sql
-- 1. 获取下一个消息序号
SELECT COALESCE(MAX(turn_number), 0) + 1 as next_turn_number
FROM thread_turns
WHERE thread_id = :thread_id;

-- 2. 创建消息记录
INSERT INTO thread_turns (
    id, thread_id, turn_number, user_query, status, created_at, updated_at
)
VALUES (
    :turn_id, :thread_id, :turn_number, :user_query, 'pending', NOW(), NOW()
);

-- 3. 关联文件（每条消息可以关联不同的文件）
INSERT INTO turn_files (id, turn_id, file_id, created_at)
VALUES
    (:id1, :turn_id, :file_id1, NOW()),
    (:id2, :turn_id, :file_id2, NOW());

-- 4. 更新线程更新时间
UPDATE threads
SET updated_at = NOW()
WHERE id = :thread_id;
```

#### 8. 创建线程并处理第一条消息（一体化）

```sql
-- 1. 创建线程
INSERT INTO threads (id, user_id, title, status, created_at, updated_at)
VALUES (:thread_id, :user_id, :title, 'active', NOW(), NOW());

-- 2. 创建第一条消息（turn_number = 1）
INSERT INTO thread_turns (
    id, thread_id, turn_number, user_query, status, created_at, updated_at
)
VALUES (
    :turn_id, :thread_id, 1, :user_query, 'pending', NOW(), NOW()
);

-- 3. 关联文件到消息（不是线程）
INSERT INTO turn_files (id, turn_id, file_id, created_at)
VALUES
    (:id1, :turn_id, :file_id1, NOW()),
    (:id2, :turn_id, :file_id2, NOW());

-- 4. 开始处理（更新状态）
UPDATE thread_turns
SET status = 'processing', started_at = NOW()
WHERE id = :turn_id;

-- 5. 处理完成后更新
UPDATE thread_turns
SET status = 'completed', completed_at = NOW(), analysis = :analysis, operations_json = :operations_json
WHERE id = :turn_id;

-- 6. 保存结果
INSERT INTO turn_results (id, turn_id, variables, new_columns, formulas, ...)
VALUES (:result_id, :turn_id, :variables, :new_columns, :formulas, ...);

-- 7. 更新线程更新时间
UPDATE threads
SET updated_at = NOW()
WHERE id = :thread_id;
```

#### 9. 获取用户统计信息

```sql
SELECT
    COUNT(DISTINCT f.id) as file_count,
    COUNT(DISTINCT t.id) as thread_count,
    COUNT(DISTINCT tt.id) as message_count,
    COUNT(DISTINCT CASE WHEN tt.status = 'completed' THEN tt.id END) as completed_messages
FROM users u
LEFT JOIN files f ON u.id = f.user_id
LEFT JOIN threads t ON u.id = t.user_id
LEFT JOIN thread_turns tt ON t.id = tt.thread_id
WHERE u.id = :user_id;
```

## 多轮对话设计说明

### 设计理念

1. **线程（Thread）**：代表一次完整的对话线程，关联一组文件
   - 用户可以创建多个线程，每个线程处理不同的文件组合
   - 线程可以归档或删除（软删除）

2. **消息（ThreadTurn/ThreadMessage）**：代表线程中的一条用户消息及其处理结果
   - 每条消息包含：用户输入 → LLM 分析 → 生成操作 → 执行结果
   - 消息按 `turn_number` 排序（1, 2, 3...）
   - 后续消息可以基于前面消息的结果进行进一步处理
   - 概念上类似于聊天系统中的消息（message）

3. **文件关联**：文件关联到每条消息（ThreadTurn），而不是线程
   - 每条消息可以使用不同的文件组合
   - 用户可以在对话过程中添加新文件
   - 更灵活，符合实际使用场景

### 多轮对话流程

**一体化创建**

```
# 同时创建线程并处理第一条消息
1. POST /api/threads {
    query: "...",
    file_ids: [...]
   }
# 发送后续消息
2. POST /api/threads {
    thread_id: "",
    query: "...",
    file_ids: [...]
   }
```

**处理流程**（每条消息）:

```
用户发送消息 query
    ↓
加载文件 → LLM 分析 → 生成操作 → 执行 → 返回结果
    ↓
保存消息记录和结果
```

### API 设计建议

#### 线程管理

```
POST   /api/threads              # 开始会话 / 发送后续消息，SSE 流式返回
GET    /api/threads/:id          # 获取线程详情（包含所有消息）
PUT    /api/threads/:id          # 更新线程（标题等信息）
DELETE /api/threads/:id          # 删除线程
```

#### API 详细说明

**1. POST /api/threads - 创建线程（同时处理第一条消息）/ 继续会话 **

请求体（创建线程并处理第一条消息）:

```json
{
  "query": "用户的需求描述",
  "file_ids": ["file_id_1", "file_id_2"]  # 文件关联到消息，不是线程
}
```

响应（创建并处理，SSE 流式响应）:

```
event: message
data: {"action": "load", "status": "start"}

event: message
data: {"action": "load", "status": "done", "data": {...}}

event: message
data: {"action": "analysis", "status": "start"}

event: message
data: {"action": "analysis", "status": "done", "data": {...}}

event: message
data: {"action": "generate", "status": "start"}

event: message
data: {"action": "generate", "status": "done", "data": {...}}

event: message
data: {"action": "execute", "status": "start"}

event: message
data: {"action": "execute", "status": "done", "data": {...}}
```

**2. POST /api/threads 继续会话**

请求体:

```json
{
  "thread_id": "xx",
  "query": "用户的需求描述",
  "file_ids": ["file_id_1", "file_id_2"]  # 可选
}
```

响应（SSE 流式响应，格式同上）

## 安全考虑

### 1. 密码安全

- 使用 bcrypt 加密，不存储明文密码
- 密码强度要求（最小长度、复杂度）
- 支持密码重置功能（需要邮箱验证）

### 2. Token 安全

- Access Token 存储在客户端，建议使用 httpOnly cookie（可选）
- Refresh Token 存储在数据库，可以撤销
- Token 过期时间合理设置
- 支持多设备登录（多个 Refresh Token）

### 3. 权限控制（RBAC）

- **基于角色的访问控制（RBAC）**：用户通过角色获得权限
- **权限检查**：通过 `resource:action` 格式的权限代码进行验证
- **实现方式**：
  - 使用 FastAPI 的依赖注入实现权限验证
  - 通过中间件或装饰器检查用户权限
  - 支持细粒度的资源级权限控制

**权限验证流程**:

```
1. 获取用户的所有角色
2. 通过角色获取所有权限
3. 检查是否有目标权限（如 file:read）
4. 如果有权限则允许访问，否则拒绝
```

**示例权限**:

- `file:read` - 读取文件（自己的）
- `file:read:all` - 读取所有文件（管理员）
- `thread:create` - 创建线程
- `thread:delete` - 删除线程（自己的）
- `thread:delete:all` - 删除所有线程（管理员）
- `user:manage` - 管理用户（管理员）

### 4. 数据隔离

- 所有查询都添加 `user_id` 过滤条件
- 文件存储路径可以包含 `user_id` 目录
- 防止越权访问

### 5. 审计日志

- 记录用户登录/登出时间
- 记录敏感操作（密码修改、文件删除等）
- 可选：添加操作日志表

## 扩展性考虑

### 未来可能添加的表

1. **TaskLog（任务日志表）** - 如果需要详细的操作日志

   ```python
   class TaskLog(Base):
       id: UUID
       task_id: UUID
       action: str  # load, analysis, generate, execute
       status: str  # start, done, error
       message: str
       created_at: datetime
   ```

2. **FileMetadata（文件元数据表）** - 如果需要存储 Excel 表结构信息
   ```python
   class FileMetadata(Base):
       id: UUID
       file_id: UUID
       table_name: str
       schema: JSONB  # 表结构信息
       created_at: datetime
   ```

## 性能优化建议

1. **索引策略**
   - 所有外键字段建立索引
   - 常用查询字段建立索引（status, created_at）
   - JSONB 字段可以建立 GIN 索引（如果需要查询 JSON 内容）

2. **连接池配置**
   - asyncpg 连接池大小：建议 10-20
   - 根据并发量调整

3. **查询优化**
   - 使用 `selectinload` 或 `joinedload` 预加载关联数据
   - 避免 N+1 查询问题

4. **数据清理**
   - 定期清理过期的任务和文件（可配置保留时间）
   - 定期清理过期的刷新令牌
   - 使用数据库的 `ON DELETE CASCADE` 自动清理关联数据

5. **认证优化**
   - 实现 token 黑名单（Redis）用于立即撤销 token
   - 支持 OAuth2 登录（GitHub、Google 等）
   - 支持双因素认证（2FA）

## 依赖库清单

### 认证相关依赖

需要在 `pyproject.toml` 中添加：

```toml
dependencies = [
    # ... 现有依赖 ...

    # 数据库
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",

    # 认证
    "python-jose[cryptography]>=3.3.0",  # JWT 处理
    "passlib[bcrypt]>=1.7.4",            # 密码加密
    "python-multipart>=0.0.20",          # 表单数据（已有）
]
```

### 环境变量配置

在 `.env` 文件中添加：

```bash
# 数据库配置
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/llm_excel
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# JWT 配置
JWT_SECRET_KEY=your-secret-key-here  # 使用 openssl rand -hex 32 生成
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30   # Access Token 过期时间（分钟）
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7      # Refresh Token 过期时间（天）

# 密码加密
BCRYPT_ROUNDS=12
```
