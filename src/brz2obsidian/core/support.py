"""Version-two support namespace, reserved before imported target assignment.

Later slices activate these obligations; reservation alone creates no files.
"""

from pathlib import PurePosixPath

from brz2obsidian.contracts import SupportArtifact

SUPPORT_NAMESPACE = (
    SupportArtifact(relative_path="MIGRATION REPORT.md", purpose="report"),
    SupportArtifact(relative_path="migration-record.json", purpose="migration_record"),
    SupportArtifact(relative_path=".obsidian/app.json", purpose="configuration"),
    SupportArtifact(relative_path=".obsidian/bookmarks.json", purpose="configuration"),
    SupportArtifact(relative_path="Uncreated targets.md", purpose="listing"),
    SupportArtifact(relative_path="Tag memberships.md", purpose="listing"),
    SupportArtifact(relative_path="Categories.md", purpose="overview"),
    SupportArtifact(relative_path="Vault guide.md", purpose="guide"),
    SupportArtifact(relative_path="Templates/New note.md", purpose="template"),
    SupportArtifact(relative_path="Templates/Category starter.md", purpose="starter"),
    SupportArtifact(
        relative_path="Templates/Member template starter.md", purpose="starter"
    ),
    SupportArtifact(relative_path="Templates/Bases/Members.base", purpose="base"),
    SupportArtifact(relative_path="Templates/Bases/Gallery.base", purpose="base"),
    SupportArtifact(relative_path="Templates/Bases/Categories.base", purpose="base"),
    SupportArtifact(relative_path="Templates/Bases/Starter.base", purpose="starter"),
    SupportArtifact(
        relative_path=".obsidian/core-plugins.json", purpose="configuration"
    ),
    SupportArtifact(relative_path=".obsidian/templates.json", purpose="configuration"),
    SupportArtifact(relative_path=".obsidian/types.json", purpose="configuration"),
)

SUPPORTING_NAMES = frozenset(
    PurePosixPath(a.relative_path).stem.casefold() for a in SUPPORT_NAMESPACE
)


def support_artifacts(has_uncreated_listing, tag_listing_path):
    paths = {
        "MIGRATION REPORT.md",
        "migration-record.json",
        ".obsidian/app.json",
        ".obsidian/bookmarks.json",
    }
    if has_uncreated_listing:
        paths.add("Uncreated targets.md")
    if tag_listing_path:
        paths.add(tag_listing_path)
    return tuple(a for a in SUPPORT_NAMESPACE if a.relative_path in paths)
