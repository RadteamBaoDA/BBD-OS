# Deployment

The production Compose stack contains PostgreSQL with pgvector installed, Redis, a one-shot Alembic migration service, the FastAPI API, one ARQ worker, and the Next.js frontend. Application containers run as non-root users. Persistent database and Redis data live in named volumes.

The web port binds to loopback by default. For remote access, terminate HTTPS at a trusted reverse proxy and set `PUBLIC_ORIGIN` to the exact browser origin and `SECURE_COOKIES=true` in `.env`. Keep the API, Redis, PostgreSQL, and Docker socket private. Do not deploy with the example placeholder values.

To apply migrations separately, run `./scripts/dev.ps1 migrate` or `make migrate`. Compose prevents API/worker startup if migrations fail. `docker compose ps` reports health and one-shot migration state; inspect `docker compose logs migrate api worker` for failures without publishing secret-bearing configuration.

The design target is a 2-core, 8 GB host with remote AI inference. Phase 0 has not yet been measured on a complete deployment, so this target is not a capacity guarantee. OmniRoute credentials only configure a future gateway and are not connectivity-tested in this phase. Graph, n8n, and browser services are not installed yet.
