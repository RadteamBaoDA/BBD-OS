# P02-T3 implementation report

## Scope delivered

- Added source configuration and lifecycle-aware connector routes for RSS/Atom, REST mapping and web collection, with source-scoped collector authorization and durable ingestion receipts.
- Added RSS/Atom pagination with overlap catch-up, response-size and page limits, and source cursor handling. RSS network fetching runs through the authenticated browser sidecar, shares its one-job lock, and has a 60-second job bound.
- Added Crawlee BeautifulSoup HTTP collection and opt-in Playwright collection with page/depth/time/byte limits, public URL/DNS/redirect checks, and browser-container egress firewall rules.
- Added inactive n8n RSS, URL and REST workflow exports, placeholder environment settings, optional browser dependencies, the browser Docker image and Compose overlay, and operator setup guidance.

## Changed files

- `.env.example`
- `apps/api/main.py`
- `apps/worker/main.py`
- `core/config.py`
- `docker-compose.connectors.yml`
- `docs/connectors.md`
- `infrastructure/docker/browser-entrypoint.sh`
- `infrastructure/docker/browser.Dockerfile`
- `infrastructure/docker/n8n-connectors-entrypoint.sh`
- `infrastructure/docker/n8n-connectors.Dockerfile`
- `infrastructure/n8n/workflows/rest.json`
- `infrastructure/n8n/workflows/rss.json`
- `infrastructure/n8n/workflows/url.json`
- `modules/connectors/__init__.py`
- `modules/connectors/crawl.py`
- `modules/connectors/n8n.py`
- `modules/connectors/public.py`
- `modules/connectors/registry.py`
- `modules/connectors/routes.py`
- `modules/ingestion/public.py`
- `pyproject.toml`
- `uv.lock`
- This report.

Pre-existing changes to `AGENTS.md`, `CLAUDE.md`, GitNexus skill files, `docs/IMPLEMENTATION_STATUS.md`, the phase plans and `docs/superpowers/plans/EXECUTION.md` were preserved and are excluded from this task commit.

## Impact evidence

GitNexus upstream impact queries for `read_rss` and `preview_rss` returned UNKNOWN because those symbols were not found in the then-current index; this does not establish zero callers. Source tracing covered the API preview route, authenticated sidecar endpoint, shared browser lock, RSS fetch/normalization path, and source-scoped ingestion state.

After refreshing the GitNexus index, upstream impact for `queue_connector_crawl` was LOW, with its direct caller `submit_crawl`, two flows and one module. `crawl` was LOW, with caller `collect`, one flow and one module. `process_ingestion_event` and `submit_crawl` had no indexed upstream callers. The later review fix changed `registry.validate`, which GitNexus rated CRITICAL with 6 direct callers and 10 flows; the change is scoped to REST (`source.type == "api"`) and leaves RSS/web behavior unchanged. The reviewer also checked `validate_public_url` (CRITICAL, 12 direct callers and 14 flows); it was not changed. These results describe the refreshed graph; source review remains necessary for symbols absent from it.

## Validation

- `./scripts/dev.ps1 build` from `D:\Project\BBD-OS-phase-2`, with process-only `POSTGRES_PASSWORD=build-only-placeholder`: exit 0. Next.js production build passed and Docker built the web, API, worker and migration images.
- `docker compose -f docker-compose.yml -f docker-compose.connectors.yml build browser`: exit 0; the browser image built with the pinned dependency lock and Chromium installation.
- `docker compose -f docker-compose.yml -f docker-compose.connectors.yml build n8n`: exit 0; the firewall image built and both `iptables --version` and `ip6tables --version` passed. Earlier attempts showed the hardened n8n base has neither `apk` nor `apt-get`; the multi-stage Alpine image then failed because copied shared-library symlinks lacked their targets. Copying those binaries and libraries with `cp -aL` fixed the image build.
- After the final review fixes, `./scripts/dev.ps1 build` passed again, and `docker compose -f docker-compose.yml -f docker-compose.connectors.yml build browser n8n` passed (both images built).

No tests or fixtures were created, modified or run. No lint or standalone typecheck was run. The Compose stack was not launched; workflow import, credential mapping, browser firewall behavior and live provider pagination remain deferred runtime acceptance gates until all Phase 1-12 production code is complete.

## Review boundary

RSS preview no longer fetches feed pages from the API process. It calls the browser service using its shared bearer token; the sidecar applies the same job lock used by crawling and a 60-second timeout. Build success verifies image construction, not these runtime network and workflow behaviors.

## Scoped review fixes

The independent review and follow-up source review identified connector hardening gaps, addressed in the scoped follow-up changes:

1. URL crawl submission now persists an ingestion batch, run, stage and `connector.crawl.requested` outbox event, returning its `run_id` immediately. The existing ARQ dispatcher/worker performs collection; observations and the source cursor are committed only after successful collection, and the existing run endpoint provides polling.
2. The HTTP collector now reads response bodies as a stream, counts bytes across the complete job, aborts as soon as the 25 MiB budget is exceeded, and fails the whole batch. Redirect destinations are checked before requesting them; declared sizes can reject early without replacing streamed accounting.
3. REST pagination constrains every `next_url` to the configured origin and disables redirects. n8n runs on a dedicated private API network plus a filtered egress network; PostgreSQL and Redis are not attached. The n8n image firewall permits API traffic, DNS and public HTTP(S), while blocking private and reserved IPv4 destinations.
4. REST items without a valid updated timestamp now receive a stable observation timestamp, and the cursor is preserved unless a valid update timestamp exists. Identical pages therefore produce an idempotent batch key on later runs.
5. RSS preview calls the sidecar with the required shared bearer authorization header.
6. The Playwright response interceptor resumes 3xx responses with `Fetch.continueResponse` rather than attempting to read a response body; the page request route still validates each redirected URL before network continuation. REST source configuration now rejects explicit nonstandard HTTP(S) ports, while RSS/web URL handling is unchanged. REST `next_url` values remain constrained to the initial URL's origin, including its now-standard port.

The GitNexus tools available in this session expose no `detect_changes` operation, and `npx gitnexus --help` lists no equivalent CLI command. Before commit, the staged file list and staged diff are checked directly to confirm scope; this is not a GitNexus `detect_changes` result.
