"""Interpret exact owned source payload and a complete current inventory."""

import hashlib
import json
import unicodedata
from collections import defaultdict
from pathlib import PurePosixPath
from types import SimpleNamespace

from brz2obsidian.content_values import same_content
from brz2obsidian.contracts import (
    QUALIFIED_OUTPUT_FORMATS,
    AttachmentDestination,
    AttachmentFacts,
    ClassificationMapping,
    ContentVersion,
    CurrentContent,
    ExactContent,
    FormatBaselineOutput,
    FormatOperation,
    IdentityInventoryItem,
    IdentityTargetFacts,
    ImportedItemIdentity,
    InlineExactContent,
    LinkContext,
    MovedNavigationReference,
    OpaqueContent,
    OutputIdentity,
    ReconciliationInput,
    ReconciliationSubject,
    ReferenceTarget,
    SafetyFact,
    SupportedFormatBaseline,
)
from brz2obsidian.core.text_candidates import moved_navigation_valid
from brz2obsidian.obsidian import (
    align_structure,
    inspect_text_candidate,
    interpret_link_target,
    interpret_links,
    interpret_structure,
)
from brz2obsidian.obsidian.sections import retained_relationship_survives
from brz2obsidian.obsidian_dialect import (
    category,
    classification_view_paths,
    native_properties,
    read_migration_record,
)


def digest(value):
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def target(path):
    return IdentityTargetFacts(
        normalized_path=unicodedata.normalize(
            "NFC", unicodedata.normalize("NFC", path).casefold()
        ),
        containment="contained",
        status="safe",
    )


def record(payload, record_path="migration-record.json"):
    return read_migration_record(payload[record_path])


def output_identity(value):
    source = value["source_identity"]
    return OutputIdentity(
        collection_id=source["source_id"],
        module_id=source["module_id"],
        module_version=source["module_version"],
        profile_id=value["profile_id"],
        profile_version=value["profile_version"],
        output_format=value["schema_version"],
        settings_digest=hashlib.sha256(b"{}").hexdigest(),
    )


def _outputs(value, payload):
    result = {}
    for row in value["item_targets"]:
        if row["created"]:
            result[(row["original_identity"], "content")] = (
                row["relative_path"],
                "note",
                row["original_title"],
            )
    for row in value["asset_targets"]:
        if row["relative_path"] is not None and row["relative_path"] in payload:
            result[(row["asset_id"], "asset")] = (
                row["relative_path"],
                "guide",
                row["relative_path"],
            )
    known = {row[0] for row in result.values()}
    for path in payload:
        if path not in known:
            result[("support:" + path, "content")] = (
                path,
                "configuration" if path.startswith(".obsidian/") else "guide",
                path,
            )
    return result


def _identity(identity, item):
    return ImportedItemIdentity(
        collection_id=identity.collection_id,
        module_id=identity.module_id,
        item_id=item,
    )


def _representations(path, kind):
    if kind != "category":
        return (path,)
    names = (path, str(PurePosixPath(path).with_suffix("")), PurePosixPath(path).stem)
    return (path,) + tuple("[[" + name + "]]" for name in dict.fromkeys(names))


def _shared_membership_target(claim, path, inventory):
    identity = None
    if claim is not None:
        module, collection, item = claim
        identity = ImportedItemIdentity(
            module_id=module, collection_id=collection, item_id=item
        )
    observed = [
        row.current.path
        for row in inventory
        if identity is not None and row.identity == identity and row.facet == "content"
    ]
    if len(observed) == 1:
        path = observed[0]
    return ReferenceTarget(
        schema_id="brz2obsidian.reference-target",
        schema_version=1,
        target_id="shared-category:" + digest(claim if claim is not None else path),
        kind="category",
        canonical_path=path,
        identity=identity,
        target=target(path),
        representations=_representations(path, "category"),
        validation_fingerprint=digest(("shared category", claim, path)),
        status="unknown" if len(observed) > 1 else "safe",
        category_anchor="observed_path" if identity is None else "scoped_identity",
    )


def _membership_targets(records, inventory=(), *, scoped_record=False):
    rows, tokens, shared = {}, {}, {}
    scoped_mappings = any(
        value.get("category_mappings") or value.get("vault_tag_mappings")
        for value in records
    )
    identity = output_identity(records[-1])
    for value in records:
        external = {
            row["source_identity"]: row["destination"]
            for row in value.get("category_mappings", ())
            if row.get("destination") and row["destination"].get("destination_path")
        }
        for row in value["item_targets"]:
            item = row["original_identity"]
            if "definition" in row.get("creation_reasons", ()) and item not in external:
                rows[item] = row
            if row.get("vault_tag_token"):
                tokens[item] = row["vault_tag_token"]
        for choice in external.values():
            claim = choice.get("destination_identity")
            path = choice["destination_path"]
            key = tuple(claim) if claim is not None else (None, path)
            shared[key] = (claim, path)
    result = [
        _shared_membership_target(claim, path, inventory)
        for claim, path in shared.values()
    ]
    for item, row in sorted(rows.items()):
        claim = _identity(identity, item)
        observed = [
            entry
            for entry in inventory
            if entry.identity == claim and entry.facet == "content"
        ]
        path = observed[0].current.path if len(observed) == 1 else row["relative_path"]
        result.append(
            ReferenceTarget(
                schema_id="brz2obsidian.reference-target",
                schema_version=1,
                target_id="subject:" + item + ":content",
                kind="category",
                canonical_path=path,
                identity=claim,
                target=target(path),
                representations=_representations(path, "category"),
                validation_fingerprint=digest((claim.model_dump(), path, "category")),
                status="unknown" if len(observed) > 1 else "safe",
                category_anchor="scoped_identity" if scoped_record else None,
            )
        )
    if scoped_mappings:
        result.extend(_manual_category_targets(inventory, result))
    result.extend(_tag_membership_targets(tokens, identity, scoped_mappings, inventory))
    # Current templates carry the reserved role even when this source has no
    # definitions. Keep recorded7 target registries deterministic for replay.
    # The shared role identity remains stable across the qualified7/8 grammar.
    if rows or identity.output_format in QUALIFIED_OUTPUT_FORMATS:
        result.append(
            ReferenceTarget(
                schema_id="brz2obsidian.reference-target",
                schema_version=1,
                target_id="format:7:categories",
                kind="tag",
                canonical_path=None,
                identity=None,
                target=None,
                representations=("categories",),
                validation_fingerprint=digest((7, "categories")),
                status="safe",
            )
        )
    return tuple(result)


