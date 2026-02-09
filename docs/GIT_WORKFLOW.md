# Selgetabel Git 工作流规范

本项目采用 **GitHub Flow** 分支管理策略，配合语义化版本和手动触发的发布流程。

## 核心原则

- **main 分支**始终处于可部署状态
- 所有开发在**功能分支**进行，通过 PR 合并
- 只有**手动打 tag**才会触发 Docker 镜像构建和发布
- 所有代码变更必须经过代码审查

## 分支策略

### 分支类型

```
main                    # 生产分支，始终可部署
├── feature/*           # 功能分支
├── fix/*               # 修复分支
├── docs/*              # 文档分支
├── refactor/*          # 重构分支
├── perf/*              # 性能优化分支
└── chore/*             # 构建/工具变更
```

### 命名规范

| 类型 | 前缀        | 示例                      |
| ---- | ----------- | ------------------------- |
| 功能 | `feature/`  | `feature/excel-export`    |
| 修复 | `fix/`      | `fix/auth-timeout`        |
| 文档 | `docs/`     | `docs/api-examples`       |
| 重构 | `refactor/` | `refactor/db-models`      |
| 性能 | `perf/`     | `perf/query-optimization` |
| 工具 | `chore/`    | `chore/update-deps`       |

## 提交规范

### 提交信息格式

```
<类型>(<可选作用域>): <描述>

[可选的正文]

[可选的脚注]
```

### 类型说明

| 类型       | 说明                   | 示例                            |
| ---------- | ---------------------- | ------------------------------- |
| `feat`     | 新功能                 | `feat: 添加 Excel 批量导入功能` |
| `fix`      | 修复问题               | `fix: 修复数据导出时的内存泄漏` |
| `docs`     | 文档变更               | `docs: 更新 API 接口文档`       |
| `style`    | 代码格式（不影响功能） | `style: 统一缩进格式`           |
| `refactor` | 重构                   | `refactor: 优化数据库查询逻辑`  |
| `perf`     | 性能优化               | `perf: 缓存频繁访问的数据`      |
| `test`     | 测试相关               | `test: 添加用户认证单元测试`    |
| `build`    | 构建相关               | `build: 更新 Docker 基础镜像`   |
| `ci`       | CI/CD 配置             | `ci: 添加自动化测试工作流`      |
| `chore`    | 其他变更               | `chore: 升级依赖包版本`         |
| `revert`   | 回滚                   | `revert: 撤销某次提交`          |

### 作用域（可选）

- `api` - 后端 API 相关
- `web` - 前端相关
- `db` - 数据库相关
- `docker` - Docker 配置
- `deps` - 依赖更新

### 示例

```bash
# 功能提交
feat(api): 添加 Excel 文件解析接口

支持 xlsx 和 xls 格式的文件解析，
返回标准化的 JSON 数据结构。

Closes #123

# 修复提交
fix(web): 修复表格渲染时的闪烁问题

在数据量大于 1000 行时出现页面卡顿，
通过虚拟滚动优化性能。

Fixes #456

# 文档提交
docs: 添加本地开发环境配置指南

- 环境变量配置说明
- Docker 开发模式启动步骤
- 常见问题解决方案
```

## 开发流程

### 1. 开始新功能

```bash
# 确保 main 分支是最新的
git checkout main
git pull origin main

# 创建功能分支
git checkout -b feature/excel-parser

# 或者使用更具体的命名
git checkout -b feature/support-xlsx-format
```

### 2. 开发阶段

```bash
# 进行开发...
# 编辑代码

# 定期提交（保持提交粒度小且有意义）
git add .
git commit -m "feat(api): 实现 xlsx 文件读取"

# 继续开发...
git commit -m "feat(api): 添加单元格数据格式化"

# 同步 main 分支的最新变更（减少冲突）
git fetch origin
git rebase origin/main
```

### 3. 推送和创建 PR

```bash
# 推送到远程
git push -u origin feature/excel-parser

# 在 GitHub 上创建 Pull Request
# 标题格式：feat: 添加 Excel 解析功能
```

