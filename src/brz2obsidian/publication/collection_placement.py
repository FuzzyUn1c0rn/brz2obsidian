"""Qualify scoped import paths and link choices against a native vault observation."""

import io
import json
import unicodedata
from hashlib import sha256
from pathlib import Path

from brz2obsidian.application.update_facts import classification_view_paths, record
from brz2obsidian.application.update_lifecycle import _read_physical
from brz2obsidian.content_values import content_sha, content_size
from brz2obsidian.contracts import (
    ContentIdentity,
    ImportCategoryChoice,
    ImportLinkConnection,
    ImportLinkImpact,
    InlineExactContent,
    MigrationRefused,
)
from brz2obsidian.core.import_placement import validate_import_location
from brz2obsidian.obsidian.import_classification import (
    qualify_category_targets,
    vault_classifications,
)
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


def retained_nonmember_paths(admission, checkpoint):
    if checkpoint is None or checkpoint.status != "valid":
        return ()
    git = _Git(admission.vault)
    inventory = {row.path: row.sha256 for row in admission.inventory}
    paths = set()
    for selected in collection_baselines(checkpoint).values():
        if selected is None:
            continue
        _, manifest = selected
        record = _retained_record(git, manifest)
        support = (
            row["relative_path"]
            for row in record.get("support_artifacts", ())
            if row["purpose"] in ("template", "starter")
        )
        assets = (row["relative_path"] for row in record.get("asset_targets", ()))
        candidates = {
            path for path in (*support, *assets) if path and path.endswith(".md")
        }
        paths.update(
            row.path
            for row in manifest.source
            if row.path in candidates and inventory.get(row.path) == row.sha256
        )
    return tuple(sorted(paths))


def collection_connection_choices(record):
    return tuple(
        ImportLinkConnection.model_validate(row)
        for row in record.get("import_link_connections", ())
    )


def recorded_classification_choices(record):
    categories = tuple(
        ImportCategoryChoice.model_validate_json(json.dumps(row["destination"]))
        for row in record.get("category_mappings", ())
        if row.get("destination") is not None
    )
    reused = tuple(
        (row["source_identity"], row["vault_tag"])
        for row in record.get("vault_tag_mappings", ())
        if row["mode"] == "reuse"
    )
    return categories, reused


def classification_approval(record):
    categories = record.get("category_mappings", ())
    tags = record.get("vault_tag_mappings", ())
    if not categories and not tags:
        return None
    material = json.dumps((categories, tags), sort_keys=True, ensure_ascii=False)
    return sha256(material.encode()).hexdigest()


def observe_classification_inventory(admission, checkpoint, *, existing=None):
    collections = (
        collection_baselines(checkpoint)
        if checkpoint is not None and checkpoint.status == "valid"
        else ()
    )
    return vault_classifications(
        existing_files(admission) if existing is None else existing,
        excluded={row.path for row in admission.inventory if row.excluded},
        collections=collections,
    )


def classification_target_status(admission, checkpoint, choices, *, existing=None):
    categories, tags = observe_classification_inventory(
        admission, checkpoint, existing=existing
    )
    try:
        qualify_category_targets(choices, categories)
    except MigrationRefused as error:
        return error.issues[0].code, tags
    return None, tags


def remembered_tag_mappings(record):
    return tuple(
        (row["source_identity"], row["vault_tag"], row["mode"])
        for row in record.get("vault_tag_mappings", ())
    )


def classification_policy(record):
    categories, _ = recorded_classification_choices(record)
    return (
        {
            row.source_identity: (
                row.destination_identity or row.destination_path,
                row.compatible_view,
            )
            for row in categories
        },
        {
            source: (token, mode)
            for source, token, mode in remembered_tag_mappings(record)
        },
    )


def classification_policy_changed(original, incoming):
    live_source_ids = {
        row["original_identity"] for row in incoming.get("item_targets", ())
    }
    return any(
        old[key] != new.get(key)
        for old, new in zip(
            classification_policy(original),
            classification_policy(incoming),
            strict=True,
        )
        for key in old.keys() & live_source_ids
    )


def _new_default_tags(original, incoming, sources):
    retained = set(remembered_tag_mappings(original))
    return {
        _name_key(token)
        for source, token, mode in remembered_tag_mappings(incoming)
        if mode == "new"
        and (source, token, mode) not in retained
        and (sources is None or ("tag", source) in sources)
    }


