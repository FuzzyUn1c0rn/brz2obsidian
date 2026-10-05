"""Read-only structural checks of current vault files, independent of sources."""

from ._checking import check_vault
from .contracts import VaultCheckCounts, VaultCheckIssue, VaultCheckResult

__all__ = ["VaultCheckCounts", "VaultCheckIssue", "VaultCheckResult", "check_vault"]
