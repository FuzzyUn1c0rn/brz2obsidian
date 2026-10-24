"""Small public IO observations retain real physical byte/binding checks."""

import hashlib
import json
import tempfile
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from brz2obsidian.application.checkpoint_contracts import (
    CheckpointLocator,
    VaultAssociation,
)
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.source_payload_contracts import SourcePayloadFile
from brz2obsidian.application.update_contracts import UpdatePreparation
from brz2obsidian.application.update_facts import assemble_facts
from brz2obsidian.application.vault_contracts import VaultFile
from brz2obsidian.application.vault_update_contracts import VaultApplyResult
from brz2obsidian.contracts import (
    AttachmentCandidate,
    AttachmentSelection,
    IdentityTargetFacts,
    ReviewConsentRequirement,
    SourceIdentity,
)
from brz2obsidian.core import prepare_review, resolve_review
from brz2obsidian.obsidian import interpret_link_target
from brz2obsidian.publication.vault_native import observe_file
from tests.reconciliation.test_resolution import action, preflight

COLLECTION = "11111111-1111-4111-8111-111111111111"
ITEM = "22222222-2222-4222-8222-222222222222"
NOTE = "Notes/Opening.md"


@pytest.fixture(autouse=True)
def controlled_public_input_reader(monkeypatch):
    def inputs(operations, vault):
        return nullcontext(
            SimpleNamespace(
                history=operations.inspect_history(vault),
                read_payload=lambda **kwargs: operations.read_checkpoint_payload(
                    vault, **kwargs
                ),
                inspect=lambda **kwargs: operations.inspect_history(vault, **kwargs),
            )
        )

    monkeypatch.setattr(Operations, "inspect_update_inputs", inputs)


def note(body):
    return (
        '---\nsource_collection_id: "'
        + COLLECTION
        + '"\nsource_item_id: "'
        + ITEM
        + '"\n---\n\n# Opening\n\n'
        + body
        + "\n"
    ).encode()


def payload(version, body):
    identity = SourceIdentity(
        source_id=COLLECTION,
        module_id="thebrain-brz",
        module_version="10",
        format_version="5",
        source_sha256=version * 64,
        snapshot_digest=version * 64,
    )
    record = {
        "schema": "brz2obsidian.migration",
        "schema_version": 7,
        "source_identity": identity.model_dump(),
        "profile_id": "thebrain-format5-reviewed",
        "profile_version": "10",
        "item_targets": [
            {
                "created": True,
                "relative_path": NOTE,
                "original_identity": ITEM,
                "original_title": "Opening",
            }
        ],
        "asset_targets": [],
        "source_gaps": [],
    }
    return {NOTE: note(body), "migration-record.json": json.dumps(record).encode()}


def refused_publication():
    return VaultApplyResult(
        schema_id="brz2obsidian.vault-apply-result",
        schema_version=1,
        status="refused",
        code="publication_boundary_reached",
        operation_id=None,
        kind="apply",
        generation=None,
        phase="admission",
        publication="not_started",
        history="none",
        planned_files=0,
        published_files=0,
        authored_files_changed=False,
        checkpoint_commit=None,
        intent_commit=None,
        result_commit=None,
        receipt_commit=None,
        recovery_required=False,
        elapsed_ms=0,
        message="The controlled public mutation boundary was reached.",
    )