def classification_transition_refusal(
    admission,
    checkpoint,
    original,
    incoming,
    approval,
    *,
    remap,
    sources=None,
    existing=None,
):
    changed = classification_policy_changed(original, incoming)
    if changed and not remap:
        return "classification_remap_required"
    if remap and not changed:
        return "classification_remap_no_change"
    if (
        remap
        and original["source_identity"]["snapshot_digest"]
        != incoming["source_identity"]["snapshot_digest"]
    ):
        return "classification_remap_source_changed"
    if approval != classification_approval(incoming):
        return "import_classification_approval_missing"
    choices, reused = recorded_classification_choices(incoming)
    if sources is not None:
        choices = tuple(
            row for row in choices if ("category", row.source_identity) in sources
        )
        reused = tuple(row for row in reused if ("tag", row[0]) in sources)
    new_defaults = _new_default_tags(original, incoming, sources)
    if not choices and not reused and not new_defaults:
        return None
    refusal, tags = classification_target_status(
        admission, checkpoint, choices, existing=existing
    )
    if refusal is not None:
        return refusal
    if new_defaults.intersection(_name_key(token) for token in tags):
        return "import_tag_namespace_changed"
    known = set(recorded_classification_choices(original)[1])
    if any(row not in known and row[1] not in tags for row in reused):
        return "import_tag_reuse_unavailable"
    return None


def scoped_update_classification_refusal(
    admission, checkpoint, source, record_path, review, *, git=None
):
    if not record_path or "/" not in record_path:
        return None
    if not _safe_relative(record_path):
        return "collection_scope_changed"
    root = Path(source)
    budget = available_memory() // 4
    info, _, raw, _ = observe_file(root, root / record_path, prefix_limit=budget + 1)
    if info.st_size > budget or len(raw) != info.st_size:
        raise OSError("Scoped migration record exceeds the review resources")
    incoming = json.loads(raw)
    observed = incoming["source_identity"]
    baseline = collection_baselines(checkpoint).get(
        (observed["module_id"], observed["source_id"])
    )
    if baseline is None or baseline[1].collection_record_path != record_path:
        return "collection_not_active"
    original = _retained_record(git or _Git(admission.vault), baseline[1])
    context = review.producer_facts.link_context
    removals = {
        row.path
        for row in review.proposal.changes
        if row.provenance.rule == "classification_view_retired"
    }
    if removals and (
        context is None
        or not context.import_classification_remap
        or removals
        - (classification_view_paths(original) - classification_view_paths(incoming))
    ):
        return "classification_view_scope_changed"
    return classification_transition_refusal(
        admission,
        checkpoint,
        original,
        incoming,
        context.import_classification_approval if context is not None else None,
        remap=context is not None and context.import_classification_remap,
    )


def classification_write_refusal(
    admission, checkpoint, record, approval, *, existing=None
):
    if classification_approval(record) != approval:
        return "import_classification_approval_missing"
    if approval is None:
        return None
    choices, reused = recorded_classification_choices(record)
    if len(choices) != len(record["category_mappings"]):
        return "import_classification_approval_missing"
    refusal, tags = classification_target_status(
        admission, checkpoint, choices, existing=existing
    )
    if refusal is not None:
        return refusal
    if any(token not in tags for _, token in reused):
        return "import_tag_reuse_unavailable"
    occupied = {_name_key(token.partition("/")[0]) for token in tags}
    if any(
        row["mode"] == "new"
        and _name_key(row["vault_tag"].partition("/")[0]) in occupied
        for row in record["vault_tag_mappings"]
    ):
        return "import_tag_namespace_changed"
    return None


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
        and row.after.status
        in ("resolved", "fragment_missing", "fragment_ambiguous", "unknown")
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
    refusal = classification_write_refusal(
        admission,
        checkpoint,
        json.loads(incoming[record_path]),
        context.import_classification_approval if context is not None else None,
    )
    if refusal is not None:
        return refusal
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


def _qualify_recovery_classifications(
    admission,
    checkpoint,
    record_path,
    original,
    produced,
    existing,
    published,
):
    context = original.producer_facts.link_context
    approval = context.import_classification_approval if context is not None else None
    if approval is None:
        return
    record = produced.get(record_path)
    if not isinstance(record, InlineExactContent):
        raise ImportRecoveryLinkChange("recovery_import_classifications_unavailable")
    refusal = classification_write_refusal(
        admission,
        checkpoint,
        json.loads(record.data),
        approval,
        existing={
            path: value for path, value in existing.items() if path not in published
        },
    )
    if refusal is not None:
        raise ImportRecoveryLinkChange("recovery_import_classifications_changed")


def _record_matches(content, row):
    return (
        isinstance(content, InlineExactContent)
        and row is not None
        and (content_size(content), content_sha(content)) == (row.size, row.sha256)
    )


def _classifications_for_record(before, incoming):
    for kind, field in (
        ("category", "category_mappings"),
        ("tag", "vault_tag_mappings"),
    ):
        old = {row["source_identity"]: row for row in before.get(field, ())}
        for row in incoming.get(field, ()):
            source = row["source_identity"]
            if old.get(source) != row:
                yield kind, source


