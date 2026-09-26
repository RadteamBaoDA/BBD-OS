import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from crawlee import ConcurrencySettings
from fastapi import FastAPI, Header, HTTPException
from pydantic import ValidationError

from core.config import Settings
from modules.connectors.n8n import read_rss
from modules.connectors.public import CrawlRequest, RSSRequest, validate_public_url
from modules.connectors.registry import normalize

MAX_BYTES = 25 * 1024 * 1024
_job_lock = asyncio.Lock()
app = FastAPI(title="BBD-OS bounded browser collector")


async def _dns_safe(url: str) -> None:
    await validate_public_url(url)


async def preview_rss(payload: RSSRequest) -> dict[str, object]:
    if _job_lock.locked():
        raise HTTPException(status_code=429, detail="A browser job is already running")
    async with _job_lock:
        async with asyncio.timeout(60):
            return await read_rss(str(payload.url), payload.cursor)


async def crawl(payload: CrawlRequest) -> list[dict[str, Any]]:
    if _job_lock.locked():
        raise HTTPException(status_code=429, detail="A browser job is already running")
    async with _job_lock:
        await _dns_safe(str(payload.url))
        records: list[dict[str, Any]] = []
        state = {"bytes": 0}
        deadline = timedelta(seconds=payload.timeout_seconds)

        async def append(url: str, content: str, size: int) -> None:
            state["bytes"] += size
            if state["bytes"] > MAX_BYTES:
                raise HTTPException(status_code=413, detail="Browser download limit exceeded")
            records.append(
                normalize(
                    {
                        "provider_id": url,
                        "content": content[:200_000],
                        "observed_at": datetime.now(UTC).isoformat(),
                        "metadata": {"url": url},
                    }
                )
            )

        async with asyncio.timeout(deadline.total_seconds()):
            if payload.mode == "http":
                from crawlee.crawlers import BeautifulSoupCrawler, BeautifulSoupCrawlingContext

                crawler = BeautifulSoupCrawler(
                    max_requests_per_crawl=payload.max_pages,
                    max_crawl_depth=payload.max_depth,
                    max_request_retries=0,
                    request_handler_timeout=deadline,
                    concurrency_settings=ConcurrencySettings(max_concurrency=1, max_tasks_per_minute=60),
                    respect_robots_txt_file=True,
                    configure_logging=False,
                )

                @crawler.router.default_handler
                async def handle_http(context: BeautifulSoupCrawlingContext) -> None:
                    await _dns_safe(context.request.url)
                    remaining = MAX_BYTES - state["bytes"]
                    length = context.http_response.headers.get("content-length")
                    if length and int(length) > remaining:
                        state["exceeded"] = True
                        raise HTTPException(status_code=413, detail="Browser download limit exceeded")
                    body = await context.http_response.read()
                    text = context.soup.get_text("\n", strip=True)
                    await append(context.request.loadedUrl or context.request.url, text, len(body))
                    await context.enqueue_links()

                crawler.pre_navigation_hook(lambda context: _dns_safe(context.request.url))
                await crawler.run([str(payload.url)])
            else:
                from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext

                crawler = PlaywrightCrawler(
                    max_requests_per_crawl=payload.max_pages,
                    max_crawl_depth=payload.max_depth,
                    max_request_retries=0,
                    request_handler_timeout=deadline,
                    navigation_timeout=deadline,
                    concurrency_settings=ConcurrencySettings(max_concurrency=1, max_tasks_per_minute=60),
                    headless=True,
                    configure_logging=False,
                )

                response_tasks: list[asyncio.Task[None]] = []

                async def guard(context: Any) -> None:
                    await _dns_safe(context.request.url)

                    async def check_request(route: Any) -> None:
                        try:
                            if state.get("exceeded"):
                                await route.abort()
                                return
                            await _dns_safe(route.request.url)
                            await route.continue_()
                        except (ValueError, OSError):
                            await route.abort()

                    await context.page.route("**/*", check_request)

                    async def count_response(response: Any) -> None:
                        length = response.headers.get("content-length")
                        if length and state["bytes"] + int(length) > MAX_BYTES:
                            state["exceeded"] = True
                            return
                        try:
                            body = await response.body()
                        except Exception:
                            return
                        state["bytes"] += len(body)
                        if state["bytes"] > MAX_BYTES:
                            state["exceeded"] = True

                    def capture_response(response: Any) -> None:
                        response_tasks.append(asyncio.create_task(count_response(response)))

                    context.page.on("response", capture_response)

                @crawler.router.default_handler
                async def handle_browser(context: PlaywrightCrawlingContext) -> None:
                    if state.get("exceeded"):
                        raise HTTPException(status_code=413, detail="Browser download limit exceeded")
                    page = context.page
                    text = await page.locator("body").inner_text(timeout=payload.timeout_seconds * 1000)
                    await append(page.url, text, 0)
                    await context.enqueue_links()

                crawler.pre_navigation_hook(guard)
                await crawler.run([str(payload.url)])
                if response_tasks:
                    await asyncio.gather(*response_tasks, return_exceptions=True)
                if state.get("exceeded"):
                    raise HTTPException(status_code=413, detail="Browser download limit exceeded")
        return records


@app.post("/crawl")
async def collect(
    payload: CrawlRequest, authorization: str | None = Header(default=None)
) -> list[dict[str, Any]]:
    settings = Settings()
    scheme, _, token = (authorization or "").partition(" ")
    expected = settings.browser_shared_token.get_secret_value()
    if not expected or scheme.lower() != "bearer" or token != expected:
        raise HTTPException(status_code=401, detail="Browser service authentication required")
    try:
        return await crawl(payload)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Browser job timed out") from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Invalid browser job") from exc


@app.post("/rss")
async def collect_rss(
    payload: RSSRequest, authorization: str | None = Header(default=None)
) -> dict[str, object]:
    settings = Settings()
    scheme, _, token = (authorization or "").partition(" ")
    expected = settings.browser_shared_token.get_secret_value()
    if not expected or scheme.lower() != "bearer" or token != expected:
        raise HTTPException(status_code=401, detail="Browser service authentication required")
    try:
        return await preview_rss(payload)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="RSS job timed out") from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail="RSS source could not be collected") from exc
