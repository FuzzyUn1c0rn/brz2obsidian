"""Inward value boundaries; declarations do not grant access to bytes."""

from collections.abc import Mapping

from .contracts import OpaqueContent, ReconciliationContract


def require_inline(value):
    """Reject opaque values before a pure inline algorithm consumes its input."""
    pending = [value]
    seen = set()
    while pending:
        item = pending.pop()
        if isinstance(item, OpaqueContent):
            # Opaque is a valid content value; this refuses unavailable bytes.
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
