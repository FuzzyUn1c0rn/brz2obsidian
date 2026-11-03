"""Operation-local stale slots come from actual reobservation and Core review."""

import hashlib
import json
import tempfile
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_contracts import UpdateResult
from brz2obsidian.application.update_facts import (
    assemble_facts,
    output_identity,
    record,
)
from brz2obsidian.application.vault_contracts import VaultFile
from brz2obsidian.contracts import ReviewConsentRequirement, SourceIdentity
from brz2obsidian.core import prepare_review
from brz2obsidian.publication.vault_native import observe_file
from tests.application.test_update_lifecycle_admission import NOTE, note, payload
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_resolution import action, preflight

GUIDE = "Vault guide.md"


def review_context(plan):
    changes = {c.change_id: c for c in plan.proposal.changes}
    return {
        "required": [
            (
                r.domain,
                changes[r.change_id].path if r.change_id in changes else r.change_id,
            )
            for r in plan.requirements
        ],
        "subjects": [
            (
                s.path,
                s.interpretation,
                None
                if s.structure is None
                else (s.structure.alignment, s.structure.issues),
            )
            for s in plan.facts.subjects
        ],
        "approvals": [
            (a.domain, a.choice, changes[a.change_id].path) for a in plan.approvals
        ],
    }


def refresh_case(
    tmp_path,
    request,
    *,
    bulk=False,
    consent=False,
    identity=False,
    rename=False,
    flat=False,
):
    def reviewed_note(body):
        if not flat:
            return note(body)
        return (
            '---\nsource_collection_id: "11111111-1111-4111-8111-111111111111"\n'
            'source_item_id: "22222222-2222-4222-8222-222222222222"\n---\n'
            + body
            + "\n"
        ).encode()

    before = payload("a", "Original Second.") | {GUIDE: b"Original Guide.\n"}
    incoming = payload("b", "Incoming Second.") | {GUIDE: b"Incoming Guide.\n"}
    before[NOTE] = reviewed_note("Original Second.")
    incoming[NOTE] = reviewed_note("Incoming Second.")
    current = incoming | {
        NOTE: reviewed_note("Authored Second."),
        GUIDE: b"Authored Guide.\n",
    }
    if bulk:
        current = before | {"migration-record.json": incoming["migration-record.json"]}
    if rename:
        current["Authored/Second.md"] = current.pop(NOTE)
    if identity:
        current[NOTE] = b"Authored Second without imported identity.\n"
    vault = tmp_path / "vault"
    vault.mkdir()
    owned = tempfile.TemporaryDirectory(prefix="brz2obsidian-update-")
    request.addfinalizer(owned.cleanup)
    source = Path(owned.name) / "incoming"
    source.mkdir()
    for path, raw in incoming.items():
        target = source / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    checks = preflight()
    if consent:
        checks = checks.model_copy(
            update={
                "consents": (
                    ReviewConsentRequirement(
                        schema_id="brz2obsidian.review-consent-requirement",
                        schema_version=1,
                        consent_id="reviewed-storage",
                        kind="storage",
                        requirement="required",
                        policy="ordinary",
                        fingerprint="first-policy",
                        disclosure="Exact reviewed storage",
                        subjects=(),
                    ),
                )
            }
        )
    case = SimpleNamespace(current=current, checks=checks, note=reviewed_note)

    def inventory():
        rows = []
        for path, raw in sorted(case.current.items()):
            target = vault / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            info, sha, _, physical = observe_file(vault, target, prefix_limit=0)
            rows.append(
                VaultFile(
                    path=path,
                    mode="100644",
                    size=info.st_size,
                    sha256=sha,
                    identity=physical,
                    tracked=True,
                    excluded=False,
                    exclusion=None,
                )
            )
        return tuple(rows)

    rows = inventory()
    facts = assemble_facts(
        before,
        incoming,
        current,
        proposal_id="review:stale-slots",
        generation=1,
        current_inventory=rows,
    )
    plan = prepare_review(facts, preflight=checks)
    prepared = preparation(facts).model_copy(
        update={"vault": str(vault), "payload_directory": str(source), "review": plan}
    )
    observed = SourceIdentity.model_validate(record(incoming)["source_identity"])
    locator = prepared.locator.model_copy(
        update={
            "association": prepared.locator.association.model_copy(
                update={
                    "collection_id": facts.incoming_identity.collection_id,
                    "module_id": facts.incoming_identity.module_id,
                }
            )
        }
    )

    class Inputs(Operations):
        def read_checkpoint(self, vault, **kwargs):
            from brz2obsidian.application.checkpoint_contracts import CheckpointRead

            return CheckpointRead(
                schema_id="brz2obsidian.checkpoint-read",
                schema_version=1,
                status="valid",
                code="controlled_current",
                locator=locator,
                manifest=None,
                review=None,
                message="Controlled current checkpoint observation",
            )

        def inspect_history(self, *args, **kwargs):
            return SimpleNamespace(
                status="intact",
                admission=SimpleNamespace(
                    vault=str(vault),
                    status="supported",
                    inventory=inventory(),
                    preflight=case.checks,
                    findings=(),
                    recovery_gaps=(),
                    repository=SimpleNamespace(kind="root"),
                ),
                checkpoint=SimpleNamespace(
                    status="valid",
                    locator=locator,
                    review=None,
                    manifest=SimpleNamespace(
                        boundary="local",
                        identity=output_identity(record(before)),
                        source=case.baseline_rows,
                        reviewed_source=case.binding,
                        observed_source=observed,
                    ),
                ),
            )

        def inspect_update_inputs(self, vault):
            return nullcontext(
                SimpleNamespace(
                    history=self.inspect_history(vault),
                    read_payload=self.read_checkpoint_payload,
                    inspect=lambda **kwargs: self.inspect_history(vault, **kwargs),
                )
            )

        def read_checkpoint_payload(self, *args, **kwargs):
            return SimpleNamespace(
                status="available",
                chunks=tuple(
                    SimpleNamespace(path=p, data=raw) for p, raw in before.items()
                ),
            )

        def prepare_update(self, *args, **kwargs):
            value = case.prepared
            return UpdateResult(
                status="prepared_review" if value.review.ready else "unresolved",
                code="controlled_preparation",
                preparation=value,
                ready=value.review.ready,
                changes=len(value.review.proposal.changes),
                unresolved=len(value.review.requirements),
                history_retained=True,
                checkpoint_commit=locator.commit,
            )

        def capture_checkpoint(self, *args, **kwargs):
            raise AssertionError("Count projection cannot Save")

        def apply_reviewed_update(self, *args, **kwargs):
            raise AssertionError("Count projection cannot publish")

    operations = Inputs()
    binding = operations.observe_reviewed_source(source, plan)
    prepared = prepared.model_copy(
        update={
            "locator": locator,
            "source_binding": binding,
            "observed_source": observed,
        }
    )
    from brz2obsidian.application.source_payload_contracts import SourcePayloadFile

    case.baseline_rows = tuple(
        SourcePayloadFile(
            path=p, mode="100644", size=len(raw), sha256=hashlib.sha256(raw).hexdigest()
        )
        for p, raw in sorted(before.items())
    )
    case.binding, case.prepared, case.operations = binding, prepared, operations
    if identity or rename:
        change = next(
            c
            for c in prepared.review.proposal.changes
            if c.path == NOTE or c.item_id == facts.subjects[0].item_id
        )
        chosen = operations.resolve_update(
            prepared,
            action(
                prepared.review,
                change,
                domain="identity" if identity else "rename",
                choice="associate" if identity else "keep_path",
                selected_entry_id="file:" + NOTE if identity else None,
                decision_id="producer:original",
            ),
        )
        assert chosen.code == "accepted", chosen.code
        prepared = chosen.preparation
    if bulk:
        (group,) = prepared.review.groups
        prepared = operations.resolve_update(
            prepared,
            action(
                prepared.review,
                change_id=group.group_id,
                domain="compatible_group",
                reviewed_assumptions=group.assumptions,
                decision_id="bulk:both",
            ),
        ).preparation
    else:
        for path in (NOTE, GUIDE):
            if (identity or rename) and path == NOTE:
                continue
            change = next(c for c in prepared.review.proposal.changes if c.path == path)
            prepared = operations.resolve_update(
                prepared,
                action(
                    prepared.review,
                    change,
                    choice="current",
                    decision_id="accepted:" + path,
                ),
            ).preparation
    if consent:
        requirement = next(
            r for r in prepared.review.requirements if r.domain == "storage"
        )
        prepared = operations.resolve_update(
            prepared,
            action(
                prepared.review,
                domain="storage",
                choice="accept",
                change_id=requirement.change_id,
                reviewed_assumptions=requirement.assumptions,
                decision_id="storage:accepted",
            ),
        ).preparation
    case.prepared = prepared
    return case