def _manual_category_targets(inventory, recorded):
    occupied = {row.canonical_path for row in recorded}
    for item in inventory:
        path = item.current.path
        if path in occupied or not path.casefold().endswith(".md"):
            continue
        properties = native_properties(item.current.content)
        if properties is not None and category(properties, path, scoped=True):
            identity = item.identity if item.identity_state == "valid" else None
            claim = (
                (identity.module_id, identity.collection_id, identity.item_id)
                if identity is not None
                else None
            )
            yield _shared_membership_target(claim, path, inventory)


def _tag_membership_targets(tokens, identity, scoped_mappings, inventory):
    result = []
    tag_groups = {}
    for item, token in sorted(tokens.items()):
        key = (
            unicodedata.normalize("NFC", token).casefold() if scoped_mappings else item
        )
        tag_groups.setdefault(key, set()).add(token)
    if scoped_mappings:
        for row in inventory:
            properties = native_properties(row.current.content)
            observed = (properties or {}).get("tags", ())
            if isinstance(observed, list):
                for token in observed:
                    if isinstance(token, str):
                        key = unicodedata.normalize("NFC", token).casefold()
                        tag_groups.setdefault(key, set()).add(token)
    for key, values in tag_groups.items():
        if scoped_mappings and key == "categories":
            continue
        aliases = tuple(sorted(values))
        result.append(
            ReferenceTarget(
                schema_id="brz2obsidian.reference-target",
                schema_version=1,
                target_id=(
                    "vault-tag:" + key
                    if scoped_mappings
                    else f"tag:{identity.module_id}:{identity.collection_id}:{key}"
                ),
                kind="tag",
                canonical_path=None,
                identity=None,
                target=None,
                representations=aliases,
                validation_fingerprint=digest(
                    (
                        identity.collection_id,
                        key,
                        aliases[0] if not scoped_mappings else aliases,
                    )
                ),
                status="safe",
            )
        )
    return tuple(result)


def link_state(
    content,
    *,
    target_id,
    existence,
    memberships=None,
    membership_targets=(),
    source_path=None,
    output_format=7,
    qualify_roles=False,
    _owner=None,
):
    if _owner is not None:
        return _owner._assembly_link_state(
            content,
            target_id=target_id,
            existence=existence,
            memberships=memberships,
            membership_targets=membership_targets,
            source_path=source_path,
            output_format=output_format,
            qualify_roles=qualify_roles,
        )
    document = (
        interpret_structure(
            content, output_format=output_format, membership_targets=membership_targets
        )
        if content is not None
        else None
    )
    if memberships is None:
        memberships = (
            tuple(
                entry.target_id
                for group in document.memberships
                for entry in group.entries
            )
            if document is not None
            else ()
        )
    return interpret_link_target(
        content,
        target_id=target_id,
        existence=existence,
        memberships=memberships,
        membership_targets=membership_targets,
        source_path=source_path,
        output_format=output_format,
        qualify_roles=qualify_roles,
    )


def _observed_identity(path, content, identity, established, *, native_metadata=False):
    if path in established and established[path][1] != "note":
        return "valid", _identity(identity, established[path][0]), established[path][2]
    if not path.lower().endswith(".md"):
        return "missing", None, None
    if identity.output_format in QUALIFIED_OUTPUT_FORMATS or native_metadata:
        properties = native_properties(content)
        names = ("source_collection_id", "source_item_id")
        if properties is not None and all(
            isinstance(properties.get(name), str) and properties[name] for name in names
        ):
            return (
                "valid",
                ImportedItemIdentity(
                    collection_id=properties[names[0]],
                    module_id=identity.module_id,
                    item_id=properties[names[1]],
                ),
                "content",
            )
        return (
            "malformed"
            if properties is None or any(name in properties for name in names)
            else "missing",
            None,
            "content",
        )
    read_format = 7 if identity.output_format == 6 else identity.output_format
    document = interpret_structure(content, output_format=read_format)
    fields = {
        field.identity_component: field.value
        for field in document.fields
        if field.kind == "identity"
    }
    if fields.get("collection") and fields.get("item"):
        return (
            "valid",
            ImportedItemIdentity(
                collection_id=fields["collection"],
                module_id=identity.module_id,
                item_id=fields["item"],
            ),
            "content",
        )
    state = (
        "malformed"
        if any("identity" in issue for issue in document.issues)
        else "missing"
    )
    return state, None, "content"


