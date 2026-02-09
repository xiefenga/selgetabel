# Repository Guidelines

## Project Structure & Module Organization
- `apps/api/` — FastAPI backend (entry: `apps/api/app/main.py`, routes in `apps/api/app/api/`).
- `apps/web/` — React Router + Vite frontend (app code in `apps/web/app/`).
- `docs/` — design docs and specs (e.g., `docs/OPERATION_SPEC.md`).
- `docker/` — production and dev compose files plus scripts.
- `fixtures/` — sample data used in development.

## Build, Test, and Development Commands
Run from repo root unless noted.
- `pnpm dev` — start all apps via Turbo.
- `pnpm dev:api` — start API only (FastAPI).
- `pnpm build` — build all packages.
- `pnpm check-types` — run type checks across packages.
- `pnpm lint` — run lint tasks defined in packages.
- `pnpm format` — format `ts/tsx/md` with Prettier.
- `pnpm dev:docker` — start dev Docker stack.
- `pnpm docker:build` / `pnpm docker:up` / `pnpm docker:down` — build and manage prod stack.

API-only local workflow (from `apps/api/`):
- `uv sync` — install Python deps.
- `uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` — start API.

## Coding Style & Naming Conventions
- TypeScript/TSX: Prettier is the source of truth (`pnpm format`).
- React components live in `apps/web/app/components/` and use kebab-case filenames (e.g., `user-profile-dialog.tsx`).
- Python modules use snake_case; keep functions typed where practical.
- Match existing formatting and import ordering in nearby files.

## Testing Guidelines
- No dedicated test runner is configured in this repo.
- Use `pnpm check-types` and manual QA; add tests if you introduce critical logic.

## Commit & Pull Request Guidelines
- Commit messages follow Conventional Commits with short Chinese summaries (examples: `feat: 添加权限相关逻辑`, `fix: 修复postgresql数据卷挂载目录`, `chore: 优化compose`).
- PRs should include a concise summary, steps to test (commands run), and linked issues when relevant.
- UI changes should include screenshots or a short screen recording.

## Configuration Tips
- Environment variables live in `.env` files; see `ENV.md` and `apps/api/README.md` for required keys.
- Docker installs are managed via `install.sh` and the `docker/` scripts.
