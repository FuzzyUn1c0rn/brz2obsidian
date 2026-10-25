"""Shared lexical validation for application handles and selections."""

from pathlib import Path
from uuid import UUID


def absolute(value: str) -> str:
    if not Path(value).is_absolute():
        raise ValueError("An absolute path is required")
    return value


def request_identity(value: str) -> str:
    if str(UUID(value)) != value:
        raise ValueError("A canonical UUID is required")
    return value
