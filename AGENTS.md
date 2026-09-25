# Repository Guidelines

## Project Structure & Module Organization

This repository implements Phase 0 of the single-user, self-hosted Personal Intelligence OS. The approved product and engineering specification remains `specs/personal-intelligence-os-spec-v2.md`; delivery and later-phase status are tracked in `docs/IMPLEMENTATION_STATUS.md`.

Follow the specification when adding code:
- `apps/web/`: Next.js, React, and TypeScript frontend.
- `apps/api/` and `apps/worker/`: Python FastAPI backend and background processing.
- `packages/`: shared UI, contracts, SDK, and configuration.
- `core/` and `modules/<capability>/`: shared infrastructure and domain modules, following the modular-monolith requirements in sections 139–143.
- `tests/integration/`, `tests/e2e/`, and `tests/fixtures/`: cross-module validation.
- `infrastructure/` and `docs/`: deployment configuration and operational documentation.

Keep module internals private; integrate through public contracts or events. Create directories only when used.

## Build, Test, and Development Commands

Use `make setup`, `make dev`, `make stop`, `make migrate`, `make lint`, `make typecheck`, `make test`, and `make build` on macOS/Linux. Windows PowerShell equivalents are `./scripts/dev.ps1 <task>`. `test` creates a uniquely named disposable Compose project and removes only its own volumes. `seed`, `reset`, `backup`, and `restore` are not implemented yet.

## Coding Style & Naming Conventions

Use four-space Python indentation and two-space TypeScript indentation. Use `snake_case` for Python functions/modules, `camelCase` for TypeScript functions, and `PascalCase` for React components and types.

The specification requires ESLint and TypeScript checks for frontend code, and Ruff and mypy for Python. Keep changes focused and avoid unused scaffolding.

## Testing Guidelines

Use pytest for backend tests and Playwright for end-to-end flows; the frontend unit-test framework is not selected. Name Python tests `test_*.py` and Playwright tests `*.spec.ts`. Cover module contracts, ingestion, permissions, search, and citation flows. No numeric coverage threshold is specified. Report checks run and any unavailable validation.

## Commit & Pull Request Guidelines

There is no commit history or established message convention. Use concise, imperative subjects, such as `docs: clarify ingestion contracts`. PRs should describe scope, reference relevant specification sections or issues, list validation results, and include screenshots for UI changes.

## Security & Configuration

Never commit secrets or personal data. Provide placeholder configuration in `.env.example` when configuration is introduced. Preserve source provenance and enforce agent access through supported APIs and permission checks.
