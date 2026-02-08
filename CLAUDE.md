# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Selgetabel** is an LLM-assisted Excel data processing system. Users describe data processing requirements in natural language, and the system generates structured JSON operations that are executed to produce Excel files with formulas.

**Tech Stack:**
- Frontend: React Router v7 + Vite + TypeScript
- Backend: Python FastAPI + OpenAI API
- Monorepo: pnpm workspace + Turborepo
- Node.js: 22.22.0 | pnpm: 10.28.0 | Python: 3.11+

## Development Commands

```bash
# Install dependencies (run from root)
pnpm install

# Install backend dependencies
pnpm --filter @selgetabel/api install

# Start both web and API
pnpm dev

# Start only API
pnpm dev:api

# Build all packages
pnpm build

# Format code
pnpm format

# Type checking
pnpm check-types
```

## Architecture

### Monorepo Structure

```
llm-excel/
├── apps/
│   ├── api/          # Python FastAPI backend
│   └── web/          # React Router v7 frontend
├── docs/             # Technical specifications
├── package.json      # Root workspace config
├── pnpm-workspace.yaml
└── turbo.json        # Turborepo task orchestration
```

### Backend (apps/api)

**Entry Point:** `apps/api/app/api/main.py` (FastAPI app: `app.main:app`)

**Key Directories:**
- `app/api/routes/` - API route handlers
- `app/lib/` - Core logic: JSON parsing, execution engine, formula generation
- `app/services/` - Excel file I/O and file management

**Core Flow:**
1. User uploads Excel file(s) → returns `file_id` for each
2. User sends natural language query + `file_ids` via `/excel/chat`
3. Backend streams SSE events: `load` → `analysis` → `generate` → `execute` → `complete`
4. LLM generates structured JSON operations (not raw formulas)
5. Executor parses JSON, executes operations, generates Excel formulas
6. Returns preview data + downloadable Excel file with formulas

**Operation Types:**
- `aggregate` - Column aggregation (SUM, AVERAGE, SUMIF, etc.)
- `add_column` - Add calculated column with formula
- `update_column` - Update existing column (e.g., fill nulls)
- `compute` - Scalar computation on variables
- `filter`, `sort`, `group_by`, `take` - Excel 365+ dynamic array operations

**Formula Expression Format:**
All formulas use JSON objects (not strings) to avoid parsing ambiguity:
```json
{
  "op": "*",
  "left": {"col": "price"},
  "right": {"value": 0.9}
}
```

**Environment Variables:**
- `OPENAI_API_KEY` (required)
- `OPENAI_BASE_URL` (optional)
- `OPENAI_MODEL` (optional)

**File Storage:**
- Files stored in MinIO object storage
- MinIO accessible at `http://localhost:9000` (API), `http://localhost:9001` (Console)
- Default credentials in `.env` file

### Frontend (apps/web)

**Framework:** React Router v7 (file-based routing)

**Key Directories:**
- `app/routes/` - File-based routes
- `app/components/` - Reusable UI components
- `app/features/` - Feature-specific components
- `app/lib/` - Utilities and API client

**API Integration:**
- Frontend requests to `/api/*` are proxied to backend in dev mode
- Proxy configured in `vite.config.ts`
- Default backend: `http://localhost:8000`
- Override with `API_BASE_URL` env var

**Dev Ports:**
- Web: `http://localhost:5173`
- API: `http://localhost:8000`
- API Docs: `http://localhost:8000/docs`

## Key Technical Concepts

### Two-Phase LLM Processing

The system uses a single-step LLM flow:
1. LLM receives user requirement + table structure
2. LLM generates structured JSON operations
3. Parser validates format and function whitelist
4. Executor runs operations and generates Excel formulas

### JSON Expression Objects

Formulas are represented as JSON objects to ensure unambiguous parsing:

**Types:**
- Literal: `{"value": 100}`
- Column reference: `{"col": "price"}`
- Cross-table reference: `{"ref": "table.column"}`
- Variable reference: `{"var": "total"}`
- Function call: `{"func": "IF", "args": [...]}`
- Binary operation: `{"op": "+", "left": {...}, "right": {...}}`

### Excel Formula Generation

The executor generates Excel formulas from JSON operations:
- Row formulas use `{row}` placeholder (e.g., `=D{row}*0.9`)
- Column names mapped to Excel column letters (A, B, C, etc.)
- All operations produce 100% reproducible Excel formulas