### 4. PR 审查和合并

**PR 标题规范：**

- 使用英文或中文开头
- 包含类型前缀
- 简明扼要描述变更内容

**示例：**

- ✅ `feat: 添加用户认证功能`
- ✅ `fix: 修复数据导出时的内存泄漏`
- ❌ `更新代码`（太模糊）
- ❌ `fix bug`（没有具体描述）

**PR 描述模板：**

```markdown
## 变更内容

简要描述本次 PR 的变更内容。

## 测试方式

- [ ] 本地测试通过
- [ ] 单元测试通过
- [ ] 集成测试通过

## 检查清单

- [ ] 代码遵循项目编码规范
- [ ] 添加了必要的测试
- [ ] 更新了相关文档
- [ ] 所有 CI 检查通过

## 关联 Issue

Closes #123
```

**合并要求：**

- 至少 1 个代码审查批准
- 所有 CI 检查通过
- 无合并冲突
- 使用 **"Squash and merge"** 保持主线历史整洁

### 5. 清理

```bash
# 合并后删除本地分支
git checkout main
git pull origin main
git branch -d feature/excel-parser

# 删除远程分支（GitHub 上合并时可选）
git push origin --delete feature/excel-parser
```

## 发布流程

### 版本号规则（语义化版本）

```
主版本号.次版本号.修订号
MAJOR.MINOR.PATCH

例如：v0.2.1
```

**版本号递增规则：**

- **MAJOR**：不兼容的 API 修改（破坏性变更）
- **MINOR**：向下兼容的功能添加
- **PATCH**：向下兼容的问题修复

### 发布步骤

**只有手动打 tag 才会触发 Docker 镜像构建和发布。**

```bash
# 1. 确保 main 分支是最新的
git checkout main
git pull origin main

# 2. 检查当前版本号（在 package.json 中）
cat package.json | grep version

# 3. 更新版本号（三选一）
npm version patch   # 修订号 +1 (0.1.3 → 0.1.4)
npm version minor   # 次版本号 +1 (0.1.3 → 0.2.0)
npm version major   # 主版本号 +1 (0.1.3 → 1.0.0)

# 或使用 pnpm
pnpm version patch
pnpm version minor
pnpm version major

# 4. 推送标签（触发 GitHub Actions）
git push origin main --tags

# 或者手动打标签
git tag -a v0.2.0 -m "Release version 0.2.0"
git push origin v0.2.0
```

### 自动触发的工作流

推送标签后，GitHub Actions 会自动：

1. **构建 Docker 镜像**
   - API 镜像：`selgetabel-api:v0.2.0`
   - Web 镜像：`selgetabel-web:v0.2.0`

2. **多架构支持**
   - linux/amd64
   - linux/arm64

3. **推送到 Docker Hub**

4. **创建 GitHub Release**（可选配置）

### 发布检查清单

- [ ] main 分支代码测试通过
- [ ] 版本号已更新
- [ ] CHANGELOG 已更新（如需要）
- [ ] 文档已更新（如需要）
- [ ] tag 已推送
- [ ] Docker 镜像构建成功
- [ ] 生产环境验证通过

## CI/CD 配置

### 自动触发的工作流

| 触发条件       | 工作流                  | 执行内容                        |
| -------------- | ----------------------- | ------------------------------- |
| PR 创建/更新   | `ci.yml`                | 代码检查、类型检查、测试、构建  |
| 合并到 main    | `ci.yml`                | 完整测试套件、构建验证          |
| 推送 tag (v\*) | `docker-build-push.yml` | 构建并推送 Docker 镜像          |
| 手动触发       | `docker-build-push.yml` | 可手动构建镜像（不推送 latest） |

### 本地开发检查

在提交前，请在本地运行以下检查：

