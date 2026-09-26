from collections.abc import Iterable
from typing import Any

from modules.knowledge.documents.descriptor import descriptor as documents
from modules.sources.descriptor import descriptor as sources


def register_modules(descriptors: Iterable[Any] = (sources, documents)) -> dict[str, Any]:
    registry: dict[str, Any] = {}
    for descriptor in descriptors:
        if descriptor.id in registry:
            raise ValueError(f"Duplicate module id: {descriptor.id}")
        registry[descriptor.id] = descriptor
    for descriptor in registry.values():
        missing = set(descriptor.dependencies) - registry.keys()
        if missing:
            raise ValueError(
                f"Module {descriptor.id} has missing dependencies: {', '.join(sorted(missing))}"
            )
    return registry
