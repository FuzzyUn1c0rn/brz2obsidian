"""Stable scoped category choices and generated navigation paths."""

from pathlib import PurePosixPath

from brz2obsidian.contracts import (
    ImportCategoryChoice,
    Issue,
    MigrationRefused,
    SupportArtifact,
)

from .import_placement import validate_import_location


def checked_choices(snapshot, location, choices):
    choices = tuple(ImportCategoryChoice.model_validate(row) for row in choices)
    definitions = {
        item.original_identity
        for item in snapshot.items
        if item.live and item.role == "definition"
    }
    if (
        choices
        and location is None
        or len({row.source_identity for row in choices}) != len(choices)
        or any(
            row.source_identity not in definitions or not _valid(row, location)
            for row in choices
        )
    ):
        raise MigrationRefused(
            (
                Issue(
                    code="import_category_mapping_invalid",
                    phase="planning",
                    message="A category choice does not match the source category or vault target.",
                    guidance="Review the category mapping against the current vault.",
                ),
            )
        )
    return choices


def _valid(row, location):
    path = row.destination_path
    if path is None:
        return not (
            row.destination_sha256 or row.destination_identity or row.compatible_view
        )
    validate_import_location(path)
    return (
        path.casefold().endswith(".md")
        and bool(row.destination_sha256)
        and not path.casefold().startswith(location.casefold() + "/")
    )


def view_paths(target):
    stem = PurePosixPath(target.relative_path).stem.removesuffix(" — source reference")
    return f"Views/{stem} — linked members.md", f"Views/{stem} — linked members.base"


def approved_views(snapshot, targets, choices):
    used = {row.definition_key for row in snapshot.classification_assignments}
    approved = {row.source_identity for row in choices if row.compatible_view}
    return tuple(
        row
        for row in targets
        if row.item_key in used and row.original_identity in approved
    )


def view_artifacts(snapshot, targets, choices):
    return tuple(
        SupportArtifact(
            relative_path=path, purpose="base" if path.endswith(".base") else "guide"
        )
        for target in approved_views(snapshot, targets, choices)
        for path in view_paths(target)
    )


def shared_destinations(plan):
    return {
        row.source_identity: row.destination_path
        for row in plan.category_choices
        if row.destination_path
    }
