"""Qualify scoped import paths and link choices against a native vault observation."""

import io
import json
import unicodedata
from hashlib import sha256
from pathlib import Path

from brz2obsidian.application.update_lifecycle import _read_physical
from brz2obsidian.content_values import content_sha
from brz2obsidian.contracts import (
    ContentIdentity,
    ImportLinkConnection,
    ImportLinkImpact,
    InlineExactContent,
    MigrationRefused,
)
from brz2obsidian.core.import_placement import validate_import_location
from brz2obsidian.obsidian.import_links import (
    import_links_depend_on,
    inspect_import_links,
)

from .git_payload import verify_blobs
from .vault_admission import _safe_relative, _walk
from .vault_history import _Git, collection_baselines
from .vault_native import available_memory, observe_file, verify_directory


def read_rendered_collection(root, record_path):
    directory, _, name = record_path.rpartition("/")
    if name != "migration-record.json" or not _safe_relative(record_path):
        raise ValueError("Invalid collection record path")
    available = available_memory() // 4
    payload = {}
    for parent, _, filenames in _walk(root):
        for name in filenames:
            path = Path(parent) / name
            relative = path.relative_to(root).as_posix()
            if (
                not _safe_relative(relative)
                or directory
                and not relative.startswith(directory + "/")
            ):
                raise ValueError("Rendered output is outside the import scope")
            info, _, raw, _ = observe_file(root, path, prefix_limit=available + 1)
            if info.st_size > available or info.st_size != len(raw):
                raise OSError("Rendered collection exceeds the review resources")
            payload[relative] = raw
            available -= len(raw)
    return payload


def _name_key(name):
    return unicodedata.normalize("NFC", name).casefold()


def _physical_children(directory):
    verify_directory(directory)
    children = {}
    for entry in directory.iterdir():
        children.setdefault(_name_key(entry.name), []).append(entry)
    return children


def location_conflict(root, location, *, directories=None):
    directories = {} if directories is None else directories
    directory = root
    for part in location.split("/"):
        if directory not in directories:
            directories[directory] = _physical_children(directory)
        matches = directories[directory].get(_name_key(part), ())
        if not matches:
            return False
        if len(matches) != 1 or matches[0].name != part:
            return True
        directory = matches[0]
        if not directory.is_dir():
            return True
    verify_directory(directory)
    return False


def existing_files(admission):
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


def _retained_record(git, manifest):
    path = manifest.collection_record_path or "migration-record.json"
    file = next(row for row in manifest.source if row.path == path)
    if file.size > available_memory() // 4:
        raise OSError("Active collection source record exceeds observation budget")
    sink = io.BytesIO()
    verify_blobs(
        [*git.prefix, "cat-file", "--batch"],
        env=git.env,
        objects=((file.object_id, file.size, file.sha256, sink),),
        timeout=120,
    )
    return json.loads(sink.getvalue())


def uncreated_destinations(admission, checkpoint, *, git=None):
    reserved, gaps = set(), set()
    if checkpoint is not None and checkpoint.status == "valid":
        git = git if git is not None else _Git(admission.vault)
        for selected in collection_baselines(checkpoint).values():
            if selected is None:
                continue
            _, manifest = selected
            record = _retained_record(git, manifest)
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


def _rendered_parents(incoming):
    return {path.rsplit("/", 1)[0] for path in incoming}