def _bind_retained_asset_outputs(old, new, historical, identity, retained_ownership):
    ownership = {}
    paths = set()
    for proof in retained_ownership:
        key = proof.identity.item_id, proof.facet
        if (
            (proof.identity.collection_id, proof.identity.module_id)
            != (identity.collection_id, identity.module_id)
            or proof.facet != "asset"
            or key in ownership
            or proof.source_path in paths
        ):
            raise ValueError("Retained asset identity is ambiguous")
        ownership[key] = proof
        paths.add(proof.source_path)
        historical[key] = proof.source_path, "guide", proof.source_path
    old = {
        key: value
        for key, value in old.items()
        if key[1] != "asset" or key in ownership
    }
    new = {
        key: value
        for key, value in new.items()
        if key[1] != "asset" or key in ownership
    }
    if any(
        key in old and old[key][0] != value[0] or key in new and new[key][0] != value[0]
        for key, value in historical.items()
        if key[1] == "asset"
    ):
        raise ValueError("Retained asset moved without current identity proof")
    return old, new, ownership


def _established_output_paths(old, historical):
    established = {
        path: (item, role, facet) for (item, facet), (path, role, _) in old.items()
    }
    for (item, facet), (path, role, _) in historical.items():
        if facet != "asset":
            continue
        if path in established and established[path] != (item, role, facet):
            raise ValueError("Retained asset path has a different association")
        established[path] = item, role, facet
    return established


def _observed_identity_inventory(
    current,
    content,
    established,
    old_identity,
    identity,
    *,
    import_outputs=None,
    current_inventory=(),
):
    inventory = []
    for path, raw in sorted(current.items()):
        current_content = content(
            raw, semantic=established.get(path, (None, None, None))[2] != "asset"
        )
        state, claim, facet = _observed_identity(
            path,
            current_content,
            old_identity,
            established,
            native_metadata=identity.output_format in QUALIFIED_OUTPUT_FORMATS,
        )
        inventory.append(
            IdentityInventoryItem(
                entry_id="file:" + path,
                facet=facet,
                identity_state=state,
                identity=claim,
                raw_identity=None,
                title=PurePosixPath(path).stem,
                current=CurrentContent(
                    existence="present", path=path, content=current_content
                ),
                target=target(path),
            )
        )
    if import_outputs is not None:
        _validate_import_destinations(
            identity, import_outputs, current, current_inventory, inventory
        )
    return inventory


def _interpret_subject_structure(
    facet, versions, membership_views, output_formats, *, mapping_evidence
):
    structure = None
    interpretation = "opaque" if facet == "asset" else "supported"
    if facet != "asset" and all(content is not None for content in versions):
        documents = tuple(
            interpret_structure(
                content, output_format=version, membership_targets=targets
            )
            for content, targets, version in zip(
                versions,
                membership_views,
                output_formats,
                strict=True,
            )
        )
        structure = align_structure(*documents, **mapping_evidence)
        if any(d.status != "supported" for d in documents):
            interpretation = "unsupported"
    return structure, interpretation


def _note_reservations(old, baseline, records, retired_note_ids):
    old_reserved, new_reserved = (
        {
            (row["original_identity"], "content"): row["relative_path"]
            for row in value["item_targets"]
            if not row["created"]
        }
        for value in records
    )
    retired = set()
    historical = {}
    retired.update(retired_note_ids)
    retired.update(
        key[0] for key in old.keys() & new_reserved.keys() if old[key][0] in baseline
    )
    historical.update(
        (key, (path, "note", PurePosixPath(path).stem))
        for key, path in new_reserved.items()
        if key[0] in retired and key not in old
    )
    return old_reserved, new_reserved, retired, historical


def _classification_mappings(record, targets):
    paths = {
        row.canonical_path: row.target_id for row in targets if row.kind == "category"
    }
    tokens = {
        token: row.target_id
        for row in targets
        if row.kind == "tag"
        for token in row.representations
    }
    rows = []
    for item in record.get("category_mappings", ()):
        choice = item.get("destination") or {}
        path = choice.get("destination_path") or item["source_reference"]
        if path in paths:
            rows.append(("category", item["source_identity"], paths[path], path))
    for item in record.get("vault_tag_mappings", ()):
        token = item["vault_tag"]
        if token in tokens:
            rows.append(("tag", item["source_identity"], tokens[token], token))
    by_classification = {
        (kind, source): ClassificationMapping(
            schema_id="brz2obsidian.classification-mapping",
            schema_version=1,
            classification_id=f"{kind}:{source}",
            target_id=destination,
            kind=kind,
            source_label=label,
        )
        for kind, source, destination, label in rows
    }
    items = {
        row.get("item_key"): row["original_identity"] for row in record["item_targets"]
    }
    reasons = defaultdict(list)
    for item in record.get("classification_assignments", ()):
        mapping = by_classification.get(("category", items.get(item["definition_key"])))
        if mapping is not None:
            reasons[items.get(item["item_key"])].append(mapping)
    for item in record.get("tag_memberships", ()):
        mapping = by_classification.get(("tag", item.get("tag_original_identity")))
        if mapping is not None:
            reasons[items.get(item["item_key"])].append(mapping)
    return {key: tuple(values) for key, values in reasons.items()}


def _retired_classification_views(old, new, remap):
    if not remap:
        return set()
    return classification_view_paths(old) - classification_view_paths(new)


def _subject_mapping_evidence(item, original, incoming, remap):
    prior, planned = original.get(item, ()), incoming.get(item, ())
    return {
        "prior_mappings": prior,
        "incoming_mappings": planned,
        "classification_mode": ("remap" if remap else "retained")
        if prior or planned
        else None,
    }


