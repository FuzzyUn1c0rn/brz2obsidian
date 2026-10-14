"""The reviewed outer policy binding for metadata-only local acquisition."""

from brz2obsidian.contracts import SourcePolicy

LOCAL_API_POLICY = SourcePolicy(
    profile_id="thebrain-local-api-reviewed",
    profile_version="1",
    module_id="thebrain-local-api",
    module_version="1",
    format_version="1",
)
