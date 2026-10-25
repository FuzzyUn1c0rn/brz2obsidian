"""Read bounded generated-asset associations under a validated current ancestry."""

import hashlib
import io
from typing import NamedTuple

from brz2obsidian.application.checkpoint_contracts import CheckpointManifest
from brz2obsidian.contracts import ExactContent, ImportedItemIdentity, RetainedAttachmentOwnership
from brz2obsidian.obsidian import interpret_attachment_mapping
from brz2obsidian.publication.git_payload import verify_blobs
from brz2obsidian.publication.vault_native import available_memory


class _Claim(NamedTuple):
    kind: str
    item_id: str
    facet: str
    path: str
    current_path: str
    proof: RetainedAttachmentOwnership


def interpret_attachment_disposition(owners, *, original, final, receipt, plan):
    """Retain or revoke known associations after one completed native operation.

    Values describe a disposition, not proof of a real operation. The native
    reader binds their actual receipt graph, RESULT and canonical original
    review before using this projection. This function never creates an owner.
    """
    if (
        (original.operation_id, original.kind, original.association_id)
        != (final.operation_id, final.kind, final.association_id)
        or (receipt.operation_id, receipt.kind, receipt.generation,
            receipt.direction, receipt.prepared_commit)
        != (final.operation_id, final.kind, final.generation,
            final.direction, final.prepared_commit)
        or final.generation < original.generation
        or any(owner.association_id != original.association_id for owner in owners)
    ):
        raise ValueError("Attachment disposition has no matching operation identity")
    present = {row.path for row in final.proposed}
    disassociated = set()
    if receipt.direction != "restore":
        for facts in (plan.facts, plan.producer_facts):
            entries = {entry.entry_id: entry for entry in facts.identity_inventory}
            for decision in facts.association_decisions:
                for entry_id in decision.disassociate_entry_ids:
                    entry = entries.get(entry_id)
                    if entry is None:
                        raise ValueError("Completed disassociation lacks its observed entry")
                    disassociated.add((decision.collection_id, decision.module_id,
                                       decision.item_id, decision.facet, entry.current.path))
    return tuple(owner for owner in owners if owner.source_path in present and (
        owner.identity.collection_id, owner.identity.module_id, owner.identity.item_id,
        owner.facet, owner.source_path,
    ) not in disassociated)


def review_ownership_claims(plan, effects=None):
    claims = tuple(dict.fromkeys(
        _Claim(facts.format_operation.kind, subject.item_id, subject.facet,
               subject.path, subject.current.path, subject.attachment.retained_ownership)
        for facts in (plan.facts, plan.producer_facts)
        for subject in facts.subjects
        if subject.attachment is not None and subject.attachment.retained_ownership is not None
    ))
    missing = False
    if plan.facts.format_operation.kind == "attachment_cleanup" and plan.ready:
        if effects is None:
            from brz2obsidian.core import select_review_effects

            effects = select_review_effects(plan)
        missing = effects.status != "selected" or any(
            path not in {claim.current_path for claim in claims}
            for path in effects.remove_paths
        )
    return claims, missing


def _bound_claims(*, association, roles, claims, missing, cutoff, origin_claims):
    if missing:
        raise OSError("Cleanup removal has no native ownership witness")
    if not claims:
        return None
    point = next((role for role in roles if role.commit == cutoff), None)
    if point is None:
        raise OSError("Cleanup witness has no current ancestor context")
    commits = {role.commit for role in roles if role.generation <= point.generation}
    origins = {(claim.item_id, claim.facet): claim.proof for claim in origin_claims if claim.kind == "attachment_cleanup"}
    for claim in claims:
        proof = claim.proof
        if (
            claim.kind != "attachment_cleanup"
            and origins.get((claim.item_id, claim.facet)) != proof
            or proof.association_id != association.association_id
            or (proof.identity.collection_id, proof.identity.module_id, proof.identity.item_id, proof.facet)
            != (association.collection_id, association.module_id, claim.item_id, claim.facet)
            or proof.source_path != claim.path
            or proof.source_path != claim.current_path
            or proof.checkpoint_commit not in commits
        ):
            raise OSError("Cleanup ownership witness is unbound")
    return point.generation, tuple(claim.proof for claim in claims)


def _validate_demands(git, *, association, roles, demands, observation=None):
    requests = {}
    for generation, proofs in demands:
        requests.setdefault(generation, set()).update(proof.source_path for proof in proofs)
    snapshots = _ownership_at_cutoffs(git, association=association, roles=roles, requests=requests, observation=observation)
    for generation, proofs in demands:
        expected = snapshots[generation]
        if any(expected.get(proof.source_path) != proof for proof in proofs):
            raise OSError("Cleanup ownership witness changed")