def assemble_facts(
    baseline,
    incoming,
    current,
    *,
    proposal_id,
    generation,
    source_memory=(),
    current_inventory=(),
    originals_known=True,
    onboarding=False,
    retained_ownership=None,
    retired_note_ids=(),
    record_path=None,
    classification_remap=False,
    _owner=None,
):
    def content(raw, *, semantic):
        value = (
            raw
            if isinstance(raw, (InlineExactContent, OpaqueContent))
            else ExactContent(data=raw)
        )
        return (
            _owner._assembly_content(value, semantic=semantic)
            if _owner is not None
            else value
        )

    explicit_collection = record_path is not None
    record_path = record_path or "migration-record.json"
    first_import = baseline is None
    new_record = record(incoming, record_path)
    old_record = (
        new_record | {"item_targets": (), "asset_targets": (), "relationships": ()}
        if first_import
        else record(baseline, record_path)
    )
    baseline = baseline or {}
    originals_known = originals_known and not first_import
    old_identity, identity = output_identity(old_record), output_identity(new_record)
    old, new = _outputs(old_record, baseline), _outputs(new_record, incoming)
    retired_views = _retired_classification_views(
        old_record, new_record, classification_remap
    )
    qualified_scope = (
        identity.output_format == 9
        and originals_known
        and (old_identity.collection_id, old_identity.module_id)
        == (identity.collection_id, identity.module_id)
    )
    old_reserved, new_reserved, retired, historical = {}, {}, set(), {}
    if qualified_scope:
        old_reserved, new_reserved, retired, historical = _note_reservations(
            old, baseline, (old_record, new_record), retired_note_ids
        )
    ownership = {}
    if retained_ownership is not None:
        old, new, ownership = _bind_retained_asset_outputs(
            old, new, historical, identity, retained_ownership
        )
    established = _established_output_paths(old, historical)
    inventory = _observed_identity_inventory(
        current,
        content,
        established,
        old_identity,
        identity,
        import_outputs=new if first_import else None,
        current_inventory=current_inventory,
    )
    membership_views = (
        _membership_targets((old_record,)),
        _membership_targets((old_record, new_record), inventory),
        _membership_targets((new_record,)),
    )
    original_mappings = _classification_mappings(old_record, membership_views[0])
    incoming_mappings = _classification_mappings(new_record, membership_views[2])
    subjects, outputs = [], []
    observed_paths = {row.path for row in current_inventory} | set(current)
    for key in sorted(old.keys() | new.keys() | historical.keys()):
        item, facet = key
        path, role, title = new.get(key, old.get(key, historical.get(key)))
        old_path = old.get(key, (path, role, title))[0]
        original = (
            content(baseline[old_path], semantic=facet != "asset")
            if originals_known
            and (
                key in old or identity.output_format != 9 and retained_ownership is None
            )
            and old_path in baseline
            else None
        )
        received = (
            content(incoming[path], semantic=facet != "asset") if key in new else None
        )
        matches = [
            row
            for row in inventory
            if row.identity == _identity(identity, item) and row.facet == facet
        ]
        selected = (
            matches[0].current
            if len(matches) == 1
            else CurrentContent(
                existence="present"
                if old_path in current
                else "unknown"
                if old_path in observed_paths
                else "absent",
                path=old_path,
                content=content(current[old_path], semantic=facet != "asset")
                if old_path in current
                else None,
            )
        )
        if not matches and selected.existence == "absent":
            inventory.append(
                IdentityInventoryItem(
                    entry_id="absent:" + old_path,
                    facet=facet,
                    identity_state="valid",
                    identity=_identity(identity, item),
                    raw_identity=None,
                    title=title,
                    current=selected,
                    target=target(old_path),
                )
            )
        structure, interpretation = _interpret_subject_structure(
            facet,
            (original, selected.content, received),
            membership_views,
            (
                old_identity.output_format,
                old_identity.output_format,
                identity.output_format,
            ),
            mapping_evidence=_subject_mapping_evidence(
                item, original_mappings, incoming_mappings, classification_remap
            ),
        )
        attachment = None
        if facet == "asset" and not first_import:
            slots = ()
            if received is not None:
                parent = PurePosixPath(selected.path)
                suffix = PurePosixPath(path).suffix
                name = (
                    parent.stem
                    + " (incoming-"
                    + received.identity.sha256[:8]
                    + ")"
                    + suffix
                )
                allocation = str(parent.with_name(name))
                slots = (
                    AttachmentDestination(path=allocation, target=target(allocation)),
                )
            attachment = AttachmentFacts(
                current_target_id="subject:" + item + ":" + facet,
                allocation_candidates=slots,
                affected_documents=(),
                retained_ownership=ownership.get(key),
            )
        subjects.append(
            ReconciliationSubject(
                item_id=item,
                facet=facet,
                path=path,
                baseline=ContentVersion(
                    status="known" if original is not None else "unknown",
                    content=original,
                    unavailable_digest=None,
                ),
                current=selected,
                incoming=received,
                interpretation=interpretation,
                title=title,
                source_target=_physical_target(path, selected.path, current_inventory),
                output_role=role,
                structure=structure,
                attachment=attachment,
                classification_view_retirement=path in retired_views
                and item == "support:" + path,
                prior_reservation=received is not None
                and old_reserved.get(key) == path,
                source_still_reserved=received is None and key in new_reserved,
                previously_generated=facet == "content"
                and item in retired
                and (key not in old or key in new_reserved),
            )
        )
        if original is not None:
            outputs.append(
                FormatBaselineOutput(item_id=item, facet=facet, content=original)
            )
    facts = ReconciliationInput(
        schema_id="brz2obsidian.reconciliation-input",
        schema_version=1,
        proposal_id=proposal_id,
        generation=generation,
        baseline_identity=old_identity,
        incoming_identity=identity,
        subjects=tuple(subjects),
        inventory="complete",
        safety_facts=tuple(
            SafetyFact(
                key=kind,
                kind=kind,
                fingerprint=digest((identity.collection_id, identity.module_id, kind)),
                status="safe",
                subjects=(),
            )
            for kind in ("identity", "target", "candidate", "operation")
        ),
        identity_inventory=tuple(inventory),
        source_version_memory=source_memory,
        retired_note_ids=tuple(sorted(retired)),
        format_operation=FormatOperation(
            schema_id="brz2obsidian.format-operation",
            schema_version=1,
            kind=(
                "collection_import"
                if first_import
                else "onboarding"
                if onboarding
                else "source_update"
            ),
            automatic_merge=True,
            recorded_generation="supported" if originals_known else "unknown",
            baseline_source_version=old_record["source_identity"]["snapshot_digest"]
            if originals_known
            else None,
            target_source_version=new_record["source_identity"]["snapshot_digest"],
            established_baseline=SupportedFormatBaseline(
                schema_id="brz2obsidian.supported-format-baseline",
                schema_version=1,
                identity=old_identity,
                source_version=old_record["source_identity"]["snapshot_digest"],
                outputs=tuple(outputs),
            )
            if originals_known
            else None,
        ),
        link_context=None,
    )
    facts = facts.model_copy(
        update={
            "link_context": _link_context(
                facts,
                old_record,
                new_record,
                current_inventory,
                scoped_collection=explicit_collection,
                record_path=record_path,
                classification_remap=classification_remap,
                _owner=_owner,
            )
        }
    )

    if qualified_scope:
        facts = _bind_moved_navigation(facts, old_record, new_record)
    return automatic_merge_facts(facts, _owner=_owner)


