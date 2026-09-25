import asyncio
import os

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.skipif(
    os.getenv("BBD_INTEGRATION") != "1", reason="requires disposable Compose test services"
)


@pytest.mark.asyncio
async def test_simultaneous_setup_requests_create_exactly_one_owner() -> None:
    base_url = os.getenv("BBD_API_URL", "http://localhost:38000")
    origin = os.getenv("TEST_PUBLIC_ORIGIN", "http://localhost:3300")

    async with (
        AsyncClient(base_url=base_url) as first,
        AsyncClient(base_url=base_url) as second,
    ):
        first_csrf = (await first.get("/api/v1/auth/csrf")).json()["csrfToken"]
        second_csrf = (await second.get("/api/v1/auth/csrf")).json()["csrfToken"]

        async def create_owner(client: AsyncClient, csrf_token: str):
            return await client.post(
                "/api/v1/auth/setup",
                headers={
                    "Origin": origin,
                    "X-CSRF-Token": csrf_token,
                    "X-Setup-Token": "bbd-os-disposable-test-token",
                },
                json={"password": "test-owner-password-42"},
            )

        responses = await asyncio.gather(
            create_owner(first, first_csrf), create_owner(second, second_csrf)
        )
        assert sorted(response.status_code for response in responses) == [201, 409]
