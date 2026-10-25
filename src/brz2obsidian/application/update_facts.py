"""Interpret exact owned source payload and a complete current inventory."""

import hashlib
import json
import unicodedata
from pathlib import PurePosixPath

from brz2obsidian.contracts import (
    AttachmentDestination,
    AttachmentFacts,
    ContentVersion,
    CurrentContent,
    ExactContent,
    FormatBaselineOutput,
    FormatOperation,
    IdentityInventoryItem,
    IdentityTargetFacts,
    ImportedItemIdentity,
    LinkContext,
    OutputIdentity,
    ReconciliationInput,
    ReconciliationSubject,
    ReferenceTarget,
    SafetyFact,
    SupportedFormatBaseline,
)
from brz2obsidian.obsidian import (
    align_structure,
    interpret_link_target,
    interpret_links,
    interpret_structure,
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


def record(payload):
    value = json.loads(payload["migration-record.json"])
    if value.get("schema") != "brz2obsidian.migration":
        raise ValueError("association_record_invalid")
    return value


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


def _membership_targets(records, inventory=()):
    rows, tokens = {}, {}
    identity = output_identity(records[-1])
    for value in records:
        for row in value["item_targets"]:
            item = row["original_identity"]
            if "definition" in row.get("creation_reasons", ()):
                rows[item] = row
            if row.get("vault_tag_token"):
                tokens[item] = row["vault_tag_token"]
    result = []
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
            )
        )
    for item, token in sorted(tokens.items()):
        result.append(
            ReferenceTarget(
                schema_id="brz2obsidian.reference-target",
                schema_version=1,
                target_id=(
                    "tag:"
                    + identity.module_id
                    + ":"
                    + identity.collection_id
                    + ":"
                    + item
                ),
                kind="tag",
                canonical_path=None,
                identity=None,
                target=None,
                representations=(token,),
                validation_fingerprint=digest((identity.collection_id, item, token)),
                status="safe",
            )
        )
    if rows:
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


def link_state(content, *, target_id, existence, membership_targets=()):
    document = (
        interpret_structure(
            content, output_format=7, membership_targets=membership_targets
        )
        if content is not None
        else None
    )
    memberships = (
        tuple(
            entry.target_id for group in document.memberships for entry in group.entries
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
    )


def _observed_identity(path, content, identity, established):
    if path in established and established[path][1] != "note":
        return "valid", _identity(identity, established[path][0]), established[path][2]
    if not path.lower().endswith(".md"):
        return "missing", None, None
    document = interpret_structure(content, output_format=7)
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
):
    old_record, new_record = record(baseline), record(incoming)
    old_identity, identity = output_identity(old_record), output_identity(new_record)
    old, new = _outputs(old_record, baseline), _outputs(new_record, incoming)
    established = {
        path: (item, role, facet) for (item, facet), (path, role, _) in old.items()
    }
    inventory = []
    for path, raw in sorted(current.items()):
        content = ExactContent(data=raw)
        state, claim, facet = _observed_identity(path, content, identity, established)
        inventory.append(
            IdentityInventoryItem(
                entry_id="file:" + path,
                facet=facet,
                identity_state=state,
                identity=claim,
                raw_identity=None,
                title=PurePosixPath(path).stem,
                current=CurrentContent(existence="present", path=path, content=content),
                target=target(path),
            )
        )
    membership_views = (
        _membership_targets((old_record,)),
        _membership_targets((old_record, new_record), inventory),
        _membership_targets((new_record,)),
    )
    subjects, outputs = [], []
    observed_paths = {row.path for row in current_inventory} | set(current)
    for key in sorted(old.keys() | new.keys()):
        item, facet = key
        path, role, title = new.get(key, old.get(key))
        old_path = old.get(key, (path, role, title))[0]
        original = (
            ExactContent(data=baseline[old_path])
            if originals_known and old_path in baseline
            else None
        )
        received = ExactContent(data=incoming[path]) if key in new else None
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
                content=ExactContent(data=current[old_path])
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
        structure = None
        interpretation = "opaque" if facet == "asset" else "supported"
        if facet != "asset" and all(
            content is not None for content in (original, selected.content, received)
        ):
            documents = tuple(
                interpret_structure(
                    content, output_format=7, membership_targets=targets
                )
                for content, targets in zip(
                    (original, selected.content, received),
                    membership_views,
                    strict=True,
                )
            )
            structure = align_structure(*documents)
            if any(d.status != "supported" for d in documents):
                interpretation = "unsupported"
        attachment = None
        if facet == "asset":
            slots = ()
            if received is not None:
                parent = PurePosixPath(selected.path)
                suffix = PurePosixPath(path).suffix
                name = (
                    parent.stem
                    + " (incoming-"
                    + hashlib.sha256(received.data).hexdigest()[:8]
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
        format_operation=FormatOperation(
            schema_id="brz2obsidian.format-operation",
            schema_version=1,
            kind="onboarding" if onboarding else "source_update",
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
    return facts.model_copy(
        update={
            "link_context": _link_context(
                facts, old_record, new_record, current_inventory
            )
        }
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


def _link_context(facts, baseline_record, incoming_record, physical_inventory):
    subjects = {(s.item_id, s.facet): s for s in facts.subjects}
    current_memberships = _membership_targets(
        (baseline_record, incoming_record), facts.identity_inventory
    )
    incoming_memberships = _membership_targets((incoming_record,))
    categories = {
        record.identity.item_id
        for record in current_memberships + incoming_memberships
        if record.kind == "category"
    }
    current_targets, incoming_targets, current_states, incoming_states = [], [], [], []
    paths = []
    for row in facts.identity_inventory:
        subject = (
            subjects.get((row.identity.item_id, row.facet))
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
            if row.identity is not None and row.identity.item_id in categories
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
                if row.identity is not None and row.identity.item_id in categories
                else "note",
            ),
            validation_fingerprint=digest((target_id, row.current.path)),
            status="safe",
        )
        if actual.kind == "resource":
            actual = actual.model_copy(update={"identity": None})
        future = (
            actual
            if subject is None
            else actual.model_copy(
                update={
                    "canonical_path": subject.path,
                    "target": subject.source_target,
                    "representations": _representations(subject.path, actual.kind),
                }
            )
        )
        # Duplicate identities retain distinct physical targets for ambiguity.
        if any(t.target_id == target_id for t in current_targets):
            actual = actual.model_copy(
                update={"target_id": target_id + ":" + row.entry_id}
            )
            future = future.model_copy(update={"target_id": actual.target_id})
        received = row.current.content if subject is None else subject.incoming
        current_targets.append(actual)
        incoming_targets.append(future)
        current_states.append(
            link_state(
                row.current.content,
                target_id=actual.target_id,
                existence="present" if row.current.content is not None else "missing",
                membership_targets=current_memberships,
            )
        )
        incoming_states.append(
            link_state(
                received,
                target_id=future.target_id,
                existence="present" if received is not None else "missing",
                membership_targets=incoming_memberships,
            )
        )
        paths.append((row, subject, actual, received))
    current_targets.extend(t for t in current_memberships if t.kind == "tag")
    incoming_targets.extend(t for t in incoming_memberships if t.kind == "tag")
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
                    )
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
