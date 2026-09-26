"""Explicit, fictional Phase 1 demo data."""

import asyncio
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import Settings
from modules.knowledge.documents.models import Document, DocumentVersion
from modules.knowledge.documents.public import content_hash
from modules.sources.models import Source

DEMO_NAMESPACE = "bbd-os.demo.phase-1"
SOURCE_ID = uuid5(NAMESPACE_URL, f"{DEMO_NAMESPACE}/source")
NOTES = (
    (
        "project-note",
        "Orchard lantern project",
        "Fictional project: Mira plans to catalogue the lanterns in a storybook orchard.",
    ),
    (
        "reading-note",
        "Paper boats reading note",
        "Fictional note: Jun read an article about folding paper boats for a village festival.",
    ),
)


@dataclass(frozen=True)
class SeedReport:
    created: int
    existing: int


async def seed_demo(session: AsyncSession) -> SeedReport:
    """Create the Phase 1 fixture once; preserve subsequent edits and deletions."""
    document_ids = tuple(uuid5(NAMESPACE_URL, f"{DEMO_NAMESPACE}/{key}") for key, _, _ in NOTES)
    async with session.begin():
        inserted = await session.scalar(
            insert(Source)
            .values(
                id=SOURCE_ID,
                type="manual",
                name="Demo: fictional notes",
                local_only=True,
                configuration={"demo_namespace": DEMO_NAMESPACE},
            )
            .on_conflict_do_nothing(index_elements=[Source.id])
            .returning(Source.id)
        )
        if inserted is None:
            source = await session.get(Source, SOURCE_ID)
            if source is None or source.configuration.get("demo_namespace") != DEMO_NAMESPACE:
                raise RuntimeError("Demo source identity is occupied by another source")
            document_count = await session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.source_id == SOURCE_ID, Document.id.in_(document_ids))
            )
            return SeedReport(created=0, existing=1 + (document_count or 0))

        for (key, title, content), document_id in zip(NOTES, document_ids, strict=True):
            digest = content_hash(content)
            session.add(
                Document(
                    id=document_id,
                    source_id=SOURCE_ID,
                    external_id=f"{DEMO_NAMESPACE}/{key}",
                    title=title,
                    metadata_json={"demo_namespace": DEMO_NAMESPACE},
                    current_version=1,
                    content_hash=digest,
                )
            )
            session.add(
                DocumentVersion(
                    id=uuid5(NAMESPACE_URL, f"{DEMO_NAMESPACE}/{key}/version-1"),
                    document_id=document_id,
                    version_number=1,
                    content=content,
                    content_hash=digest,
                )
            )
    return SeedReport(created=1 + len(NOTES), existing=0)


async def _run_seed() -> None:
    engine = create_async_engine(Settings().database_url, pool_pre_ping=True)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            report = await seed_demo(session)
        print(f"Demo seed: created={report.created}, existing={report.existing}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_run_seed())
