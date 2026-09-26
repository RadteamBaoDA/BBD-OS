from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree
from urllib.parse import urljoin

import httpx

from modules.connectors.public import overlap_floor, validate_public_url


def workflow_state(cursor: str | None) -> dict[str, str | None]:
    floor = overlap_floor(cursor)
    return {
        "cursor_before": cursor,
        "catch_up_since": floor.isoformat() if floor is not None else None,
    }


async def read_rss(url: str, cursor: str | None) -> dict[str, object]:
    from modules.connectors.registry import normalize

    await validate_public_url(url)
    floor = overlap_floor(cursor)
    visited: set[str] = set()
    records: list[dict[str, object]] = []
    total_bytes = 0
    current_url: str | None = url
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        for _ in range(10):
            if current_url is None or current_url in visited:
                break
            await validate_public_url(current_url)
            visited.add(current_url)
            async with client.stream("GET", current_url, headers={"Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml"}) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("RSS redirect has no location")
                    current_url = urljoin(current_url, location)
                    await validate_public_url(current_url)
                    continue
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    total_bytes += len(chunk)
                    if total_bytes > 25 * 1024 * 1024:
                        raise ValueError("RSS pagination exceeded the 25 MiB limit")
                    body.extend(chunk)
            root = ElementTree.fromstring(bytes(body))

            def text(element: ElementTree.Element, names: set[str]) -> str:
                for child in element.iter():
                    if child.tag.rsplit("}", 1)[-1].lower() in names:
                        return "".join(child.itertext()).strip()
                return ""

            for item in (node for node in root.iter() if node.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}):
                identifier = text(item, {"guid", "id", "link"})
                title = text(item, {"title"})
                content = text(item, {"encoded", "content", "summary", "description"}) or title
                raw_date = text(item, {"updated", "published", "pubdate", "date"})
                observed_at = datetime.now(UTC)
                if raw_date:
                    try:
                        observed_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                    except ValueError:
                        try:
                            observed_at = parsedate_to_datetime(raw_date)
                        except (TypeError, ValueError):
                            pass
                if observed_at.tzinfo is None:
                    observed_at = observed_at.replace(tzinfo=UTC)
                observed_at = observed_at.astimezone(UTC)
                if floor is None or observed_at >= floor:
                    records.append(
                        normalize(
                            {
                                "provider_id": identifier or url,
                                "content": content[:4_000],
                                "observed_at": observed_at.isoformat(),
                                "version": raw_date or None,
                                "metadata": {"title": title[:1_000]},
                            }
                        )
                    )
                if len(records) == 500:
                    break

            next_link = next(
                (node.attrib.get("href") for node in root.iter() if node.tag.rsplit("}", 1)[-1].lower() == "link" and node.attrib.get("rel", "").lower() == "next"),
                None,
            )
            current_url = urljoin(current_url, next_link) if next_link else None
            if len(records) >= 500:
                break
    return {
        "cursor_before": cursor,
        "cursor_after": max((str(row["observed_at"]) for row in records), default=cursor),
        "records": records,
    }
