# Development

Install Python 3.12, uv, Node.js 24/npm, and Docker Compose v2. Run `./scripts/dev.ps1 setup` in Windows PowerShell or `make setup` on macOS/Linux. Setup creates `.env` only when missing, then installs locked Python and npm dependencies.

Run the hot-reload stack with `./scripts/dev.ps1 dev` or `make dev`. The frontend is at `http://localhost:3000`. Only its loopback port is published; API, PostgreSQL, and Redis stay on the Compose network. To stop services without deleting data, use the matching `stop` command.

The first-run form requires `SETUP_TOKEN` from the local `.env` file and a password of 12–128 characters. The setup token is separate from the owner password. The application stores only password/session hashes. Do not paste secrets into issues, screenshots, or shared logs.

Use `lint`, `typecheck`, `test`, and `build` before submitting changes. `test` creates an isolated Compose project and cleans only its uniquely named test volumes on exit. To run only the backend unit tests, use `uv run pytest -q`; to run frontend lint/typecheck, use `npm run lint` and `npm run typecheck`.

Migrations are managed through Alembic. Run `migrate` for an existing local stack; startup also runs the one-shot migration service and waits for success. Do not manually edit a live database schema.