```bash
# 后端（API）
cd apps/api
uv run ruff check .           # 代码检查
uv run ruff format --check .  # 格式检查
uv run pyright                # 类型检查
uv run pytest                 # 单元测试

# 前端（Web）
cd apps/web
pnpm lint                     # ESLint 检查
pnpm check-types              # TypeScript 类型检查
pnpm build                    # 构建测试

# 根目录（monorepo）
pnpm lint                     # 运行所有 lint
pnpm check-types              # 运行所有类型检查
pnpm build                    # 构建所有包
```

## 代码审查规范

### 审查者检查清单

- [ ] 代码逻辑正确
- [ ] 遵循项目编码规范
- [ ] 有必要的注释和文档
- [ ] 包含适当的测试
- [ ] 无安全问题
- [ ] 性能考虑（如适用）
- [ ] 无调试代码（console.log 等）

### 被审查者注意事项

- 保持 PR 大小适中（建议 < 500 行变更）
- 提供清晰的 PR 描述
- 关联相关的 Issue
- 及时响应审查意见
- 保持礼貌和耐心

## 紧急情况处理

### 生产环境紧急修复

```bash
# 1. 从 main 切出热修复分支
git checkout main
git pull origin main
git checkout -b fix/critical-bug

# 2. 修复问题并提交
git commit -m "fix: 修复生产环境崩溃问题"

# 3. 创建 PR 并加急审查

# 4. 合并后立即发布
git checkout main
git pull origin main
git tag -a v0.2.1 -m "Hotfix: 修复崩溃问题"
git push origin v0.2.1
```

### 回滚发布

```bash
# 如果新版本有问题，快速回滚到上一版本
git checkout main
git pull origin main

# 查看历史标签
git tag -l

# 回滚到上一版本（示例）
git reset --hard v0.1.9
git push origin main --force

# 或者创建回滚 PR（推荐）
git revert HEAD
git push origin fix/rollback-v0.2.0
# 然后创建 PR 合并
```

## 实用命令速查

```bash
# 分支操作
git checkout -b feature/xxx    # 创建并切换到新分支
git branch -a                  # 查看所有分支
git branch -d feature/xxx      # 删除本地分支
git push origin --delete feature/xxx  # 删除远程分支

# 同步操作
git fetch origin               # 获取远程变更
git pull origin main           # 拉取 main 分支
git rebase origin/main         # 变基到 main

# 提交操作
git status                     # 查看变更状态
git add .                      # 暂存所有变更
git commit -m "type: desc"     # 提交
git commit --amend             # 修改最后一次提交

# 标签操作
git tag -a v0.2.0 -m "desc"    # 创建带注释的标签
git push origin v0.2.0         # 推送指定标签
git push origin --tags         # 推送所有标签
git tag -d v0.2.0              # 删除本地标签

# 撤销操作
git reset HEAD~1               # 撤销最后一次提交（保留变更）
git reset --hard HEAD~1        # 撤销最后一次提交（丢弃变更）
git revert HEAD                # 创建撤销提交

# 查看历史
git log --oneline --graph      # 图形化历史
git log --oneline -20          # 最近 20 条提交
git show v0.2.0                # 查看标签详情
```

## 常见问题

**Q: 功能开发到一半，需要紧急修复生产环境怎么办？**

A: 提交当前变更，切换到 main 创建修复分支：

```bash
git add .
git commit -m "WIP: 暂存当前进度"
git stash  # 或者保持提交状态
git checkout main
git checkout -b fix/urgent
```

**Q: PR 合并后出现冲突怎么办？**

A: 在本地解决冲突后强制推送：

```bash
git checkout feature/xxx
git fetch origin
git rebase origin/main
# 解决冲突
git push origin feature/xxx --force-with-lease
```

**Q: 不小心提交了敏感信息怎么办？**

A: 使用 git filter-repo 或 BFG Repo-Cleaner 清理历史，并立即撤销相关密钥。

**Q: 可以推送到 main 分支吗？**

A: 不可以。所有变更必须通过 PR 合并，main 分支受到保护。

---

**文档维护：** 如有疑问或需要更新，请创建 Issue 或 PR。
