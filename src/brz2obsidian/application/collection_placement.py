"""Placement and link evidence for a rendered import in an existing vault."""

import json
import unicodedata
from pathlib import Path

from brz2obsidian.contracts import (
    ContentIdentity,
    ImportLinkConnection,
    ImportLinkImpact,
    Issue,
    MigrationRefused,
)
from brz2obsidian.core.import_placement import validate_import_location
from brz2obsidian.core.naming import readable_filename
from brz2obsidian.obsidian.import_links import (
    inspect_import_links,
    reserved_import_names,
)
from brz2obsidian.publication.vault_history import collection_baselines
from brz2obsidian.publication.vault_native import verify_directory

from .checkpoint_payload_contracts import CheckpointPayloadRequest
from .update_contracts import UpdateResult
from .update_lifecycle import _read_physical


def _name_key(name):
    return unicodedata.normalize("NFC", name).casefold()


def _location_conflict(root, location):
    directory = root
    for part in location.split("/"):
        verify_directory(directory)
        matches = tuple(
            entry
            for entry in directory.iterdir()
            if _name_key(entry.name) == _name_key(part)
        )
        if not matches:
            return False
        if len(matches) != 1 or matches[0].name != part:
            return True
        directory = matches[0]
        if not directory.is_dir():
            return True
    verify_directory(directory)
    return False


def _existing_files(history):
    admission = history.admission
    if not admission.inventory_complete:
        raise OSError("The vault link inventory is incomplete")
    rows = tuple(
        row
        for row in admission.inventory
        if row.exclusion not in ("cache", "temporary")
    )
    documents = tuple(
        row for row in rows if row.path.casefold().endswith((".md", ".base"))
    )
    exact = _read_physical(admission.vault, documents)
    return {
        row.path: exact[row.path]
        if row.path in exact
        else ContentIdentity(
            content_id=f"sha256:{row.sha256}:{row.size}",
            sha256=row.sha256,
            size=row.size,
        )
        for row in rows
    }


def _retained_record(operations, history, identity, manifest):
    path = manifest.collection_record_path or "migration-record.json"
    file = next(row for row in manifest.source if row.path == path)
    payload = operations.read_checkpoint_payload(
        history.admission.vault,
        locator=history.checkpoint.locator,
        collection=identity,
        requests=(CheckpointPayloadRequest(path=path, limit=file.size),),
        byte_limit=file.size,
    )
    if payload.status != "available" or len(payload.chunks) != 1:
        raise OSError("The active collection source record is unavailable")
    return json.loads(payload.chunks[0].data)


def _uncreated_destinations(operations, history):
    reserved, gaps = set(), set()
    checkpoint = history.checkpoint
    if checkpoint is not None and checkpoint.status == "valid":
        for identity, (_, manifest) in collection_baselines(checkpoint).items():
            record = _retained_record(operations, history, identity, manifest)
            reserved.update(
                row["relative_path"]
                for row in record["item_targets"]
                if not row["created"]
            )
            gaps.update(
                row["owner_target"]
                for row in record.get("source_gaps", ())
                if not row["owner_created"]
            )
    return tuple(sorted(reserved)), tuple(sorted(gaps))


def collection_connection_choices(record):
    return tuple(
        ImportLinkConnection.model_validate(row)
        for row in record.get("import_link_connections", ())
    )


def observe_collection_placement(
    operations, history, incoming, record_path, *, connections
):
    """Use the same authenticated source and working inventory on every observation."""
    source_record = json.loads(incoming[record_path])
    location = record_path.rsplit("/", 1)[0]
    if source_record.get("collection_location", location) != location:
        return ImportLinkImpact(blockers=("collection_scope_changed",))
    try:
        validate_import_location(location)
    except MigrationRefused as error:
        return ImportLinkImpact(blockers=(error.issues[0].code,))
    root = Path(history.admission.vault)
    if _location_conflict(root, location):
        return ImportLinkImpact(blockers=("import_target_occupied",))
    existing = _existing_files(history)
    reserved, gaps = _uncreated_destinations(operations, history)
    if collection_connection_choices(source_record) != connections:
        return ImportLinkImpact(blockers=("import_connection_approval_missing",))
    return inspect_import_links(
        existing,
        incoming,
        reserved_paths=reserved,
        gap_paths=gaps,
        connections=connections,
    )


def _placement_inputs(existing, reserved, root, snapshot, location, choices, preview):
    location = validate_import_location(
        location
        if location is not None
        else "Imports/" + readable_filename(snapshot.collection_title)
    )
    if _location_conflict(root, location):
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
        _read_rendered,
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
        existing = _existing_files(history)
        reserved, gaps = _uncreated_destinations(operations, history)
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
            incoming = _read_rendered(staging, record_path)
            if not _rendered_receipt_matches(incoming, result.receipt):
                return _refused("source_payload_changed")
            impact = observe_collection_placement(
                operations,
                operations.inspect_history(root),
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
