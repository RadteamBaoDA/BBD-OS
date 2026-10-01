# Deployment

The production Compose stack contains PostgreSQL with pgvector installed, Redis, a one-shot Alembic migration service, the FastAPI API, one ARQ worker, and the Next.js frontend. Application containers run as non-root users. Persistent database and Redis data live in named volumes.

The web port binds to loopback by default. For remote access, terminate HTTPS at a trusted reverse proxy and set `PUBLIC_ORIGIN` to the exact browser origin and `SECURE_COOKIES=true` in `.env`. Keep the API, Redis, PostgreSQL, and Docker socket private. Do not deploy with the example placeholder values.

To apply migrations separately, run `./scripts/dev.ps1 migrate` or `make migrate`. Compose prevents API/worker startup if migrations fail. `docker compose ps` reports health and one-shot migration state; inspect `docker compose logs migrate api worker` for failures without publishing secret-bearing configuration.

## Google sign-in

Create a Google OAuth web client, add the exact `PUBLIC_ORIGIN` to its authorized JavaScript origins, and register `<PUBLIC_ORIGIN>/api/v1/auth/google/callback` as an authorized redirect URI. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in the server `.env`; the secret is consumed by the API through Compose `env_file` and is never sent to the browser. Sign-in requests only `openid`, `email`, and `profile`. Gmail collection requires separate consent when the Gmail source is configured. Google login is available only after an owner has linked that identity from Account settings; it never creates the owner or links by email.

The design target is a 2-core, 8 GB host with remote AI inference. Phase 0 has not yet been measured on a complete deployment, so this target is not a capacity guarantee. OmniRoute credentials only configure a future gateway and are not connectivity-tested in this phase. Graph, n8n, and browser services are not installed yet.

## AI endpoint network policy

Before enabling OmniRoute or a configured web-search endpoint, set `AI_ALLOWED_ENDPOINT_HOSTS` to exact hostnames or `host:port` entries and `AI_ALLOWED_ENDPOINT_CIDRS` to the approved IPv4/IPv6 CIDRs in the protected deployment environment. Both lists are required: every DNS answer must fall within the approved CIDRs, and the client connects to a checked numeric address while retaining the original Host and TLS hostname. Empty CIDR policy denies gateway connections. Include a specific private CIDR for a self-hosted gateway; do not use broad private ranges unless the deployment operator intends to authorize them. Redirects and environment proxy variables are disabled for these SDK requests. A private certificate authority must be configured explicitly in the trusted TLS context; certificate verification stays enabled.
