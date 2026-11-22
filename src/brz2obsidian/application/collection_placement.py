"""Render a source into separate staging for a scoped import review."""

from pathlib import Path

from brz2obsidian.contracts import ImportLinkConnection, Issue, MigrationRefused
from brz2obsidian.core.import_placement import validate_import_location
from brz2obsidian.core.naming import readable_filename
from brz2obsidian.obsidian.import_links import reserved_import_names
from brz2obsidian.publication.collection_placement import (
    existing_files,
    location_conflict,
    observe_collection_placement,
    read_rendered_collection,
    uncreated_destinations,
)

from .update_contracts import UpdateResult


def _placement_inputs(existing, reserved, root, snapshot, location, choices, preview):
    location = validate_import_location(
        location
        if location is not None
        else "Imports/" + readable_filename(snapshot.collection_title)
    )
    if location_conflict(root, location):
        raise MigrationRefused(
            (
                Issue(
                    code="import_target_occupied",
                    phase="planning",
                    message="The import folder conflicts with an existing vault path.",
                    guidance="Choose a distinct import location.",
                ),
            )
        )
    return {
        "import_location": location,
        "reserved_names": reserved_import_names(
            existing,
            location,
            reserved_paths=reserved,
            connections=choices,
            preview_connections=preview,
        ),
        "import_link_connections": choices,
    }


def _refused(code, *, impact=None, findings=()):
    return UpdateResult(
        kind="collection_import",
        status="refused",
        code=code,
        findings=findings,
        import_link_impact=impact,
        next_actions=("review_import_placement",),
    )


def prepare_collection_import_from_source(
    operations,
    workflow,
    vault,
    source,
    *,
    staging,
    import_location,
    connections,
    preview_connections,
):
    from .collection_import import (
        _history_refusal,
        _rendered_receipt_matches,
        prepare_collection_import,
    )

    try:
        root, staging = Path(vault).resolve(), Path(staging).resolve()
        if root == staging or root in staging.parents or staging in root.parents:
            return _refused("distinct_source_required")
        history = operations.inspect_history(root)
        unavailable = _history_refusal(history)
        if unavailable is not None:
            return unavailable
        existing = existing_files(history.admission)
        reserved, gaps = uncreated_destinations(history.admission, history.checkpoint)
        choices = tuple(ImportLinkConnection.model_validate(row) for row in connections)
        result = workflow.convert_collection(
            source,
            staging,
            placement=lambda snapshot: _placement_inputs(
                existing,
                reserved + gaps,
                root,
                snapshot,
                import_location,
                choices,
                preview_connections,
            ),
        )
        if result.outcome not in ("clean", "warnings") or result.receipt is None:
            codes = tuple(issue.code for issue in result.issues)
            return _refused(
                codes[0] if codes else "collection_render_unavailable", findings=codes
            )
        record_path = next(
            row.relative_path
            for row in result.receipt.manifest
            if row.relative_path.endswith("/migration-record.json")
        )
        if preview_connections:
            incoming = read_rendered_collection(staging, record_path)
            if not _rendered_receipt_matches(incoming, result.receipt):
                return _refused("source_payload_changed")
            current = operations.inspect_history(root)
            impact = observe_collection_placement(
                current.admission,
                current.checkpoint,
                incoming,
                record_path,
                connections=choices,
            )
            return _refused("import_connection_preview", impact=impact)
        return prepare_collection_import(
            operations,
            root,
            staging,
            record_path=record_path,
            rendered=result.receipt,
            connections=choices,
        )
    except MigrationRefused as error:
        return _refused(error.issues[0].code)
    except OSError, ValueError, TypeError, KeyError, StopIteration:
        return _refused("collection_placement_unavailable")
