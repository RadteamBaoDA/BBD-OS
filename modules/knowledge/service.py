"""Narrow public facade for knowledge owners consumed by presentation routes."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from modules.knowledge.entities import public as entities
from modules.knowledge.relationships import public as relationships


class KnowledgeService:
    """Adapt the public entity and relationship contracts for route consumers."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the request-scoped session used by delegated contract calls."""
        self.session = session

    async def entities(self, *, limit: int, cursor: str | None, entity_type: str | None, query: str | None):
        """List entities through the owning public contract with its page filters."""
        return await entities.list_entities(self.session, limit, cursor, entity_type, query)

    async def entity(self, entity_id: UUID):
        """Resolve one entity through its owning public contract."""
        return await entities.get_entity(self.session, entity_id)

    async def entity_evidence(self, entity_id: UUID, *, limit: int, cursor: str | None):
        """List versioned evidence for an entity through its public contract."""
        return await entities.list_entity_evidence(self.session, entity_id, limit, cursor)

    async def entity_neighbors(self, entity_id: UUID, *, limit: int, cursor: str | None):
        """Read adjacent entities and relationships through the relationship owner."""
        return await relationships.get_neighbors(self.session, entity_id, limit, cursor)

    async def entity_review(self, *, limit: int, cursor: str | None = None):
        """List owner-review candidates using the extraction snapshot contract."""
        return await entities.list_review_candidates(self.session, limit, cursor)

    async def assign_review_candidate(self, candidate_id: UUID, payload, *, actor_id: int):
        """Delegate a review assignment with its authenticated actor identity."""
        return await entities.assign_review_candidate(self.session, candidate_id, payload, actor_id=actor_id)

    async def resolve_relationship_review(self, candidate_id: UUID, payload, *, actor_id: int):
        """Delegate relationship review with its authenticated actor identity."""
        return await entities.resolve_relationship_review(self.session, candidate_id, payload, actor_id=actor_id)