def observe_collection_placement(
    admission, checkpoint, incoming, record_path, *, connections, git=None
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
    root = Path(admission.vault)
    directories = {}
    if any(
        location_conflict(root, parent, directories=directories)
        for parent in _rendered_parents(incoming)
    ):
        return ImportLinkImpact(blockers=("import_target_occupied",))
    existing = existing_files(admission)
    reserved, gaps = uncreated_destinations(admission, checkpoint, git=git)
    if collection_connection_choices(source_record) != connections:
        return ImportLinkImpact(blockers=("import_connection_approval_missing",))
    return inspect_import_links(
        existing,
        incoming,
        reserved_paths=reserved,
        gap_paths=gaps,
        connections=connections,
    )


def passive_import_targets(admission, impact):
    """Bind preserved Git-ignored targets without keeping their file contents."""
    exact = {
        (row.after.path, row.after.target_version)
        for row in impact.observations
        if row.before == row.after
        and row.after.status in ("resolved", "fragment_missing", "fragment_ambiguous")
    }
    alternatives = {
        path
        for row in impact.observations
        if row.before == row.after and row.after.status == "ambiguous"
        for path in row.after.candidates
    }
    return tuple(
        sorted(
            (row.path, row.sha256)
            for row in admission.inventory
            if row.exclusion == "git_ignore"
            and ((row.path, row.sha256) in exact or row.path in alternatives)
        )
    )


def reviewed_connections(review):
    context = review.producer_facts.link_context
    return context.import_link_connections if context is not None else ()


def collection_write_refusal(
    admission,
    checkpoint,
    source,
    record_path,
    review,
    *,
    choices,
    git=None,
    selected=None,
):
    if record_path is None or reviewed_connections(review) != choices:
        return "import_connection_approval_missing"
    incoming = read_rendered_collection(source, record_path)
    if selected is not None and (
        selected.remove_paths
        or {row.path: content_sha(row.content) for row in selected.files}
        != {path: sha256(raw).hexdigest() for path, raw in incoming.items()}
    ):
        return "import_selected_payload_changed"
    impact = observe_collection_placement(
        admission,
        checkpoint,
        incoming,
        record_path,
        connections=choices,
        git=git,
    )
    if not impact.safe:
        return impact.blockers[0]
    context = review.producer_facts.link_context
    if context is not None and context.import_passive_targets != passive_import_targets(
        admission, impact
    ):
        return "import_link_meanings_changed"
    if context is not None and context.import_unrelated_documents:
        observed = {
            (row.path, row.sha256)
            for row in admission.inventory
            if row.path in impact.warnings
        }
        if not set(context.import_unrelated_documents) <= observed:
            return "import_link_meanings_changed"
    return None


def prove_ignored_reversal_documents(admission, affected_paths, selected):
    """Keep unmodified ignored notes outside retention after checking their inbound links."""
    ignored = {
        row.path
        for row in admission.inventory
        if row.exclusion == "git_ignore"
        and row.path.casefold().endswith(".md")
        and row.path not in affected_paths
    }
    if ignored and import_links_depend_on(
        existing_files(admission), ignored, set(affected_paths) | set(selected)
    ):
        raise OSError("Ignored authored note depends on a recovery output")
    return ignored


class ImportRecoveryLinkChange(ValueError):
    """The journal's remaining import effects need a new link review."""


def require_collection_finish_links(
    admission,
    checkpoint,
    record_path,
    original,
    selected,
    removals=(),
    *,
    produced=None,
):
    if original.facts.format_operation.kind != "collection_import":
        return
    digests = {row.path: row.sha256 for row in admission.inventory}
    remaining = {
        path: content
        for path, content in selected.items()
        if digests.get(path) != content_sha(content)
    }
    if not remaining and not removals:
        return
    if record_path is None or removals:
        raise ImportRecoveryLinkChange("recovery_import_scope_changed")
    scope = record_path.rsplit("/", 1)[0] + "/"
    if any(
        not _safe_relative(path) or not path.startswith(scope) for path in remaining
    ):
        raise ImportRecoveryLinkChange("recovery_import_scope_changed")
    root = Path(admission.vault)
    directories = {}
    if any(
        location_conflict(root, parent, directories=directories)
        for parent in _rendered_parents(remaining)
    ):
        raise ImportRecoveryLinkChange("recovery_import_target_occupied")
    if any(
        path.casefold().endswith((".md", ".base"))
        and not isinstance(content, InlineExactContent)
        for path, content in remaining.items()
    ):
        raise ImportRecoveryLinkChange("recovery_import_link_evidence_unavailable")
    proposed = {
        path: content.data
        if path.casefold().endswith((".md", ".base"))
        else content.identity
        for path, content in remaining.items()
    }
    existing = existing_files(admission)
    unchanged_generated = {
        path
        for path, content in (selected if produced is None else produced).items()
        if digests.get(path) == content_sha(content) and path.startswith(scope)
    }
    reserved, gaps = uncreated_destinations(admission, checkpoint)
    choices = tuple(
        row
        for row in reviewed_connections(original)
        if row.target_path in proposed and row.target_path not in existing
    )
    impact = inspect_import_links(
        existing,
        proposed,
        reserved_paths=reserved,
        gap_paths=gaps,
        connections=choices,
        continuation=True,
        unchanged_generated=unchanged_generated,
    )
    if not impact.safe:
        raise ImportRecoveryLinkChange("recovery_import_link_changes")