def validate_claims(git, *, association, roles, claims, missing=False, cutoff=None, origin_claims=(), observation=None):
    if not roles:
        if claims or missing:
            raise OSError("Cleanup witness has no retained ancestor context")
        return
    bound = _bound_claims(association=association, roles=roles, claims=claims,
                          missing=missing, cutoff=cutoff or roles[0].commit,
                          origin_claims=origin_claims)
    if bound is not None:
        _validate_demands(git, association=association, roles=roles, demands=(bound,), observation=observation)


def validate_history_claims(git, *, association, roles, demands, observation=None):
    from brz2obsidian.application.vault_update_contracts import VaultOperationIntent
    from .vault_apply import _read_record

    by_commit = {role.commit: role for role in roles}
    claims_by_commit = {commit: claims for commit, _, claims, _ in demands}
    origins, bound = {}, []
    for commit, origin_commit, claims, missing in demands:
        role = by_commit[commit]
        cutoff, origin_claims = role.previous, ()
        if origin_commit is not None:
            if origin_commit not in origins:
                origin, _ = _read_record(git, origin_commit, "intent.json", VaultOperationIntent)
                origin_role = by_commit.get(origin.prepared_commit)
                if origin.association_id != association.association_id or origin_role is None:
                    raise OSError("Cleanup recovery origin is unbound")
                origins[origin_commit] = origin_role
            origin_role = origins[origin_commit]
            cutoff = origin_role.previous
            origin_claims = claims_by_commit.get(origin_role.commit, ())
        if cutoff is None:
            raise OSError("Cleanup witness predates retained authority")
        request = _bound_claims(association=association, roles=roles, claims=claims,
                                missing=missing, cutoff=cutoff, origin_claims=origin_claims)
        if request is not None:
            bound.append(request)
    if bound:
        _validate_demands(git, association=association, roles=roles, demands=bound, observation=observation)


def _manifest(git, association, role):
    from .vault_history import _control_objects

    _control_objects(git, {role.commit: "commit"}, {})
    edge = git.call("ls-tree", "-z", role.commit, "--", "manifest.json").split(b"\0")
    if len(edge) != 2 or not edge[0].startswith(b"100644 blob "):
        raise OSError("Historical attachment metadata is unavailable")
    declaration, name = edge[0].split(b"\t", 1)
    if name != b"manifest.json":
        raise OSError("Historical attachment metadata is unavailable")
    oid = declaration.split()[2].decode("ascii")
    raw = _control_objects(git, {oid: "blob"}, {})[oid]
    manifest = CheckpointManifest.model_validate_json(raw)
    if (manifest.association_id, manifest.generation, manifest.previous, manifest.boundary) != (
        association.association_id, role.generation, role.previous, role.boundary
    ):
        raise OSError("Historical attachment ancestry changed")
    return manifest


def _mapping(git, manifest):
    row = next((row for row in manifest.source if row.path == "migration-record.json"), None)
    if row is None or row.size > available_memory() // 4:
        raise OSError("Historical attachment mapping is unavailable")
    sink = io.BytesIO()
    verify_blobs([*git.prefix, "cat-file", "--batch"], env=git.env,
                 objects=((row.object_id, row.size, row.sha256, sink),))
    source, assets = interpret_attachment_mapping(ExactContent(data=sink.getvalue()), identity=manifest.identity)
    mappings = {asset.relative_path: asset.asset_id for asset in assets if asset.relative_path is not None}
    return row, source, mappings


def _owner(association, role, source, mapping, item, row):
    return RetainedAttachmentOwnership(
        schema_id="brz2obsidian.retained-attachment-ownership", schema_version=1,
        association_id=association.association_id,
        checkpoint_commit=role.commit, generation=role.generation,
        identity=ImportedItemIdentity(collection_id=source.source_id,
                                     module_id=source.module_id, item_id=item),
        facet="asset", source_path=row.path, source_version=source.snapshot_digest,
        mapping_sha256=mapping.sha256, payload_sha256=row.sha256,
        payload_size=row.size, payload_mode=row.mode,
    )


def _published_origins(graph, prepared, loaded, manifest, entries, paths):
    plan = loaded.saved.plan
    if (graph.receipt.direction != "finish" or graph.intent.kind != "apply"
        or plan.facts.format_operation.kind not in ("source_update", "onboarding", "format_transition")):
        return ()
    original = graph.authorities[-1][1]
    before = {row.path: row for row in original.before}
    produced = {row.path: row for row in graph.intent.proposed}
    proposed = {row.path: row for row in original.proposed}
    source = {row.path: row for row in manifest.source}
    original_source = {row.path: row for row in prepared.source}
    selected = {row.path: row.content for row in loaded.historical_effects.files}
    explicit = {
        entry.current.path for decision in plan.facts.association_decisions
        for entry in plan.facts.identity_inventory
        if entry.entry_id == decision.selected_entry_id
        and (decision.collection_id, decision.module_id, decision.item_id, decision.facet)
        == (manifest.identity.collection_id, manifest.identity.module_id, entries.get(entry.current.path), "asset")
    }
    qualified = []
    for path in paths & entries.keys():
        row, content = source.get(path), selected.get(path)
        if (row is not None and content is not None
            and original_source.get(path) == row == proposed.get(path) == produced.get(path)
            and row.size == len(content.data) and row.sha256 == hashlib.sha256(content.data).hexdigest()
            and (before.get(path) != produced.get(path) or path in explicit)):
            qualified.append(row)
    return tuple(qualified)


