from dataclasses import dataclass


@dataclass(frozen=True)
class RelationshipDescriptor:
    id: str = "knowledge.relationships"
    name: str = "Relationships"
    version: str = "1.0.0"
    description: str = "Store owner-authored and evidence-backed relationships."
    enabled: bool = True
    dependencies: tuple[str, ...] = ("knowledge.entities", "knowledge.documents")
    provides: tuple[str, ...] = ("relationships", "relationship_evidence")
    requires: tuple[str, ...] = ("entities", "document_versions", "document_chunks")
    routes: tuple[str, ...] = ("/api/v1/relationships", "/api/v1/entities/{id}/neighbors")
    emitted_events: tuple[str, ...] = ("knowledge.changed",)
    consumed_events: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    navigation: tuple[dict[str, str], ...] = ()
    settings_schema: dict[str, object] | None = None


descriptor = RelationshipDescriptor()