class CollectionImportConflict(ValueError):
    """The incoming collection would claim existing authored vault content."""


def _validate_import_destinations(identity, outputs, current, physical, observed):
    if any(
        row.identity_state == "valid"
        and row.identity.collection_id == identity.collection_id
        and row.identity.module_id == identity.module_id
        and (row.identity.item_id, row.facet) in outputs
        for row in observed
    ):
        raise CollectionImportConflict("retained_source_identity_conflict")
    occupied = tuple(
        target(path).normalized_path
        for path in current.keys() | {row.path for row in physical}
    )
    for path, _, _ in outputs.values():
        proposed = target(path).normalized_path
        if any(
            existing == proposed
            or existing.startswith(proposed + "/")
            or proposed.startswith(existing + "/")
            for existing in occupied
        ):
            raise CollectionImportConflict("import_target_occupied")


def _navigation_edges(source_record):
    items = {row["item_key"]: row for row in source_record["item_targets"]}
    for relation in source_record.get("relationships", ()):
        if relation["kind"] not in ("related", "hierarchy"):
            continue
        left, right = (items.get(relation[side]) for side in ("item_a", "item_b"))
        if left is None or right is None:
            continue
        first, second = (
            ("Related", "Related")
            if relation["kind"] == "related"
            else ("Children", "Parents")
        )
        for owner, peer, heading in ((left, right, first), (right, left, second)):
            yield (
                owner["original_identity"],
                peer["original_identity"],
                heading,
                peer["relative_path"],
            )


def _retained_navigation_tokens(facts, subject, links, prior):
    original = subject.baseline.content
    current = subject.current.content
    if original is None or current is None:
        return links
    proven_headings = {
        heading
        for heading in {ref.heading for ref in links.values()}
        if retained_relationship_survives(original.data, current.data, heading)
    }
    if not proven_headings:
        return links
    context = facts.link_context
    document = interpret_links(
        subject.baseline.content,
        document_id=f"subject:{subject.item_id}:{subject.facet}",
        source_path=subject.path,
        path_mode="vault",
        targets=context.current_targets,
        target_facts=context.current_target_facts,
        inventory=context.inventory,
        output_format=9,
    )
    if document.status != "supported":
        return links
    for key, reference in links.items():
        previous_edge = (
            subject.item_id,
            reference.identity.item_id,
            reference.heading,
            reference.source_path,
        )
        if reference.heading not in proven_headings or previous_edge not in prior:
            continue
        original = tuple(
            link.raw
            for link in document.occurrences
            if link.relationship_heading == reference.heading
            and not link.embedded
            and link.query is not None
            and link.query.value == reference.source_path
            and link.meaning.display_text == reference.label
        )
        if len(original) == 1:
            links[key] = reference.model_copy(
                update={
                    "retained_token_sha256": hashlib.sha256(original[0]).hexdigest()
                }
            )
    return links


def _moved_navigation_subjects(facts):
    observed = defaultdict(list)
    for entry in facts.identity_inventory:
        if entry.identity_state == "valid" and entry.facet == "content":
            observed[entry.identity].append(entry.current)
    moved = {}
    for subject in facts.subjects:
        if subject.facet != "content" or subject.incoming is None:
            continue
        identity = _identity(facts.incoming_identity, subject.item_id)
        matches = observed.get(identity, ())
        if (
            len(matches) == 1
            and matches[0].existence == "present"
            and matches[0].path != subject.path
        ):
            moved[subject.item_id] = subject, identity
    return moved


def _generated_navigation_references(subject, document, destinations):
    links = {}
    if document is not None and (
        subject.current.existence == "present" or subject.baseline.status != "known"
    ):
        for occurrence in document.occurrences:
            query = occurrence.query
            if query is None or occurrence.embedded:
                continue
            match = destinations[subject.item_id].get(
                (occurrence.relationship_heading, query.value)
            )
            if match is not None:
                peer, identity = match
                key = (occurrence.relationship_heading, identity.item_id)
                links[key] = MovedNavigationReference(
                    heading=occurrence.relationship_heading,
                    label=occurrence.meaning.display_text,
                    identity=identity,
                    source_path=peer.path,
                    observed_path=peer.current.path,
                )
    return links