def _ownership_at_cutoffs(git, *, association, roles, requests, observation=None):
    from .vault_apply import _OperationObservation

    limit = max(requests)
    results = {role.commit for role in roles if role.boundary == "result" and role.generation <= limit}
    if results and not isinstance(observation, _OperationObservation):
        raise OSError("Completed attachment ownership needs current operation proof")
    completed = {
        graph.receipt.result_commit: graph
        for graph in observation.graphs if graph.receipt is not None
    } if observation is not None else {}
    authorities = {
        commit: (graph, authority) for graph in observation.graphs
        for commit, authority in graph.authorities
    } if observation is not None else {}
    paths = set().union(*requests.values())
    owners = {}
    snapshots = {}
    mappings = {}
    for role in reversed(roles):
        if role.generation > limit:
            break
        manifest = observation.owned[role.commit][0] if observation is not None and role.commit in observation.owned else _manifest(git, association, role)
        if manifest.identity.output_format != 7 or manifest.identity.settings_digest != hashlib.sha256(b"{}").hexdigest():
            # An unqualified old format cannot establish an origin. It also
            # cannot hide a later independently qualified current publication.
            mapping, source, entries = None, None, {}
        else:
            mapping = next((row for row in manifest.source if row.path == "migration-record.json"), None)
            key = mapping, manifest.identity
            if key not in mappings:
                mapping, source, entries = _mapping(git, manifest)
                # Retain only normalized requested association facts, never
                # the record bytes or full parsed historical asset inventory.
                mappings[key] = source, {path: item for path, item in entries.items() if path in paths}
            source, entries = mappings[key]
        selected = paths & entries.keys()
        if (
            manifest.generation == 1
            and manifest.boundary == "local"
            and manifest.review_object is None
            and mapping is not None
            and next((row for row in manifest.vault if row.path == mapping.path), None) == mapping
        ):
            generated = {row.path: row for row in manifest.source}
            actual = {row.path: row for row in manifest.vault}
            for path in selected:
                row = generated.get(path)
                if row is None or actual.get(path) != row:
                    continue
                owners[path] = _owner(association, role, source, mapping, entries[path], row)
        if role.boundary == "result":
            bound = authorities.get(manifest.operation_intent_commit)
            if bound is None:
                raise OSError("Attachment RESULT has no validated native authority")
            graph, authority = bound
            if (
                authority.association_id != association.association_id
                or manifest.generation != authority.generation + 1
                or manifest.previous != authority.prepared_commit
                or manifest.preimage != authority.before
                or manifest.proposed != authority.proposed
                or manifest.vault != authority.proposed
            ):
                raise OSError("Attachment disposition differs from current native proof")
            if role.commit in completed:
                if completed[role.commit] is not graph or graph.receipt.intent_commit != manifest.operation_intent_commit:
                    raise OSError("Attachment terminal RESULT has a different receipt")
                original = graph.authorities[-1][1]
                prepared, loaded = observation.owned[original.prepared_commit]
                if loaded is None:
                    raise OSError("Attachment disposition has no canonical original plan")
                owners = {owner.source_path: owner for owner in interpret_attachment_disposition(
                    tuple(owners.values()), original=original, final=graph.intent,
                    receipt=graph.receipt, plan=loaded.saved.plan,
                )}
                if mapping is not None:
                    for row in _published_origins(graph, prepared, loaded, manifest, entries, paths):
                        if row.path not in owners or owners[row.path].identity.item_id != entries[row.path]:
                            owners[row.path] = _owner(association, role, source, mapping, entries[row.path], row)
            # An exact content-complete intermediate RESULT may remain in
            # ancestry after recovery. Without its receipt it changes no
            # effective ownership; the eventual terminal disposition does.
        requested = requests.get(role.generation)
        if requested is not None:
            snapshots[role.generation] = {path: owners[path] for path in requested & owners.keys()}
    if set(snapshots) != set(requests):
        raise OSError("Historical attachment cutoff is unavailable")
    return snapshots


def read_attachment_ownership(git, *, association, roles, paths, observation=None):
    """Return qualified owners; omission proves neither absence nor permission."""
    generation = roles[0].generation
    result = _ownership_at_cutoffs(git, association=association, roles=roles,
                                   requests={generation: set(paths)}, observation=observation)[generation]
    return tuple(result[path] for path in sorted(result))