def test_refresh_counts_second_slot_and_preserves_guide_then_resets_for_next_operation(
    tmp_path, request
):
    case = refresh_case(tmp_path, request)
    assert case.prepared.review.ready
    guide = next(
        a
        for a in case.prepared.review.approvals
        if a.decision_id == "accepted:" + GUIDE
    )
    token = case.prepared.review.actions[0]
    case.current[NOTE] = note("Later Second writing.")
    result = case.operations.refresh_update(case.prepared)
    assert result.preparation is not None and result.code == "current_facts_changed"
    assert result.stale == 1 and result.unresolved == 1 and not result.ready
    assert result.preparation.review.approvals == (guide,)
    assert guide.result.data == b"Authored Guide.\n"
    next_operation = case.operations.refresh_update(result.preparation)
    assert next_operation.stale == 0 and next_operation.unresolved == 1

    retained = result.preparation
    retained_json = retained.model_dump_json()
    vault = Path(retained.vault)
    before = {
        p.relative_to(vault): p.read_bytes() for p in vault.rglob("*") if p.is_file()
    }
    assert before[Path(GUIDE)] == b"Authored Guide.\n"
    assert before[Path(NOTE)] == note("Later Second writing.")
    rejected = case.operations.resolve_update(result.preparation, token)
    assert (rejected.status, rejected.code) == ("refused", "invalid_review_action")
    assert rejected.stale == 0 and not rejected.ready and rejected.preparation is None
    assert rejected.operation_id is None and rejected.generation is None
    assert rejected.checkpoint is None and rejected.checkpoint_commit is None
    assert rejected.capture is None and rejected.application is None
    assert rejected.publication == "not_started" and not rejected.history_retained
    assert retained.model_dump_json() == retained_json
    assert {
        p.relative_to(vault): p.read_bytes() for p in vault.rglob("*") if p.is_file()
    } == before

    page = case.operations.inspect_update_review(
        retained,
        proposal_id=retained.review.proposal.proposal_id,
        generation=retained.review.proposal.generation,
    )
    assert (page.status, page.code) == ("available", "available")
    guide_row = next(row for row in page.items if row.current_path == GUIDE)
    second_row = next(row for row in page.items if row.current_path == NOTE)
    assert guide_row.result == b"Authored Guide.\n" and not guide_row.omitted
    assert second_row.current == note("Later Second writing.") and not second_row.omitted
    assert second_row.result is None
    assert [(r.domain, r.change_id) for r in retained.review.requirements] == [
        ("text", second_row.change_id)
    ]


