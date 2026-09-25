import pytest
from sqlalchemy.dialects import postgresql

from apps.worker.main import purge_expired_sessions


class FakeResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class FakeSession:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount
        self.statement = None
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, statement):
        self.statement = statement
        return FakeResult(self.rowcount)

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_expired_session_cleanup_is_batched_and_reports_deleted_rows() -> None:
    session = FakeSession(rowcount=7)

    class Factory:
        def __call__(self):
            return session

    deleted = await purge_expired_sessions({"session_factory": Factory()})
    sql = str(
        session.statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert deleted == 7
    assert session.committed
    assert "LIMIT" in sql and "1000" in sql
    assert "now()" in sql
