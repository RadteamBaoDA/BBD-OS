#!/usr/bin/env bash
set -euo pipefail
project="bbd-os-test-$(python -c 'import secrets; print(secrets.token_hex(5))')"
free_port() { python -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'; }
export WEB_PORT="$(free_port)"
export API_TEST_PORT="$(free_port)"
export TEST_PUBLIC_ORIGIN="http://localhost:${WEB_PORT}"
compose=(docker compose -p "$project" -f docker-compose.yml -f docker-compose.test.yml)
cleanup() { "${compose[@]}" down --volumes --remove-orphans; }
trap cleanup EXIT
"${compose[@]}" up -d --build
# `up` waits for migration completion; this second run proves the revision is idempotent.
"${compose[@]}" run --rm migrate
uv run pytest -q
BBD_INTEGRATION=1 BBD_API_URL="http://localhost:${API_TEST_PORT}" \
TEST_PUBLIC_ORIGIN="$TEST_PUBLIC_ORIGIN" uv run pytest tests/integration -q
"${compose[@]}" exec -T postgres psql -U bbd_test -d bbd_test -c 'TRUNCATE auth_session, owner CASCADE'
E2E_SETUP_TOKEN=bbd-os-disposable-test-token \
PLAYWRIGHT_BASE_URL="http://localhost:${WEB_PORT}" \
PLAYWRIGHT_EXTERNAL_SERVER=1 npm run test:e2e