def test_bulk_action_counts_each_invalidated_member_slot(tmp_path, request):
    case = refresh_case(tmp_path, request, bulk=True, flat=True)
    assert case.prepared.review.ready and len(case.prepared.review.approvals) == 2, (
        review_context(case.prepared.review)
    )
    assert {a.decision_id for a in case.prepared.review.approvals} == {"bulk:both"}
    case.current[NOTE] = case.note("Later Second writing.")
    case.current[GUIDE] = b"Later Guide writing.\n"
    result = case.operations.refresh_update(case.prepared)
    assert result.preparation is not None and not result.ready
    assert result.stale == result.unresolved == 2
    assert result.preparation.review.approvals == ()


def test_invalidated_required_consent_is_one_separate_slot(tmp_path, request):
    case = refresh_case(tmp_path, request, consent=True)
    assert case.prepared.review.ready
    (requirement,) = case.checks.consents
    case.checks = case.checks.model_copy(
        update={
            "consents": (
                requirement.model_copy(update={"fingerprint": "changed-policy"}),
            )
        }
    )
    result = case.operations.refresh_update(case.prepared)
    assert result.preparation is not None and not result.ready
    assert result.preparation.review.approvals == case.prepared.review.approvals
    assert result.preparation.review.consents == ()
    assert result.stale == result.unresolved == 1
    assert [r.domain for r in result.preparation.review.requirements] == ["storage"]