@pytest.fixture
def admitted_case(tmp_path, monkeypatch, request):
    vault = tmp_path / "vault"
    vault.mkdir()
    before, incoming = payload("a", "Original A."), payload("b", "Incoming B.")
    current = {**incoming, NOTE: note("Kept authored C.")}
    for path, raw in {**current, "Ignored/private.bin": b"private"}.items():
        target = vault / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    inventory = []
    for path in sorted((*current, "Ignored/private.bin")):
        info, sha, _, identity = observe_file(vault, vault / path, prefix_limit=0)
        excluded = path.startswith("Ignored/")
        inventory.append(
            VaultFile(
                path=path,
                mode="100644",
                size=info.st_size,
                sha256=sha,
                identity=identity,
                tracked=not excluded,
                excluded=excluded,
                exclusion="git_ignore" if excluded else None,
            )
        )
    inventory = tuple(inventory)
    seed = prepare_review(
        assemble_facts(
            before,
            incoming,
            current,
            proposal_id="original-B",
            generation=1,
            current_inventory=inventory,
        ),
        preflight=preflight(),
    )
    change = next(c for c in seed.proposal.changes if c.item_id == ITEM)
    kept = resolve_review(
        seed, action(seed, change, choice="current", decision_id="keep-C")
    )
    assert kept.status == "accepted"
    memory = (kept.plan.approvals[0].source_memory,)
    assert memory[0] is not None
    plan = prepare_review(
        assemble_facts(
            incoming,
            incoming,
            current,
            proposal_id="repeat-B",
            generation=1,
            source_memory=memory,
            current_inventory=inventory,
        ),
        preflight=preflight(),
    )
    assert plan.ready, (plan.blockers, plan.requirements)
    owned = tempfile.TemporaryDirectory(prefix="brz2obsidian-update-")
    request.addfinalizer(owned.cleanup)
    source = Path(owned.name) / "incoming"
    source.mkdir()
    for path, raw in incoming.items():
        target = source / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    operations = Operations()
    binding = operations.observe_reviewed_source(source, plan)
    association = VaultAssociation(
        schema_id="brz2obsidian.vault-association",
        schema_version=1,
        association_id="a" * 64,
        vault_id="vault",
        import_id="import",
        collection_id=COLLECTION,
        module_id="thebrain-brz",
        vault_anchor="observed-vault",
        git_anchor="observed-git",
        ref="refs/brz2obsidian/imports/" + "a" * 64 + "/checkpoints",
    )
    locator = CheckpointLocator(
        schema_id="brz2obsidian.checkpoint-locator",
        schema_version=1,
        association=association,
        generation=2,
        commit="b" * 40,
    )
    observed = SourceIdentity.model_validate(
        json.loads(incoming["migration-record.json"])["source_identity"]
    )
    prepared = UpdatePreparation(
        schema_id="brz2obsidian.update-preparation",
        schema_version=1,
        vault=str(vault),
        locator=locator,
        payload_directory=str(source),
        source_binding=binding,
        observed_source=observed,
        retained_source_provenance=True,
        current_inventory=inventory,
        review=plan,
    )
    history = SimpleNamespace(
        status="intact",
        admission=SimpleNamespace(
            vault=str(vault),
            status="supported",
            inventory=inventory,
            preflight=plan.preflight,
            findings=(),
            recovery_gaps=("Ignored/private.bin",),
            repository=SimpleNamespace(kind="root"),
        ),
        checkpoint=SimpleNamespace(
            status="valid",
            locator=locator,
            manifest=SimpleNamespace(
                boundary="result",
                identity=plan.facts.incoming_identity,
                source=binding.files,
                vault=tuple(r for r in inventory if not r.excluded),
                reviewed_source=binding,
                observed_source=observed,
            ),
            review=SimpleNamespace(saved=SimpleNamespace(plan=plan)),
        ),
    )
    monkeypatch.setattr(operations, "inspect_history", lambda *args, **kwargs: history)
    monkeypatch.setattr(
        operations,
        "read_checkpoint_payload",
        lambda *args, **kwargs: SimpleNamespace(
            status="available",
            chunks=tuple(
                SimpleNamespace(path=p, data=raw) for p, raw in incoming.items()
            ),
        ),
    )
    calls = []

    def mutation(*args, **kwargs):
        calls.append(kwargs)
        return refused_publication()

    monkeypatch.setattr(operations, "apply_reviewed_update", mutation)
    return SimpleNamespace(
        operations=operations,
        preparation=prepared,
        history=history,
        calls=calls,
        incoming=incoming,
        current=current,
        memory=memory,
    )