def _bind_moved_navigation(facts, old_record, source_record):
    """Bind generated relationship entries independently of vault lookup."""
    moved = _moved_navigation_subjects(facts)
    if not moved:
        return facts

    prior = (
        set(_navigation_edges(old_record))
        if facts.baseline_identity.output_format in QUALIFIED_OUTPUT_FORMATS
        else set()
    )
    destinations = defaultdict(dict)
    for owner, peer, heading, path in _navigation_edges(source_record):
        if peer in moved:
            destinations[owner][heading, path] = moved[peer]
    documents = {
        (d.document_id, d.source_path): d for d in facts.link_context.incoming_documents
    }
    current_documents = {
        (d.document_id, d.source_path): d for d in facts.link_context.current_documents
    }
    subjects = []
    for subject in facts.subjects:
        document_id = f"subject:{subject.item_id}:{subject.facet}"
        document = documents.get((document_id, subject.path))
        links = _generated_navigation_references(subject, document, destinations)
        if links:
            links = _retained_navigation_tokens(facts, subject, links, prior)
        current = current_documents.get((document_id, subject.current.path))
        if (
            links
            and current is not None
            and current.status == "supported"
            and same_content(subject.baseline.content, subject.incoming)
            and moved_navigation_valid(
                links.values(), current.occurrences, current.occurrences
            )
        ):
            links.clear()
        subjects.append(
            subject.model_copy(update={"moved_navigation": tuple(links.values())})
            if links
            else subject
        )
    return facts.model_copy(update={"subjects": tuple(subjects)})


def automatic_merge_facts(facts, *, _owner=None):
    """Interpret computed clean results; Core independently validates their evidence."""
    facts = facts.model_copy(
        update={
            "format_operation": facts.format_operation.model_copy(
                update={"automatic_merge": True}
            )
        }
    )
    from brz2obsidian.content_fingerprints import drive_inline
    from brz2obsidian.core.reconciliation import ReconcileWork

    proposal = (
        drive_inline(ReconcileWork(facts))
        if _owner is None
        else _owner._drive(ReconcileWork(facts))
    )
    context = facts.link_context
    subjects = []
    for subject, change in zip(facts.subjects, proposal.changes, strict=True):
        if (
            change.disposition == "compatible"
            and change.attachment_review is not None
            and change.format_review is None
        ):
            subject = automatic_attachment_facts(
                facts, proposal, subject, change, _owner=_owner
            )
            subjects.append(subject)
            continue
        if (
            change.disposition != "compatible"
            or change.structure_result is None
            or subject.attachment is not None
            or change.format_review is not None
        ):
            subjects.append(subject)
            continue
        targets = context.incoming_targets
        own = next(
            (
                t
                for t in context.current_targets
                if t.canonical_path == change.target_path
            ),
            None,
        )
        if own is None:
            subjects.append(subject)
            continue
        content = change.result
        state = link_state(
            content,
            target_id=own.target_id,
            existence="present",
            membership_targets=targets,
            source_path=change.target_path,
            output_format=facts.incoming_identity.output_format,
            _owner=_owner,
        )
        states = tuple(
            s for s in context.incoming_target_facts if s.target_id != own.target_id
        ) + (state,)
        candidate = inspect_text_candidate(
            content,
            identity=_identity(facts.incoming_identity, subject.item_id),
            target=subject.source_target,
            output_format=facts.incoming_identity.output_format,
            source_path=change.target_path,
            document_id=own.target_id,
            path_mode="vault",
            link_targets=targets,
            link_target_facts=states,
            link_inventory=context.inventory,
            membership_targets=targets,
        )
        subjects.append(subject.model_copy(update={"automatic_result": candidate}))
    return facts.model_copy(update={"subjects": tuple(subjects)})


def automatic_attachment_facts(facts, proposal, subject, change, *, _owner=None):
    from brz2obsidian.contracts import ReviewRequirement

    from .attachment_choices import selected_attachment_candidate
    from .review_choices import review_plan_attachment_references

    view = SimpleNamespace(facts=facts, proposal=proposal)
    row = ReviewRequirement(
        requirement_id=change.change_id,
        change_id=change.change_id,
        domain="attachment",
        choices=("incoming",),
        assumptions=change.assumptions,
    )
    alternative = next(
        (
            a
            for a in change.attachment_review.alternatives
            if a.choice == "incoming" and a.eligible
        ),
        None,
    )
    if alternative is None:
        return subject
    refs = review_plan_attachment_references(view, row.requirement_id, _choices=(row,))
    offered = {
        (r.document_id, r.occurrence_id): r for r in change.attachment_review.links
    }
    choices = []
    for token, doc, occurrence in refs:
        link = offered[(doc.document_id, occurrence.occurrence_id)]
        if (
            link.old is None
            or link.incoming is None
            or "use_incoming" not in link.choices
        ):
            return subject
        # Only the content version may change; preserve destination identity, path,
        # fragment, status and authored display text without guessing a reference.
        if (
            link.old.model_copy(update={"target_version": link.incoming.target_version})
            != link.incoming
        ):
            return subject
        choices.append({"reference_id": token, "choice": "use_incoming"})
    try:
        links, candidate = selected_attachment_candidate(
            view,
            change,
            alternative,
            tuple(choices),
            refs,
            _session=_owner,
        )
    except ValueError:
        return subject
    return subject.model_copy(
        update={"automatic_attachment": candidate, "automatic_attachment_links": links}
    )


