from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from copy import deepcopy
import json
from pathlib import Path
from xml.etree import ElementTree
from urllib.parse import urljoin
from typing import Any
from uuid import UUID

import httpx

from modules.connectors.public import overlap_floor, validate_public_url
from modules.sources.schemas import ConnectorSource


def workflow_state(cursor: str | None) -> dict[str, str | None]:
    floor = overlap_floor(cursor)
    return {
        "cursor_before": cursor,
        "catch_up_since": floor.isoformat() if floor is not None else None,
    }


def workflow_name(source_id: UUID, operation_id: UUID) -> str:
    return f"BBD-OS connector {source_id} {operation_id.hex}"


def workflow_webhook_path(source_id: UUID, source_type: str) -> str:
    connector_type = {"api": "rest", "web": "url", "rss": "rss"}[source_type]
    return f"bbd-collect-{connector_type}-{source_id.hex}"


def build_workflow(
    source: ConnectorSource,
    *,
    desired_revision: int,
    workflow_operation_id: UUID,
    workflow_name_value: str | None = None,
    collector_credential_id: str,
    manual_credential_id: str,
    provider_credential_id: str | None,
) -> dict[str, Any]:
    filename = {"rss": "rss.json", "web": "url.json", "api": "rest.json"}.get(source.type)
    if filename is None:
        raise ValueError("This source type has no packaged workflow")
    path = Path(__file__).resolve().parents[2] / "infrastructure" / "n8n" / "workflows" / filename
    workflow = deepcopy(json.loads(path.read_text(encoding="utf-8")))
    source_id = str(source.id)
    collector_names = {
        "Read bounded RSS / Atom pages",
        "Validate source",
        "Validate source and load cursor",
        "Collect bounded pages",
        "Submit acknowledged batch",
        "Acknowledge no changes",
    }
    for node in workflow["nodes"]:
        if node.get("name") == "Manual collection":
            node["parameters"]["path"] = workflow_webhook_path(source.id, source.type)
            node.setdefault("credentials", {}).setdefault("httpHeaderAuth", {})
            node["credentials"]["httpHeaderAuth"].update(
                {"id": manual_credential_id, "name": "BBD-OS manual trigger"}
            )
        elif node.get("name") in collector_names:
            node.setdefault("credentials", {}).setdefault("httpHeaderAuth", {})
            node["credentials"]["httpHeaderAuth"].update(
                {"id": collector_credential_id, "name": "BBD-OS source collector"}
            )
        elif node.get("name") == "Fetch REST pages":
            if provider_credential_id:
                node["parameters"]["authentication"] = "genericCredentialType"
                node["parameters"]["genericAuthType"] = "httpHeaderAuth"
                node.setdefault("credentials", {})["httpHeaderAuth"] = {
                    "id": provider_credential_id,
                    "name": "BBD-OS provider credential",
                }
            else:
                node["parameters"]["authentication"] = "none"
                node["parameters"].pop("genericAuthType", None)
                node.pop("credentials", None)
    workflow["name"] = workflow_name_value or workflow_name(source.id, workflow_operation_id)
    workflow["settings"]["timezone"] = str(
        source.configuration.get("timezone", "Asia/Ho_Chi_Minh")
    )

    def bind_source_id(value: Any) -> Any:
        if isinstance(value, str):
            return (
                value.replace("{{$env.BBD_SOURCE_ID}}", source_id)
                .replace("__BBD_SOURCE_ID__", source_id)
                .replace("__BBD_SOURCE_GENERATION__", str(source.generation))
                .replace("__BBD_CONNECTOR_REVISION__", str(desired_revision))
            )
        if isinstance(value, list):
            return [bind_source_id(item) for item in value]
        if isinstance(value, dict):
            return {key: bind_source_id(item) for key, item in value.items()}
        return value

    bound = bind_source_id(workflow)
    return {
        key: bound[key]
        for key in ("name", "nodes", "connections", "settings")
        if key in bound
    }


class N8nApi:
    def __init__(self, service_url: str, api_key: str) -> None:
        self._base_url = service_url.rstrip("/")
        self._headers = {"X-N8N-API-KEY": api_key}

    async def find_workflows(self, name: str) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        cursor: str | None = None
        for page in range(20):
            params: dict[str, str | int] = {"name": name, "limit": 250}
            if cursor is not None:
                params["cursor"] = cursor
            async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
                response = await client.get(
                    f"{self._base_url}/api/v1/workflows",
                    headers=self._headers,
                    params=params,
                )
                response.raise_for_status()
            payload = response.json()
            workflows = payload.get("data", [])
            if not isinstance(workflows, list):
                raise ValueError("n8n workflow lookup returned an invalid list")
            matches.extend(
                workflow for workflow in workflows
                if isinstance(workflow, dict) and workflow.get("name") == name
            )
            cursor = payload.get("nextCursor")
            if not isinstance(cursor, str) or not cursor:
                break
            if page == 19:
                raise ValueError("n8n workflow lookup exceeded its pagination bound")
        return matches

    async def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            response = await client.get(
                f"{self._base_url}/api/v1/workflows/{workflow_id}",
                headers=self._headers,
            )
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("n8n workflow response is invalid")
        return payload

    async def create_workflow(self, workflow: dict[str, Any]) -> str:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            response = await client.post(
                f"{self._base_url}/api/v1/workflows",
                headers=self._headers,
                json=workflow,
            )
            response.raise_for_status()
        identifier = response.json().get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("n8n workflow create response omitted its ID")
        return identifier

    async def update_workflow(self, workflow_id: str, workflow: dict[str, Any]) -> None:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            response = await client.put(
                f"{self._base_url}/api/v1/workflows/{workflow_id}",
                headers=self._headers,
                json=workflow,
            )
            response.raise_for_status()

    async def set_active(self, workflow_id: str, active: bool) -> None:
        action = "activate" if active else "deactivate"
        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            response = await client.post(
                f"{self._base_url}/api/v1/workflows/{workflow_id}/{action}",
                headers=self._headers,
            )
            response.raise_for_status()


def workflow_matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    """Check stable public workflow identity before associating a recovered create ID."""
    if expected.get("name") != actual.get("name"):
        return False
    expected_nodes = expected.get("nodes")
    actual_nodes = actual.get("nodes")
    if not isinstance(expected_nodes, list) or not isinstance(actual_nodes, list):
        return False
    nodes_by_name = {
        node.get("name"): node for node in actual_nodes
        if isinstance(node, dict) and isinstance(node.get("name"), str)
    }
    if len(nodes_by_name) != len(actual_nodes) or len(nodes_by_name) != len(expected_nodes):
        return False
    for wanted in expected_nodes:
        if not isinstance(wanted, dict):
            return False
        found = nodes_by_name.get(wanted.get("name"))
        if not isinstance(found, dict):
            return False
        for key in ("type", "typeVersion", "parameters"):
            if wanted.get(key) != found.get(key):
                return False
        if wanted.get("credentials", {}) != found.get("credentials", {}):
            return False
    if expected.get("connections") != actual.get("connections"):
        return False
    expected_settings = expected.get("settings", {})
    actual_settings = actual.get("settings", {})
    if not isinstance(expected_settings, dict) or not isinstance(actual_settings, dict):
        return False
    return all(actual_settings.get(key) == value for key, value in expected_settings.items())


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