def _classifications_for_paths(facts, before, incoming, paths):
    selected = set()
    for subject in facts.subjects:
        if subject.structure is None or paths.isdisjoint(
            (subject.path, subject.current.path)
        ):
            continue
        structure = subject.structure
        for reason in (*structure.prior_mappings, *structure.incoming_mappings):
            _, _, source = reason.classification_id.partition(":")
            selected.add((reason.kind, source))
    for value in (before, incoming):
        overview = {
            row["relative_path"]
            for row in value.get("support_artifacts", ())
            if row["purpose"] == "overview"
        }
        used = {
            row["definition_key"] for row in value.get("classification_assignments", ())
        }
        category_items = {
            row["original_identity"]
            for row in value["item_targets"]
            if row.get("item_key") in used
        }
        for row in value.get("category_mappings", ()):
            if not paths.isdisjoint(
                (row.get("source_reference"), *row.get("view_paths", ()))
            ) or (
                not paths.isdisjoint(overview)
                and row["source_identity"] in category_items
            ):
                selected.add(("category", row["source_identity"]))
    return selected


def _archived_member_sources(incoming, members):
    items = {
        row.get("item_key"): row["original_identity"]
        for row in incoming["item_targets"]
    }
    owned = {
        row["item_key"]: row["relative_path"]
        for row in incoming["item_targets"]
        if row.get("created") is True
        and members.get(row["original_identity"]) == row.get("relative_path")
    }
    for row in incoming.get("classification_assignments", ()):
        source = items.get(row["definition_key"])
        if (
            source is not None
            and row["item_key"] in owned
            and owned[row["item_key"]] == row["item_target"]
        ):
            yield "category", source
    for row in incoming.get("tag_memberships", ()):
        source = items.get(row["tag_key"])
        if (
            source is not None
            and source == row["tag_original_identity"]
            and row["native"]
            and row["item_key"] in owned
            and owned[row["item_key"]] == row["item_target"]
        ):
            yield "tag", source


def _new_member_sources(facts, incoming, remaining, before_rows, proposed_rows):
    members = {
        subject.item_id: subject.path
        for subject in facts.subjects
        if subject.path in remaining
        and subject.path not in before_rows
        and subject.structure is None
        and subject.output_role == "note"
        and subject.facet == "content"
        and subject.current.existence == "absent"
        and _record_matches(subject.incoming, proposed_rows.get(subject.path))
        and _record_matches(remaining[subject.path], proposed_rows.get(subject.path))
    }
    return _archived_member_sources(incoming, members) if members else ()


def _require_classified_update_finish(
    admission,
    checkpoint,
    record_path,
    original,
    origin,
    produced,
    remaining,
    removals,
    digests,
):
    facts = original.producer_facts
    context = facts.link_context
    if context is None or context.import_classification_approval is None:
        return
    if record_path is None or not _safe_relative(record_path):
        raise ImportRecoveryLinkChange("recovery_import_classifications_unavailable")
    pending = set(remaining) | set(removals).intersection(digests)
    paths = pending.intersection(origin.affected_paths)
    if not paths:
        return
    before_rows = {row.path: row for row in origin.before}
    proposed_rows = {row.path: row for row in origin.proposed}
    predecessor = next(
        (row.baseline.content for row in facts.subjects if row.path == record_path),
        None,
    )
    successor = produced.get(record_path)
    if not (
        _record_matches(predecessor, before_rows.get(record_path))
        and _record_matches(successor, proposed_rows.get(record_path))
    ):
        raise ImportRecoveryLinkChange("recovery_import_classifications_unavailable")
    before, incoming = (
        record({record_path: data}, record_path) for data in (predecessor, successor)
    )
    sources = _classifications_for_paths(facts, before, incoming, paths)
    sources.update(
        _new_member_sources(facts, incoming, remaining, before_rows, proposed_rows)
    )
    if record_path in paths:
        sources.update(_classifications_for_record(before, incoming))
    if not sources:
        return
    published = {
        path
        for path in origin.affected_paths
        if path in proposed_rows and digests.get(path) == proposed_rows[path].sha256
    }
    refusal = classification_transition_refusal(
        admission,
        checkpoint,
        before,
        incoming,
        context.import_classification_approval,
        remap=context.import_classification_remap,
        sources=sources,
        existing={
            path: value
            for path, value in existing_files(admission).items()
            if path not in published
        },
    )
    if refusal is not None:
        raise ImportRecoveryLinkChange("recovery_import_classifications_changed")


def require_collection_finish_links(
    admission,
    checkpoint,
    record_path,
    original,
    selected,
    removals=(),
    *,
    produced=None,
    origin,
):
    kind = original.facts.format_operation.kind
    if origin.kind != "apply" or kind not in ("collection_import", "source_update"):
        return
    digests = {row.path: row.sha256 for row in admission.inventory}
    remaining = {
        path: content
        for path, content in selected.items()
        if digests.get(path) != content_sha(content)
    }
    if not remaining and not removals:
        return
    if kind == "source_update":
        _require_classified_update_finish(
            admission,
            checkpoint,
            record_path,
            original,
            origin,
            selected if produced is None else produced,
            remaining,
            removals,
            digests,
        )
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
    _qualify_recovery_classifications(
        admission,
        checkpoint,
        record_path,
        original,
        selected if produced is None else produced,
        existing,
        unchanged_generated,
    )
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