def _physical_target(path, current_path, inventory):
    value = target(path)
    normalized = value.normalized_path
    collisions = tuple(
        row
        for row in inventory
        if row.path != current_path
        and (
            target(row.path).normalized_path == normalized
            or target(row.path).normalized_path.startswith(normalized + "/")
            or normalized.startswith(target(row.path).normalized_path + "/")
        )
    )
    return value.model_copy(update={"status": "unsafe"}) if collisions else value


def _add_unrepresented_link_targets(
    facts, incoming_record, physical_inventory, current_lookup, incoming_lookup
):
    current_targets, current_states = current_lookup
    incoming_targets, incoming_states = incoming_lookup
    for row in incoming_record["item_targets"]:
        path = row["relative_path"]
        if row["created"] or any(t.canonical_path == path for t in current_targets):
            continue
        reference = ReferenceTarget(
            schema_id="brz2obsidian.reference-target",
            schema_version=1,
            target_id="intentional:" + row["original_identity"],
            kind="note",
            canonical_path=path,
            identity=_identity(facts.incoming_identity, row["original_identity"]),
            target=target(path),
            representations=(path,),
            validation_fingerprint=digest(("intentionally_uncreated", path)),
            status="safe",
        )
        current_targets.append(reference)
        incoming_targets.append(reference)
        state = interpret_link_target(
            None,
            target_id=reference.target_id,
            existence="intentionally_uncreated",
            memberships=(),
        )
        current_states.append(state)
        incoming_states.append(state)
    for row in physical_inventory:
        if any(t.canonical_path == row.path for t in current_targets):
            continue
        reference = ReferenceTarget(
            schema_id="brz2obsidian.reference-target",
            schema_version=1,
            target_id="physical:" + row.path,
            kind="note" if row.path.lower().endswith(".md") else "resource",
            canonical_path=row.path,
            identity=None,
            target=target(row.path),
            representations=(row.path,),
            validation_fingerprint=digest(row.model_dump(mode="json")),
            status="safe",
        )
        current_targets.append(reference)
        incoming_targets.append(reference)


def _interpret_link_documents(
    facts, paths, current_lookup, incoming_lookup, *, record_path
):
    current_targets, current_states = current_lookup
    incoming_targets, incoming_states = incoming_lookup
    current_documents, incoming_documents = [], []
    for row, subject, actual, received in paths:
        if actual.kind != "resource" and row.current.content is not None:
            current_documents.append(
                interpret_links(
                    row.current.content,
                    document_id=actual.target_id,
                    source_path=row.current.path,
                    path_mode="vault",
                    targets=tuple(current_targets),
                    target_facts=tuple(current_states),
                    inventory="complete",
                    output_format=facts.incoming_identity.output_format
                    if facts.incoming_identity.output_format in QUALIFIED_OUTPUT_FORMATS
                    else (
                        7
                        if facts.baseline_identity.output_format == 6
                        else facts.baseline_identity.output_format
                    ),
                    record_format=facts.baseline_identity.output_format,
                    owned_record_path=record_path,
                    authored_links=facts.format_operation.kind == "collection_import",
                )
            )
        if received is not None and actual.kind != "resource":
            for path in dict.fromkeys(
                (row.current.path, subject.path if subject else row.current.path)
            ):
                incoming_documents.append(
                    interpret_links(
                        received,
                        document_id=actual.target_id,
                        source_path=path,
                        path_mode="vault",
                        targets=tuple(incoming_targets),
                        target_facts=tuple(incoming_states),
                        inventory="complete",
                        output_format=facts.incoming_identity.output_format,
                        owned_record_path=record_path,
                        authored_links=(
                            facts.format_operation.kind == "collection_import"
                            and subject is None
                        ),
                    )
                )
    return current_documents, incoming_documents


def _add_absent_remap_destinations(
    facts,
    baseline_record,
    incoming_memberships,
    physical_inventory,
    current,
    incoming,
    *,
    classification_remap,
):
    if not classification_remap:
        return
    current_targets, current_states = current
    incoming_targets, incoming_states = incoming
    present_paths = tuple(physical_inventory) + tuple(
        SimpleNamespace(path=entry.current.path)
        for entry in facts.identity_inventory
        if entry.current.existence != "absent"
    )
    registered = {row.target_id for row in (*current_targets, *incoming_targets)}
    still_mapped = {row.target_id for row in incoming_memberships}
    for previous in _membership_targets((baseline_record,), facts.identity_inventory):
        if (
            previous.canonical_path is None
            or not previous.target_id.startswith("shared-category:")
            or previous.status != "safe"
            or previous.target_id in registered
            or previous.target_id in still_mapped
            or _physical_target(previous.canonical_path, None, present_paths).status
            != "safe"
        ):
            continue
        state = interpret_link_target(
            None, target_id=previous.target_id, existence="missing", memberships=()
        )
        current_targets.append(previous)
        incoming_targets.append(previous)
        current_states.append(state)
        incoming_states.append(state)


