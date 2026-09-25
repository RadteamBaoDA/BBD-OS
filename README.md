# BBD-OS

BBD-OS is a self-hosted Personal Intelligence OS. Phase 0 provides the private owner account, service status, database migrations, a small background worker, and the local deployment foundation. It does not collect sources, call AI models, or run graph, n8n, or browser services yet.

## Start locally

Requirements: Docker Compose v2, Python 3.12, uv, Node.js 24, and npm. On Windows, run commands from PowerShell:

```powershell
./scripts/dev.ps1 setup
./scripts/dev.ps1 dev
```

On macOS/Linux, use `make setup` and `make dev`. Setup creates `.env` once with random setup, CSRF, and database secrets; it does not print their values or replace an existing file. Open `.env` locally and copy `SETUP_TOKEN` into the first-run setup form at [http://localhost:3000](http://localhost:3000). Keep `.env` private.

The web service binds to `127.0.0.1` only. For remote use, place it behind an HTTPS reverse proxy, set `PUBLIC_ORIGIN` to the public origin and `SECURE_COOKIES=true`, then restart the stack. Do not expose the API, Redis, or PostgreSQL ports directly.

## Commands

Both `scripts/dev.ps1` and Make provide `setup`, `dev`, `stop`, `migrate`, `lint`, `typecheck`, `test`, and `build`. `test` starts a uniquely named disposable Compose project on temporary loopback ports, runs backend, real-PostgreSQL race, and browser checks, then removes only that project's containers and volumes. It never touches the normal `bbd-os` data volumes. `seed`, `reset`, `backup`, and `restore` are planned for later phases and are not implemented.

PostgreSQL migrations run before API and worker startup. Their persistent data uses named volumes. `docker compose logs api migrate worker` shows service diagnostics; do not share logs with `.env` values. If startup is blocked, inspect `docker compose ps` and the migration service first.

## OmniRoute and privacy

`OMNIROUTE_BASE_URL` and `OMNIROUTE_API_KEY` are optional placeholders. Phase 0 reports whether the gateway is configured but does not verify connectivity or send prompts. Provider/model calls and source ingestion are deferred to later phases. Review [privacy](docs/privacy.md) and [deployment](docs/deployment.md) before enabling remote access or adding connectors.

See [development](docs/development.md), [deployment](docs/deployment.md), [privacy](docs/privacy.md), and [implementation status](docs/IMPLEMENTATION_STATUS.md).
