import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from apps.api.main import create_app
from core.auth.routes import get_auth_redis
from core.config import Settings
from core.database import get_session


class MemoryOwnerStore:
    owner_exists = False
    lock = asyncio.Lock()


class OwnerKeyConflict(Exception):
    sqlstate = "23505"
    constraint_name = "owner_pkey"


class MemorySession:
    def __init__(self, store: MemoryOwnerStore) -> None:
        self.store = store
        self.pending = None

    async def scalar(self, _statement):
        return 1 if self.store.owner_exists else None

    def add(self, value) -> None:
        self.pending = value

    async def commit(self) -> None:
        async with self.store.lock:
            if self.store.owner_exists:
                raise IntegrityError("insert", {}, OwnerKeyConflict())
            self.store.owner_exists = True

    async def rollback(self) -> None:
        return None


class MemoryRedis:
    def pipeline(self, transaction=True):
        return MemoryPipeline()


class MemoryPipeline:
    def __init__(self) -> None:
        self.increments = 0

    def incr(self, _key):
        self.increments += 1
        return self

    def expire(self, _key, _seconds, nx=True):
        return self

    async def execute(self):
        return [1, True] * self.increments


@pytest.mark.asyncio
async def test_only_one_simultaneous_setup_request_creates_the_owner() -> None:
    store = MemoryOwnerStore()
    settings = Settings(setup_token="test-setup-token", csrf_signing_secret="test-csrf-key")
    app = create_app(settings)

    async def session_override():
        yield MemorySession(store)

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_auth_redis] = lambda: MemoryRedis()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost:3000") as client:
        csrf_response = await client.get("/api/v1/auth/csrf")
        csrf_token = csrf_response.json()["csrfToken"]
        headers = {
            "X-Setup-Token": "test-setup-token",
            "X-CSRF-Token": csrf_token,
            "Origin": "http://localhost:3000",
        }
        async def setup():
            return await client.post(
                "/api/v1/auth/setup", headers=headers,
                json={"password": "test-owner-password-42"},
            )

        responses = await asyncio.gather(setup(), setup())

    assert sorted(response.status_code for response in responses) == [201, 409]