def test_remembered_keep_with_exact_current_source_and_memory_is_a_noop(admitted_case):
    case = admitted_case
    result = case.operations.apply_update(case.preparation)
    assert (result.status, result.code) == ("no_content_change", "already_current")
    assert not case.calls and result.application is None
    assert result.changes == 2
    assert result.recovery_gaps == ("Ignored/private.bin",)
    assert result.checkpoint == case.preparation.locator
    assert result.vault == case.preparation.vault
    assert result.checkpoint_commit == "b" * 40
    assert (Path(result.vault) / NOTE).read_bytes() == note("Kept authored C.")


def test_new_local_checkpoint_effect_is_not_silently_a_noop(admitted_case):
    case = admitted_case
    prior = {**case.current, NOTE: note("Earlier checkpoint writing.")}
    rows = tuple(
        row.model_copy(
            update={
                "size": len(prior[NOTE]),
                "sha256": hashlib.sha256(prior[NOTE]).hexdigest(),
            }
        )
        if row.path == NOTE
        else row
        for row in case.history.admission.inventory
    )
    historical = prepare_review(
        assemble_facts(
            case.incoming,
            case.incoming,
            prior,
            proposal_id="repeat-B",
            generation=1,
            source_memory=case.memory,
            current_inventory=rows,
        ),
        preflight=preflight(),
    )
    assert historical.ready
    case.history.checkpoint.review.saved.plan = historical
    case.history.checkpoint.manifest.vault = tuple(r for r in rows if not r.excluded)
    result = case.operations.apply_update(case.preparation)
    assert (result.status, result.code) == ("refused", "publication_boundary_reached")
    assert len(case.calls) == 1
    assert (Path(case.preparation.vault) / NOTE).read_bytes() == note(
        "Kept authored C."
    )


def local_source_review(case, *, invented_memory):
    incoming = payload("c", "Incoming C.")
    source = Path(case.preparation.payload_directory)
    for path, raw in incoming.items():
        (source / path).write_bytes(raw)
    facts = assemble_facts(
        case.incoming,
        incoming,
        case.current,
        proposal_id="repeat-B",
        generation=1,
        current_inventory=case.history.admission.inventory,
    )
    offered = prepare_review(facts, preflight=preflight())
    change = next(c for c in offered.proposal.changes if c.item_id == ITEM)
    kept = resolve_review(
        offered, action(offered, change, choice="current", decision_id="saved-current")
    )
    assert kept.status == "accepted"
    if invented_memory:
        memory = kept.plan.approvals[0].source_memory
        assert memory is not None
        review = prepare_review(
            facts.model_copy(update={"source_version_memory": (memory,)}),
            preflight=preflight(),
        )
        stored = offered
    else:
        review = stored = kept.plan
    binding = case.operations.observe_reviewed_source(source, review)
    observed = SourceIdentity.model_validate(
        json.loads(incoming["migration-record.json"])["source_identity"]
    )
    case.history.checkpoint.review.saved.plan = stored
    case.history.checkpoint.manifest.boundary = "local"
    case.history.checkpoint.manifest.reviewed_source = binding
    case.history.checkpoint.manifest.observed_source = observed
    return case.preparation.model_copy(
        update={
            "review": review,
            "source_binding": binding,
            "observed_source": observed,
        }
    )


def test_same_local_saved_review_does_not_promote_its_own_approvals_to_memory(
    admitted_case,
):
    case = admitted_case
    prepared = local_source_review(case, invented_memory=False)
    result = case.operations.refresh_update(prepared)
    assert result.status == "prepared_review", result.code
    assert result.preparation.review.proposal.generation == 1
    assert result.preparation.review.actions == prepared.review.actions
    assert [a.decision_id for a in result.preparation.review.approvals] == [
        "saved-current"
    ]
    assert result.preparation.review.facts.source_version_memory == ()
    assert not case.calls


def test_same_local_saved_authority_refuses_caller_invented_producer_memory(
    admitted_case,
):
    case = admitted_case
    prepared = local_source_review(case, invented_memory=True)
    assert prepared.review.facts.source_version_memory
    result = case.operations.refresh_update(prepared)
    assert result.status == "stale_review" and not result.ready
    assert result.preparation.review.facts.source_version_memory == ()
    note_change = next(
        c for c in result.preparation.review.proposal.changes if c.item_id == ITEM
    )
    assert any(
        r.change_id == note_change.change_id
        for r in result.preparation.review.requirements
    )
    assert not case.calls


