import os
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@pytest.fixture
async def anonymous_client() -> AsyncIterator[AsyncClient]:
    base_url = os.getenv("BBD_API_URL", "http://localhost:38000")
    origin = os.getenv("TEST_PUBLIC_ORIGIN", "http://localhost:3300")
    async with AsyncClient(base_url=base_url, headers={"Origin": origin}) as client:
        yield client


@pytest.fixture
async def owner_client() -> AsyncIterator[AsyncClient]:
    base_url = os.getenv("BBD_API_URL", "http://localhost:38000")
    origin = os.getenv("TEST_PUBLIC_ORIGIN", "http://localhost:3300")
    async with AsyncClient(base_url=base_url) as client:
        csrf_response = await client.get("/api/v1/auth/csrf")
        csrf_response.raise_for_status()
        login = await client.post(
            "/api/v1/auth/login",
            headers={"Origin": origin, "X-CSRF-Token": csrf_response.json()["csrfToken"]},
            json={"password": "test-owner-password-42"},
        )
        login.raise_for_status()
        client.headers.update(
            {"Origin": origin, "X-CSRF-Token": login.json()["csrfToken"]}
        )
        yield client


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is available only in the disposable test runner")
    parsed = make_url(database_url)
    if (
        parsed.drivername != "postgresql+asyncpg"
        or parsed.database != "bbd_test"
        or parsed.username != "bbd_test"
        or parsed.host not in {"localhost", "127.0.0.1", "::1"}
    ):
        pytest.fail("Refusing database fixture URL outside the disposable local bbd_test database")

    engine = create_async_engine(database_url, pool_size=1, max_overflow=0)
    async with engine.connect() as connection:
        database, user = (await connection.execute(text("SELECT current_database(), current_user"))).one()
        if database != "bbd_test" or user != "bbd_test":
            pytest.fail("Refusing database fixture connection outside bbd_test/bbd_test")
        await connection.rollback()
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()