def _link_context(
    facts,
    baseline_record,
    incoming_record,
    physical_inventory,
    *,
    scoped_collection=False,
    record_path,
    classification_remap=False,
    _owner=None,
):
    subjects = {
        (_identity(facts.incoming_identity, s.item_id), s.facet): s
        for s in facts.subjects
    }
    unbound_reservations = {
        s.path: s
        for s in facts.subjects
        if s.prior_reservation and not s.previously_generated
    }
    observed_identities = {
        (row.identity, row.facet) for row in facts.identity_inventory
    }
    scoped_record = "/" in record_path
    current_memberships = _membership_targets(
        (baseline_record, incoming_record),
        facts.identity_inventory,
        scoped_record=scoped_record,
    )
    incoming_memberships = _membership_targets(
        (incoming_record,), scoped_record=scoped_record
    )
    if incoming_record.get("vault_tag_mappings") or incoming_record.get(
        "category_mappings"
    ):
        present = {row.target_id for row in incoming_memberships}
        incoming_memberships += tuple(
            row
            for row in current_memberships
            if row.kind == "tag" and row.target_id not in present
        )
    categories = {
        record.identity
        for record in current_memberships + incoming_memberships
        if record.kind == "category"
    }
    current_category_anchors = {
        row.target_id: row.category_anchor
        for row in current_memberships
        if row.kind == "category"
    }
    shared_categories = {
        row.canonical_path: row
        for row in incoming_memberships + current_memberships
        if row.target_id.startswith("shared-category:")
    }
    current_targets, incoming_targets, current_states, incoming_states = [], [], [], []
    paths = []
    for row in facts.identity_inventory:
        subject = (
            subjects.get((row.identity, row.facet))
            if row.identity is not None
            else None
        )
        target_id = (
            "subject:" + subject.item_id + ":" + subject.facet
            if subject is not None
            else row.entry_id
        )
        actual = ReferenceTarget(
            schema_id="brz2obsidian.reference-target",
            schema_version=1,
            target_id=target_id,
            kind="category"
            if row.facet == "content"
            and row.identity is not None
            and row.identity in categories
            else "note"
            if row.facet != "asset"
            and (row.identity is not None or row.current.path.lower().endswith(".md"))
            else "resource",
            canonical_path=row.current.path,
            identity=row.identity,
            target=row.target,
            representations=_representations(
                row.current.path,
                "category"
                if row.facet == "content"
                and row.identity is not None
                and row.identity in categories
                else "note",
            ),
            validation_fingerprint=digest((target_id, row.current.path)),
            status="safe",
            category_anchor=current_category_anchors.get(target_id),
        )
        if actual.kind == "resource":
            actual = actual.model_copy(update={"identity": None})
        actual = shared_categories.get(row.current.path, actual)
        target_id = actual.target_id
        intended = (
            unbound_reservations.get(row.current.path)
            if subject is None
            and row.identity_state == "missing"
            and row.identity is None
            else None
        )
        if (
            intended is not None
            and (_identity(facts.incoming_identity, intended.item_id), intended.facet)
            in observed_identities
        ):
            intended = None
        future = (
            actual
            if subject is None
            or subject.source_still_reserved
            or scoped_collection
            and subject.output_role == "note"
            and subject.baseline.content is not None
            and row.identity_state == "valid"
            and row.current.existence == "present"
            else actual.model_copy(
                update={
                    "canonical_path": subject.path,
                    "target": subject.source_target,
                    "representations": _representations(subject.path, actual.kind),
                }
            )
        )
        if intended is not None:
            future = actual.model_copy(
                update={
                    "identity": _identity(facts.incoming_identity, intended.item_id)
                }
            )
        if any(t.target_id == target_id for t in current_targets):
            actual = actual.model_copy(
                update={"target_id": target_id + ":" + row.entry_id}
            )
            future = future.model_copy(update={"target_id": actual.target_id})
        generated = subject or intended
        received = row.current.content if generated is None else generated.incoming
        reserved = (
            subject is not None
            and (
                subject.prior_reservation
                or subject.source_still_reserved
                or subject.previously_generated
            )
            and row.current.path == subject.path
            and row.current.existence == "absent"
        )
        if subject is not None and subject.source_still_reserved:
            received = row.current.content
        current_existence = "present" if row.current.content is not None else "missing"
        if reserved:
            current_existence = "intentionally_uncreated"
        incoming_existence = "present" if received is not None else "missing"
        if reserved and subject.previously_generated:
            received = None
            incoming_existence = "intentionally_uncreated"
        current_targets.append(actual)
        incoming_targets.append(future)
        current_states.append(
            link_state(
                row.current.content,
                target_id=actual.target_id,
                existence=current_existence,
                membership_targets=current_memberships,
                source_path=actual.canonical_path,
                qualify_roles=facts.incoming_identity.output_format
                in QUALIFIED_OUTPUT_FORMATS,
                output_format=(
                    7
                    if facts.baseline_identity.output_format == 6
                    else facts.baseline_identity.output_format
                ),
                _owner=_owner,
            )
        )
        incoming_states.append(
            link_state(
                received,
                target_id=future.target_id,
                existence=incoming_existence,
                membership_targets=incoming_memberships,
                source_path=future.canonical_path,
                output_format=facts.incoming_identity.output_format,
                _owner=_owner,
            )
        )
        paths.append((row, subject, actual, received))
    current_targets.extend(t for t in current_memberships if t.kind == "tag")
    incoming_targets.extend(t for t in incoming_memberships if t.kind == "tag")
    _add_unrepresented_link_targets(
        facts,
        incoming_record,
        physical_inventory,
        (current_targets, current_states),
        (incoming_targets, incoming_states),
    )
    _add_absent_remap_destinations(
        facts,
        baseline_record,
        incoming_memberships,
        physical_inventory,
        (current_targets, current_states),
        (incoming_targets, incoming_states),
        classification_remap=classification_remap,
    )
    current_documents, incoming_documents = _interpret_link_documents(
        facts,
        paths,
        (current_targets, current_states),
        (incoming_targets, incoming_states),
        record_path=record_path,
    )
    return LinkContext(
        schema_id="brz2obsidian.link-context",
        schema_version=1,
        inventory="complete",
        current_targets=tuple(current_targets),
        incoming_targets=tuple(incoming_targets),
        current_target_facts=tuple(current_states),
        incoming_target_facts=tuple(incoming_states),
        current_documents=tuple(current_documents),
        incoming_documents=tuple(incoming_documents),
    )
