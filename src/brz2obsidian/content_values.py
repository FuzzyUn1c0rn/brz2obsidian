"""Inward value boundaries; declarations do not grant access to bytes."""

from collections.abc import Mapping
from dataclasses import dataclass

from .contracts import OpaqueContent, ReconciliationContract, same_content


@dataclass(frozen=True, eq=False)
class _ExactKey:
    content: object

    def __eq__(self, other):
        if type(other) is not _ExactKey:
            return NotImplemented
        return same_content(self.content, other.content)

    def __hash__(self):
        return hash(self.content.identity)


def content_key(value):
    return None if value is None else _ExactKey(value)


def content_sha(value):
    return None if value is None else value.identity.sha256


def content_size(value):
    return value.identity.size


def require_inline(value):
    """Reject opaque values before a pure inline algorithm consumes its input."""
    pending = [value]
    seen = set()
    while pending:
        item = pending.pop()
        if isinstance(item, OpaqueContent):
            raise ValueError(  # noqa: TRY004
                "Pure review requires available inline content"
            )
        if isinstance(item, (ReconciliationContract, Mapping, tuple, list)):
            marker = id(item)
            if marker in seen:
                continue
            seen.add(marker)
            if isinstance(item, ReconciliationContract):
                pending.extend(getattr(item, name) for name in type(item).model_fields)
            elif isinstance(item, Mapping):
                pending.extend(item.values())
            else:
                pending.extend(item)