def binary_scope_case(case, monkeypatch, kind):
    asset = "Assets/data.bin"
    asset_id = "33333333-3333-4333-8333-333333333333"

    def with_asset(version, data):
        content = payload(version, "Incoming B.")
        record = json.loads(content["migration-record.json"])
        record["asset_targets"] = [{"asset_id": asset_id, "relative_path": asset}]
        return {
            **content,
            asset: data,
            "migration-record.json": json.dumps(record).encode(),
        }

    baseline = with_asset("b", b"\x00original")
    incoming = with_asset("c", b"abc")
    current = {**baseline, NOTE: case.current[NOTE], asset: b"\x00authored"}
    vault = Path(case.preparation.vault)
    # This case isolates new selected paths. Unrelated metadata-only binary
    # competitors have their own attachment-context regression.
    (vault / "Ignored/private.bin").unlink()
    for root, files in (
        (vault, current),
        (Path(case.preparation.payload_directory), incoming),
    ):
        for path, raw in files.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    inventory = []
    for path in sorted(current):
        info, sha, _, identity = observe_file(vault, vault / path, prefix_limit=0)
        excluded = path.startswith("Ignored/")
        inventory.append(
            VaultFile(
                path=path,
                mode="100644",
                size=info.st_size,
                sha256=sha,
                identity=identity,
                tracked=not excluded,
                excluded=excluded,
                exclusion="git_ignore" if excluded else None,
            )
        )
    inventory = tuple(inventory)
    facts = assemble_facts(
        baseline,
        incoming,
        current,
        proposal_id="repeat-B",
        generation=1,
        current_inventory=inventory,
        source_memory=case.memory,
    )
    offered = prepare_review(facts, preflight=preflight())
    binding = case.operations.observe_reviewed_source(
        case.preparation.payload_directory, offered
    )
    observed = SourceIdentity.model_validate(
        json.loads(incoming["migration-record.json"])["source_identity"]
    )
    checkpoint = case.history.checkpoint
    checkpoint.manifest.boundary = "local"
    checkpoint.manifest.source = tuple(
        SourcePayloadFile(
            path=p, mode="100644", size=len(raw), sha256=hashlib.sha256(raw).hexdigest()
        )
        for p, raw in sorted(baseline.items())
    )
    checkpoint.manifest.vault = tuple(r for r in inventory if not r.excluded)
    checkpoint.manifest.reviewed_source = binding
    checkpoint.manifest.observed_source = observed
    checkpoint.review.saved.plan = offered
    case.history.admission.inventory = inventory
    case.history.admission.recovery_gaps = ()
    monkeypatch.setattr(
        case.operations,
        "read_checkpoint_payload",
        lambda *a, **k: SimpleNamespace(
            status="available",
            chunks=tuple(
                SimpleNamespace(path=p, data=raw) for p, raw in baseline.items()
            ),
        ),
    )
    revision, queries = [1], []
    slot = "Assets/data (incoming-ba7816bf).bin"

    def inspection(vault, *, subjects=()):
        queries.append(tuple(subjects))
        selected = tuple(s.subject_id for s in subjects if s.path == slot)
        required = preflight()
        if selected:
            owners = (
                tuple(sorted({s.subject_id for s in subjects}))
                if kind == "storage"
                else selected
            )
            requirement = ReviewConsentRequirement(
                schema_id="brz2obsidian.review-consent-requirement",
                schema_version=1,
                consent_id="vault:" + kind,
                kind=kind,
                requirement="required",
                policy="builtin_transform" if kind == "storage" else "ordinary",
                fingerprint="selected-slot-policy:" + str(revision[0]),
                disclosure="Review the actual selected output storage policy.",
                subjects=owners,
            )
            required = required.model_copy(update={"consents": (requirement,)})
        admission = SimpleNamespace(
            **{**vars(case.history.admission), "preflight": required}
        )
        return SimpleNamespace(**{**vars(case.history), "admission": admission})

    monkeypatch.setattr(case.operations, "inspect_history", inspection)
    prepared = case.preparation.model_copy(
        update={
            "review": offered,
            "source_binding": binding,
            "observed_source": observed,
            "current_inventory": inventory,
        }
    )
    record = next(
        c
        for c in offered.proposal.changes
        if c.item_id == "support:migration-record.json"
    )
    chosen = case.operations.resolve_update(
        prepared, action(offered, record, choice="current", decision_id="keep-record")
    )
    assert chosen.code == "accepted", chosen.code
    return chosen.preparation, revision, queries, slot