### SSE Event Stream

The `/excel/chat` endpoint streams Server-Sent Events:
- `load` - File loading progress
- `analysis` - Requirement analysis (if two-step flow)
- `generate` - Operation generation
- `execute` - Execution progress
- `complete` - Final result with output file path

## Important Files

**Backend:**
- `apps/api/app/api/main.py` - FastAPI app entry
- `apps/api/app/lib/executor.py` - Execution engine + JSON expression evaluator
- `apps/api/app/lib/parser.py` - JSON parser + validation
- `apps/api/app/lib/functions.py` - Function implementations
- `apps/api/app/lib/excel_generator.py` - Excel formula generation
- `apps/api/app/services/excel_service.py` - Excel file I/O

**Frontend:**
- `apps/web/app/routes/_auth._app._index.tsx` - Main chat interface
- `apps/web/app/lib/api.ts` - API client
- `apps/web/vite.config.ts` - Vite config with API proxy

**Documentation:**
- `docs/OPERATION_SPEC.md` - Complete operation specification
- `README.md` - Project overview and setup
- `apps/api/README.md` - Backend API documentation

## Docker Deployment

```bash
# Build and start with docker-compose
cd docker
docker compose up --build -d

# Access points
# - Web: http://localhost:8080
# - API (via Nginx): http://localhost:8080/api/*
# - MinIO Console: http://localhost:9001
```

**Environment Variables for Docker:**
Set in `docker/.env` (copy from `docker/.env.example`):
- `OPENAI_MODEL`
- `OPENAI_BASE_URL`
- `OPENAI_API_KEY`
- `POSTGRES_PASSWORD`
- `MINIO_ROOT_PASSWORD`
- `JWT_SECRET_KEY`

**Production Deployment:**
See `docker/README.md` for detailed deployment guide.

## CI/CD - GitHub Actions

**Multi-Architecture Docker Build:**
- Workflow: `.github/workflows/docker-build-push.yml`
- Supported architectures: `linux/amd64`, `linux/arm64`
- Builds both API and Web images with multi-arch support

**Triggers:**
- **Auto:** Push tags matching `v*` (e.g., `v1.0.0`) - automatically pushes `latest` tag
- **Manual:** Workflow dispatch in GitHub Actions UI - option to push `latest` tag

**Required GitHub Secrets:**
- `DOCKERHUB_TOKEN` (required) - Docker Hub access token with Read & Write permission
- `DOCKERHUB_USERNAME` (optional) - Defaults to repository owner if not set

**Built Images:**
- `${DOCKERHUB_USERNAME}/selgetabel-api:${VERSION}`
- `${DOCKERHUB_USERNAME}/selgetabel-web:${VERSION}`

**How it works:** Uses Docker Buildx + QEMU on GitHub's x86 runners to build both amd64 (native) and arm64 (emulated) images, then creates a manifest list for automatic architecture selection.

## Code Conventions

**Backend:**
- Python 3.11+ with type hints
- FastAPI for REST API + SSE
- `uv` for dependency management
- Function whitelist validation for security

**Frontend:**
- TypeScript strict mode
- React Router v7 file-based routing
- Tailwind CSS for styling
- SSE for real-time updates

## Testing & Debugging

**Backend:**
- Swagger docs: `http://localhost:8000/docs`
- Test with sample files in `apps/api/data/`

**Frontend:**
- React Router dev tools available in browser
- API proxy logs in terminal

## Common Workflows

**Adding a new operation type:**
1. Define operation schema in `docs/OPERATION_SPEC.md`
2. Add validation in `apps/api/app/lib/parser.py`
3. Implement execution in `apps/api/app/lib/executor.py`
4. Add formula generation in `apps/api/app/lib/excel_generator.py`
5. Update LLM prompt in `apps/api/app/lib/prompt.py`

**Adding a new function:**
1. Add to function whitelist in `parser.py`
2. Implement in `functions.py`
3. Add formula template in `excel_generator.py`
4. Update `docs/OPERATION_SPEC.md`

**Modifying frontend routes:**
- Routes are file-based in `apps/web/app/routes/`
- Naming convention: `_auth._app.routename.tsx` for authenticated routes
- Use `_index.tsx` for index routes