def test_retired_choice_that_no_longer_needs_review_keeps_canonical_readiness(
    tmp_path, request
):
    from brz2obsidian.application.update_context import UpdateContext
    from tests.application.test_update_context import worker_context_call

    case = refresh_case(tmp_path, request, flat=True)
    case.current[NOTE] = case.note("Incoming Second.")
    result = case.operations.refresh_update(case.prepared)
    assert result.preparation is not None
    assert result.preparation.review.ready, review_context(result.preparation.review)
    assert len(result.preparation.review.approvals) == 1
    assert result.ready and result.stale == result.unresolved == 0
    stopped = case.operations.apply_update(case.prepared)
    assert stopped.status == "stale_review" and stopped.application is None
    assert stopped.publication == "not_started"
    context = UpdateContext(operations=case.operations)
    opened = worker_context_call(
        context,
        {
            "command": "prepare",
            "kind": "source_update",
            "source": str(tmp_path / "controlled.brz"),
            "vault": case.prepared.vault,
            "selection_id": str(uuid4()),
        },
    )
    refreshed = worker_context_call(
        context, {"command": "refresh", "binding": opened.binding}
    )
    assert refreshed.status == "prepared_review" and refreshed.ready
    assert refreshed.stale == refreshed.unresolved == 0


@pytest.mark.parametrize("kind,expected", (("identity", 1), ("rename", 0)))
def test_retired_producer_slot_counts_only_when_a_new_decision_is_required(
    tmp_path, request, kind, expected
):
    case = refresh_case(
        tmp_path, request, identity=kind == "identity", rename=kind == "rename"
    )
    prior = case.prepared.review.producer_facts
    assert (
        len(
            prior.association_decisions
            if kind == "identity"
            else prior.rename_decisions
        )
        == 1
    )
    path = NOTE if kind == "identity" else "Authored/Second.md"
    case.current[path] += b"Later distinct writing.\n"
    result = case.operations.refresh_update(case.prepared)
    assert result.preparation is not None
    facts = result.preparation.review.producer_facts
    assert not (
        facts.association_decisions if kind == "identity" else facts.rename_decisions
    )
    assert result.stale == expected
    assert result.preparation.review.approvals == case.prepared.review.approvals
    if kind == "identity":
        assert not result.ready and any(
            r.domain == "identity" for r in result.preparation.review.requirements
        )
    else:
        change = next(
            c
            for c in result.preparation.review.proposal.changes
            if c.rename_review is not None
        )
        assert (
            change.rename_review.status == "offered"
            and not change.rename_review.requires_decision
        )


def test_actual_refresh_count_survives_closed_worker_reads_and_cli_projection(
    tmp_path, request, monkeypatch, capsys
):
    from brz2obsidian.application.update_session import UpdateSession
    from brz2obsidian.cli import main
    from tests.gui.update_worker_fixture import ReviewWorkerTransport

    case = refresh_case(tmp_path, request)
    worker = ReviewWorkerTransport(case.operations)
    session = UpdateSession()
    session.select(case.prepared.vault, selection_id=str(uuid4()))

    def call(command, **values):
        operation = session.start({"command": command, **values})
        assert operation is not None
        terminal = worker.run(operation)
        return session.complete(operation.request_id, terminal)

    initial = call(
        "prepare",
        kind="source_update",
        source=str(tmp_path / "controlled.brz"),
        vault=case.prepared.vault,
        selection_id=session.snapshot.selection_id,
    )
    assert initial.ready
    case.current[NOTE] = note("Later Second writing.")
    refreshed = call("refresh", binding=initial.binding)
    assert refreshed.stale == 1 and not refreshed.ready
    actual = case.operations.refresh_update(case.prepared)
    for command in ("page", "choices"):
        observed = call(command, binding=session.snapshot.binding)
        assert observed.reply.status == "available"
        assert observed.reply.stale == 0
        assert observed.stale == 1 and not observed.ready
        assert observed.last_operation.stale == 1
    monkeypatch.setattr(
        "brz2obsidian.cli_review.Operations",
        lambda: SimpleNamespace(load_update=lambda vault: actual),
    )
    assert main(["review", "inspect", case.prepared.vault, "--json"]) == 2
    value = json.loads(capsys.readouterr().out)
    assert value["stale"] == value["unresolved"] == 1 and value["ready"] is False
    worker.close()