def choose_both(operations, prepared):
    plan = prepared.review
    change = next(c for c in plan.proposal.changes if c.attachment_review is not None)
    alternative = next(
        a for a in change.attachment_review.alternatives if a.choice == "both"
    )
    selection = AttachmentSelection(
        schema_id="brz2obsidian.attachment-selection",
        schema_version=1,
        proposal_id=plan.proposal.proposal_id,
        generation=plan.proposal.generation,
        item_id=change.item_id,
        facet=change.facet,
        reviewed_change_id=change.change_id,
        reviewed_assumptions=change.assumptions,
        choice="both",
        link_choices=(),
        provenance="explicit_user",
    )
    context = plan.producer_facts.link_context
    base = next(
        t
        for t in context.current_targets
        if t.target_id == change.attachment_review.alternatives[0].outputs[0].target_id
    )
    targets = tuple(t for t in context.current_targets if t.target_id != base.target_id)
    states = tuple(
        s for s in context.current_target_facts if s.target_id != base.target_id
    )
    for output in alternative.outputs:
        targets += (
            base.model_copy(
                update={
                    "target_id": output.target_id,
                    "canonical_path": output.path,
                    "target": IdentityTargetFacts(
                        normalized_path=output.path.casefold(),
                        containment="contained",
                        status="safe",
                    ),
                    "representations": (output.path,),
                }
            ),
        )
        states += (
            interpret_link_target(
                output.content,
                target_id=output.target_id,
                existence="present",
                memberships=(),
            ),
        )
    candidate = AttachmentCandidate(
        schema_id="brz2obsidian.attachment-candidate",
        schema_version=1,
        outputs=alternative.outputs,
        documents=context.current_documents,
        targets=targets,
        target_facts=states,
    )
    return operations.resolve_update(
        prepared,
        action(
            plan,
            change,
            domain="attachment",
            choice="both",
            decision_id="both-reviewed",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    )


@pytest.mark.parametrize("kind", ("tracking", "storage"))
def test_only_selected_binary_slot_exposes_fresh_consent_and_rule_changes(
    admitted_case, monkeypatch, kind
):
    case = admitted_case
    prepared, revision, queries, slot = binary_scope_case(case, monkeypatch, kind)
    unselected = case.operations.refresh_update(prepared)
    assert unselected.preparation is not None, unselected.code
    assert all(s.path != slot for s in queries[-1])
    chosen = choose_both(case.operations, unselected.preparation)
    assert chosen.code == "accepted" and chosen.ready, chosen.code
    refreshed = case.operations.refresh_update(chosen.preparation)
    assert refreshed.status == "stale_review" and not refreshed.ready
    assert slot in {s.path for s in queries[-1]}
    assert [a.decision_id for a in refreshed.preparation.review.approvals] == [
        "keep-record",
        "both-reviewed",
    ]
    requirement = next(
        r for r in refreshed.preparation.review.requirements if r.domain == kind
    )
    accepted = case.operations.resolve_update(
        refreshed.preparation,
        action(
            refreshed.preparation.review,
            domain=kind,
            choice="accept",
            decision_id="consent:slot",
            change_id=requirement.change_id,
            reviewed_assumptions=requirement.assumptions,
        ),
    )
    assert accepted.ready, accepted.code
    revision[0] = 2
    stale = case.operations.apply_update(accepted.preparation)
    assert stale.status == "stale_review" and not stale.ready
    assert any(r.domain == kind for r in stale.preparation.review.requirements)
    assert not stale.preparation.review.consents
    assert not case.calls
    assert not (Path(case.preparation.vault) / slot).exists()
