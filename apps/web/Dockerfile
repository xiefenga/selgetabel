FROM node:22-alpine AS base

WORKDIR /repo

# 使用 corepack 管理 pnpm（与仓库 Volta 版本一致）
RUN npm install -g pnpm@10.28.0

FROM base AS deps

# 先拷贝依赖清单以利用缓存（workspace 需要根配置）
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json /repo/
COPY apps/web/package.json /repo/apps/web/package.json

# 只安装 web 所需依赖（含其依赖链）
RUN pnpm install --frozen-lockfile --filter web...

FROM deps AS build

COPY apps/web/ /repo/apps/web/

RUN pnpm --filter web build

FROM base AS runner

ENV NODE_ENV=production \
    PORT=3000

# 生产依赖
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml /repo/
COPY apps/web/package.json /repo/apps/web/package.json
RUN pnpm install --frozen-lockfile --prod --filter web...

# 构建产物
COPY --from=build /repo/apps/web/build /repo/apps/web/build

EXPOSE 3000

CMD ["pnpm", "--filter", "web", "start"]