import asyncio
import base64
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
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
                queue = [(str(payload.url), 0)]
                visited: set[str] = set()
                async with httpx.AsyncClient(
                    timeout=deadline.total_seconds(), follow_redirects=False, trust_env=False
                ) as client:
                    while queue and len(records) < payload.max_pages:
                        request_url, depth = queue.pop(0)
                        if request_url in visited:
                            continue
                        current_url = request_url
                        response: httpx.Response | None = None
                        for _ in range(6):
                            await _dns_safe(current_url)
                            visited.add(current_url)
                            response = await client.send(client.build_request("GET", current_url, headers={"Accept": "text/html,application/xhtml+xml"}), stream=True)
                            if response.status_code not in {301, 302, 303, 307, 308}:
                                break
                            location = response.headers.get("location")
                            await response.aclose()
                            if not location:
                                raise ValueError("Web redirect has no location")
                            current_url = urljoin(current_url, location)
                            await _dns_safe(current_url)
                        else:
                            raise ValueError("Web redirect limit exceeded")
                        if response is None:
                            raise ValueError("Web response was not received")
                        async with response:
                            response.raise_for_status()
                            length = response.headers.get("content-length")
                            if length and int(length) > MAX_BYTES - state["bytes"]:
                                raise HTTPException(status_code=413, detail="Browser download limit exceeded")
                            body = bytearray()
                            async for chunk in response.aiter_bytes():
                                state["bytes"] += len(chunk)
                                if state["bytes"] > MAX_BYTES:
                                    raise HTTPException(status_code=413, detail="Browser download limit exceeded")
                                body.extend(chunk)
                        final_url = str(response.url)
                        soup = BeautifulSoup(bytes(body), "html.parser")
                        await append(final_url, soup.get_text("\n", strip=True), 0)
                        if depth < payload.max_depth:
                            for anchor in soup.find_all("a", href=True):
                                candidate = urljoin(final_url, str(anchor["href"]))
                                if urlsplit(candidate).scheme in {"http", "https"} and candidate not in visited and len(queue) < 100:
                                    queue.append((candidate, depth + 1))
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
                cdp_sessions: list[Any] = []
                response_budget_lock = asyncio.Lock()

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
                    cdp = await context.page.context.new_cdp_session(context.page)
                    cdp_sessions.append(cdp)
                    await cdp.send("Fetch.enable", {"patterns": [{"urlPattern": "*", "requestStage": "Response"}]})

                    async def intercept_response(paused: dict[str, Any]) -> None:
                        request_id = str(paused["requestId"])
                        async with response_budget_lock:
                            if state.get("exceeded"):
                                await cdp.send("Fetch.failRequest", {"requestId": request_id, "errorReason": "Aborted"})
                                return
                            try:
                                response_status = int(paused.get("responseStatusCode", 200))
                                if 300 <= response_status < 400:
                                    await cdp.send("Fetch.continueResponse", {"requestId": request_id})
                                    return
                                stream = await cdp.send("Fetch.takeResponseBodyAsStream", {"requestId": request_id})
                                handle = str(stream["stream"])
                                body = bytearray()
                                remaining = MAX_BYTES - state["bytes"]
                                while True:
                                    chunk = await cdp.send(
                                        "IO.read", {"handle": handle, "size": min(64 * 1024, remaining - len(body) + 1)}
                                    )
                                    data = (
                                        base64.b64decode(chunk["data"])
                                        if chunk.get("base64Encoded")
                                        else str(chunk.get("data", "")).encode("utf-8")
                                    )
                                    if len(body) + len(data) > remaining:
                                        state["exceeded"] = True
                                        await cdp.send("IO.close", {"handle": handle})
                                        await cdp.send(
                                            "Fetch.failRequest", {"requestId": request_id, "errorReason": "Aborted"}
                                        )
                                        return
                                    body.extend(data)
                                    if chunk.get("eof"):
                                        break
                                await cdp.send("IO.close", {"handle": handle})
                                headers = [
                                    header
                                    for header in paused.get("responseHeaders", [])
                                    if header.get("name", "").lower() not in {"content-length", "transfer-encoding"}
                                ]
                                headers.append({"name": "Content-Length", "value": str(len(body))})
                                await cdp.send(
                                    "Fetch.fulfillRequest",
                                    {
                                        "requestId": request_id,
                                        "responseCode": response_status,
                                        "responseHeaders": headers,
                                        "body": base64.b64encode(body).decode("ascii"),
                                    },
                                )
                                state["bytes"] += len(body)
                            except Exception:
                                state["interception_error"] = True
                                try:
                                    await cdp.send(
                                        "Fetch.failRequest", {"requestId": request_id, "errorReason": "Aborted"}
                                    )
                                except Exception:
                                    pass

                    cdp.on(
                        "Fetch.requestPaused",
                        lambda paused: response_tasks.append(asyncio.create_task(intercept_response(paused))),
                    )

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
                for cdp in cdp_sessions:
                    try:
                        await cdp.detach()
                    except Exception:
                        pass
                if state.get("exceeded"):
                    raise HTTPException(status_code=413, detail="Browser download limit exceeded")
                if state.get("interception_error"):
                    raise HTTPException(status_code=502, detail="Browser response could not be bounded")
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
