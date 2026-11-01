"""Worker history actions consume shared native admission, never caller authority."""

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.application.vault_progress_contracts import VaultProgress
from tests.application.test_update_context import worker_context_call


@pytest.mark.parametrize("outcome", ("repaired", "unknown"))
def test_worker_repair_keeps_matching_target_and_native_object_storage_truth(
    tmp_path, outcome
):
    from brz2obsidian.application.operations import Operations
    from brz2obsidian.application.vault_repair_contracts import (
        HistoryCopyValidation,
        HistoryRepairPreparation,
        HistoryRepairResult,
        MissingHistoryObject,
    )
    from tests.application.test_history_workflow import absent_history, operation_state

    vault, copy = tmp_path / "vault", tmp_path / "local-copy"
    vault.mkdir()
    copy.mkdir()
    (vault / "Personal.md").write_bytes(b"Author stays exact\r\n")
    history = absent_history()
    repository = history.admission.repository.model_copy(
        update={
            "kind": "root",
            "root": str(vault),
            "git_directory": str(vault / ".git"),
            "common_directory": str(vault / ".git"),
            "object_directory": str(vault / ".git/objects"),
            "object_format": "sha1",
            "ref_format": "files",
        }
    )
    history = history.model_copy(
        update={
            "status": "unavailable",
            "admission": history.admission.model_copy(
                update={"repository": repository}
            ),
        }
    )
    observed = operation_state("unknown")
    validation = HistoryCopyValidation(
        schema_id="brz2obsidian.history-copy-validation",
        schema_version=1,
        status="matching",
        code="exact_missing_dependency",
        association_id="a" * 64,
        target_commit="3" * 40,
        copy_commit="3" * 40,
        target_generation=4,
        copy_generation=4,
        missing_objects=(
            MissingHistoryObject(object_id="e" * 40, size=7, sha256="b" * 64),
        ),
        message="One qualified retained object is missing.",
    )
    native = HistoryRepairPreparation(
        schema_id="brz2obsidian.history-repair-preparation",
        schema_version=1,
        status="prepared",
        code="repair_prepared",
        validation=validation,
        target_anchor="qualified-target",
        target_git_anchor="qualified-target-git",
        copy_anchor="qualified-copy",
        copy_git_anchor="qualified-copy-git",
        target_snapshot="c" * 64,
        copy_snapshot="d" * 64,
        message="Matching native object repair prepared.",
    )
    result = HistoryRepairResult(
        schema_id="brz2obsidian.history-repair-result",
        schema_version=1,
        status=outcome,
        code="native_" + outcome,
        history_retained=outcome == "repaired",
        object_storage="verified" if outcome == "repaired" else "possible",
        objects_written=1,
        authored_files_changed=False,
        message="Actual native object-storage outcome.",
    )
    calls = []

    class NativePorts(Operations):
        def inspect_history(self, path, **kwargs):
            return history

        def inspect_update_status(self, path):
            return observed

        def validate_history_copy(self, path, candidate):
            assert Path(path) == vault and Path(candidate) == copy
            calls.append("validate")
            return validation

        def prepare_history_repair(self, path, candidate, checked):
            assert checked == validation and Path(candidate) == copy
            calls.append("prepare")
            return native

        def execute_history_repair(
            self, path, candidate, preparation, *, progress=None
        ):
            assert progress is not None, (
                "Native repair observer must survive the shared workflow"
            )
            progress(
                VaultProgress(
                    phase="final_reporting",
                    completed_units=1 if outcome == "repaired" else None,
                    unit="history_objects" if outcome == "repaired" else None,
                )
            )
            assert preparation == native and Path(candidate) == copy
            calls.append("execute")
            return result

    context = UpdateContext(operations=NativePorts())
    offered = worker_context_call(
        context,
        {
            "command": "history",
            "vault": str(vault),
            "selection_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    assert (
        "review_history_repair" in offered.next_actions
        and offered.binding.operation_id is None
    )
    assert offered.changes == 0
    prepared = worker_context_call(
        context,
        {
            "command": "prepare_history",
            "binding": offered.binding,
            "kind": "repair",
            "copy_path": str(copy),
        },
    )
    assert (
        prepared.ready
        and prepared.binding.proposal_id is None
        and prepared.binding.review_generation is None
    )
    assert prepared.binding.operation_generation is None
    assert prepared.changes == 0
    assert (
        prepared.binding.association_id == "a" * 64
        and prepared.binding.checkpoint_commit == "3" * 40
        and prepared.binding.checkpoint_generation == 4
    )
    assert (
        prepared.history_action.copy_validation.status == "matching"
        and prepared.history_action.copy_validation.missing_objects == 1
    )
    assert calls == ["validate", "prepare"]
    completed = worker_context_call(
        context, {"command": "execute_history", "binding": prepared.binding}
    )
    assert completed.status == outcome and completed.status not in (
        "applied",
        "restored",
    )
    assert (
        completed.history_action.repair == result
        and completed.history_action.operation is None
    )
    assert (
        completed.history_retained is result.history_retained
        and completed.binding is None
        and not completed.ready
    )
    assert (
        completed.history_action.repair.object_storage == result.object_storage
        and not completed.history_action.repair.authored_files_changed
    )
    assert calls == ["validate", "prepare", "execute"]
    assert (vault / "Personal.md").read_bytes() == b"Author stays exact\r\n" and list(
        copy.iterdir()
    ) == []


def test_worker_resolves_canonical_history_current_offer_without_exporting_plan(
    tmp_path,
):
    from brz2obsidian.application.operations import Operations
    from brz2obsidian.application.vault_recovery_contracts import (
        VaultRecoveryPreparation,
    )
    from brz2obsidian.application.vault_update_contracts import VaultApplyResult
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
    from tests.application.test_history_workflow import absent_history, operation_state
    from tests.reconciliation.test_resolution import preflight
    from tests.reconciliation.test_reversal_absence import reversal_facts

    facts = reversal_facts(current=b"created\r\nLater writing\r\n")
    subject = facts.subjects[0]
    proof = subject.operation_reversal.model_copy(
        update={"operation_id": "1" * 32, "operation_generation": 7}
    )
    facts = facts.model_copy(
        update={
            "generation": 3,
            "subjects": (subject.model_copy(update={"operation_reversal": proof}),),
        }
    )
    plan = prepare_review(facts, preflight=preflight())
    assert not plan.ready and len(plan.requirements) == 1
    assert (
        plan.requirements[0].domain == "reversal"
        and "current" in plan.requirements[0].choices
    )
    native = VaultRecoveryPreparation(
        schema_id="brz2obsidian.vault-recovery-preparation",
        schema_version=1,
        status="offered",
        code="recovery_offered",
        operation_id="1" * 32,
        kind="apply",
        generation=7,
        intent_commit="2" * 40,
        available_directions=("restore",),
        direction="restore",
        review=plan,
    )
    observed = operation_state("incomplete").model_copy(
        update={"direction": "restore", "origin_role": "source_update"}
    )
    completed = VaultApplyResult.model_validate(
        observed.model_dump()
        | {
            "status": "restored",
            "code": "recovery_restored",
            "generation": 8,
            "review_generation": 3,
            "phase": "terminal",
            "publication": "complete",
            "history": "terminal",
            "planned_files": 0,
            "published_files": 0,
            "authored_files_changed": False,
            "checkpoint_commit": "3" * 40,
            "result_commit": "4" * 40,
            "receipt_commit": "5" * 40,
            "recovery_required": False,
        }
    )
    calls = []

    class NativePorts(Operations):
        def inspect_history(self, vault, **kwargs):
            return absent_history()

        def inspect_update_status(self, vault):
            return observed

        def prepare_recovery(self, vault, *, direction=None):
            assert direction == "restore"
            return native

        def resolve_recovery(self, vault, preparation, action):
            calls.append(action)
            transition = resolve_review(preparation.review, action)
            assert transition.status == "accepted", transition.code
            return preparation.model_copy(
                update={"review": transition.plan, "code": "recovery_choice_recorded"}
            )

        def execute_recovery(self, vault, preparation, *, cancel=None, progress=None):
            effects = select_review_effects(preparation.review)
            assert effects.status == "selected" and effects.remove_paths == ()
            assert [(row.path, row.content.data) for row in effects.files] == [
                ("Notes/Opening.md", b"created\r\nLater writing\r\n")
            ]
            return completed

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Personal.md").write_bytes(b"Exact personal bytes\r\n")
    context = UpdateContext(operations=NativePorts())
    offered = worker_context_call(
        context,
        {
            "command": "history",
            "vault": str(vault),
            "selection_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    prepared = worker_context_call(
        context,
        {
            "command": "prepare_history",
            "binding": offered.binding,
            "kind": "recovery",
            "direction": "restore",
        },
    )
    assert not prepared.ready and prepared.unresolved == 1
    assert prepared.changes == 1, "The one review row counts before any publication"
    comparison = worker_context_call(
        context,
        {"command": "page", "binding": prepared.binding, "limit": 1},
    )
    assert comparison.page.total == 1 and comparison.page.next_offset is None
    assert comparison.changes == 1
    assert comparison.page.generation == 3
    row = comparison.page.items[0]
    assert (row.original, row.current, row.incoming, row.result) == (
        b"created\r\n",
        b"created\r\nLater writing\r\n",
        None,
        None,
    )
    bounded = worker_context_call(
        context,
        {"command": "page", "binding": prepared.binding, "limit": 1, "byte_limit": 4},
    )
    row = bounded.page.items[0]
    assert (row.original, row.current, row.incoming, row.result) == (
        b"cr",
        b"cr",
        None,
        None,
    )
    assert row.next_byte_offset == 2 and row.omitted and bounded.page.omitted
    assert comparison.binding == bounded.binding == prepared.binding
    assert bounded.changes == 1
    choices = worker_context_call(
        context, {"command": "history_choices", "binding": prepared.binding, "limit": 1}
    )
    assert choices.total_choices == 1 and choices.next_choice_offset is None
    assert choices.changes == 1
    offer = choices.offers[0]
    assert offer.domain == "reversal" and "current" in offer.choices
    wire = choices.model_dump_json()
    assert "producer_facts" not in wire and "link_context" not in wire
    wrong = worker_context_call(
        context,
        {
            "command": "choose_history",
            "binding": prepared.binding,
            "requirement_id": offer.requirement_id,
            "choice": "current",
            "assumptions_digest": "0" * 64,
        },
    )
    assert wrong.status == "refused" and wrong.code == "offer_changed" and not calls
    assert wrong.changes == 1, "A refused choice retains the existing review total"
    chosen = worker_context_call(
        context,
        {
            "command": "choose_history",
            "binding": prepared.binding,
            "requirement_id": offer.requirement_id,
            "choice": "current",
            "assumptions_digest": offer.assumptions_digest,
        },
    )
    assert chosen.ready and chosen.binding.review_generation == 3 and len(calls) == 1
    assert chosen.changes == 1 and chosen.unresolved == 0
    stale_page = worker_context_call(
        context,
        {"command": "page", "binding": prepared.binding},
    )
    assert stale_page.status == "refused" and stale_page.code == "context_changed"
    assert stale_page.changes == 1
    stale = worker_context_call(
        context,
        {
            "command": "choose_history",
            "binding": prepared.binding,
            "requirement_id": offer.requirement_id,
            "choice": "current",
            "assumptions_digest": offer.assumptions_digest,
        },
    )
    assert stale.status == "refused" and len(calls) == 1
    assert stale.changes == 1
    result = worker_context_call(
        context, {"command": "execute_history", "binding": chosen.binding}
    )
    assert result.status == "restored" and result.history_action.operation == completed
    assert result.changes == 0 and result.binding is None
    assert completed.planned_files == completed.published_files == 0
    assert (vault / "Personal.md").read_bytes() == b"Exact personal bytes\r\n"


def test_worker_history_original_incoming_keeps_home_current_and_manual_reverse(
    tmp_path,
):
    """A fresh canonical review crosses the worker; storage is a declared port."""
    from hashlib import sha256

    from brz2obsidian.application.operations import Operations
    from brz2obsidian.application.review_choices import (
        requirement_digest,
        review_plan_attachment_references,
        review_plan_choice_action,
    )
    from brz2obsidian.application.update_lifecycle import text_choice_action
    from brz2obsidian.application.vault_undo_contracts import VaultUndoPreparation
    from brz2obsidian.application.vault_update_contracts import VaultApplyResult
    from brz2obsidian.contracts import (
        AttachmentFacts,
        ContentVersion,
        CurrentContent,
        ExactContent,
        IdentityInventoryItem,
        OperationReversalOutput,
        OperationReversalTarget,
        ReconciliationSubject,
    )
    from brz2obsidian.core import (
        inspect_review_choices,
        prepare_review,
        resolve_review,
        select_review_effects,
    )
    from brz2obsidian.core.reversals import review_owned_documents
    from brz2obsidian.obsidian import interpret_link_target, interpret_links
    from tests.application.test_history_workflow import (
        intact_local_history,
        operation_state,
    )
    from tests.application.test_vault_undo import _with_unassociated_manual
    from tests.reconciliation.test_attachments import target_for_links
    from tests.reconciliation.test_identity import inventory_item, with_subjects
    from tests.reconciliation.test_proposals import request
    from tests.reconciliation.test_resolution import preflight, with_review_links

    home_before = b"Home before.\n"
    home_produced = b"Home incoming.\n"
    home_later = b"Home incoming.\nIndependent later Home writing.\n"
    original_before = (
        b"First source writing.\n# Shared heading\nOriginal block. ^original\n"
    )
    original_produced = (
        b"Second source writing.\n# Shared heading\nChanged block. ^original\n"
    )
    original_path = "Attachments/opening/Notes.md.original"
    original_target_id = "subject:entry:original:asset"
    manual_before = (
        b"[[Assets/data.bin|Keep first]] and [[Assets/data.bin|Redirect second]]"
    )
    manual_produced = (
        b"[[Assets/data.bin|Keep first]] and "
        b"[[Assets/data (incoming-ba7816bf).bin|Redirect second]]"
    )
    facts = with_review_links(
        request(original=home_before, current=home_before, incoming=home_produced)
    )
    facts = _with_unassociated_manual(facts, manual_before)
    home, linked = facts.subjects
    resource_entry = inventory_item(
        "original-entry",
        "entry:original",
        original_path,
        original_before,
        facet="asset",
    )
    resource = home.model_copy(
        update={
            "item_id": "entry:original",
            "facet": "asset",
            "path": original_path,
            "title": "Original source evidence",
            "baseline": home.baseline.model_copy(
                update={"content": ExactContent(data=original_before)}
            ),
            "current": resource_entry.current,
            "incoming": ExactContent(data=original_produced),
            "interpretation": "opaque",
            "source_target": resource_entry.target,
            "output_role": "guide",
            "attachment": AttachmentFacts(
                current_target_id=original_target_id,
                affected_documents=(),
                allocation_candidates=(),
            ),
        }
    )
    facts = with_subjects(
        facts, (*facts.subjects, resource), (*facts.identity_inventory, resource_entry)
    )
    context = facts.link_context
    resource_target = target_for_links(
        original_target_id, original_path, kind="resource"
    )
    additions = {}
    for stage, raw in (("current", original_before), ("incoming", original_produced)):
        additions[stage + "_targets"] = (
            *getattr(context, stage + "_targets"),
            resource_target,
        )
        additions[stage + "_target_facts"] = (
            *getattr(context, stage + "_target_facts"),
            interpret_link_target(
                ExactContent(data=raw),
                target_id=original_target_id,
                existence="present",
                memberships=(),
                source_path=original_path,
            ),
        )
    facts = facts.model_copy(
        update={"link_context": context.model_copy(update=additions)}
    )
    origin = prepare_review(facts, preflight=preflight())

    def origin_choice(plan, path, choice, references=()):
        change = next(c for c in plan.proposal.changes if c.path == path)
        offered = next(
            o for o in inspect_review_choices(plan) if o.change_id == change.change_id
        )
        action = review_plan_choice_action(
            plan,
            requirement_id=offered.requirement_id,
            choice=choice,
            assumptions_digest=requirement_digest(offered),
            references=references,
        )
        result = resolve_review(plan, text_choice_action(plan, action))
        assert result.status == "accepted", result.code
        return result.plan

    # The distinct linked binary creates real canonical changed-document ownership.
    binary_change = next(c for c in origin.proposal.changes if c.path == linked.path)
    binary_offer = next(
        o
        for o in inspect_review_choices(origin)
        if o.change_id == binary_change.change_id
    )
    refs = review_plan_attachment_references(origin, binary_offer.requirement_id)
    assert len(refs) == 2 and all(d.source_path == "Manual.md" for _, d, _ in refs)
    origin = origin_choice(
        origin,
        linked.path,
        "both",
        tuple(
            {"reference_id": token, "choice": choice}
            for (token, _, _), choice in zip(
                refs, ("keep_current", "use_secondary"), strict=True
            )
        ),
    )
    origin = origin_choice(origin, home.path, "incoming")
    origin = origin_choice(origin, original_path, "incoming")
    assert origin.ready and not origin.blockers
    effects = select_review_effects(origin)
    assert effects.status == "selected" and effects.remove_paths == ()
    produced = {f.path: f.content for f in effects.files}
    assert produced[home.path].data == home_produced
    assert produced[original_path].data == original_produced
    assert produced["Manual.md"].data == manual_produced != manual_before
    owned = review_owned_documents(origin)
    assert len(owned) == 1
    origin_change, origin_decision, manual_target = owned[0]
    assert (
        manual_target.canonical_path == "Manual.md" and manual_target.identity is None
    )
    assert (origin_change, origin_decision) == (
        binary_change.change_id,
        next(
            a.decision_id
            for a in origin.approvals
            if a.change_id == binary_change.change_id
        ),
    )

    # Observe only fresh in-memory fixture bytes. No physical history is manufactured.
    targets = next(
        a.attachment_candidate.targets
        for a in origin.approvals
        if a.change_id == binary_change.change_id
    )
    current = {path: raw for path, raw in produced.items()}
    current[home.path] = ExactContent(data=home_later)
    states = tuple(
        interpret_link_target(
            current[t.canonical_path],
            target_id=t.target_id,
            existence="present",
            memberships=(),
            source_path=t.canonical_path,
        )
        for t in targets
    )
    reverse_bytes = {
        home.path: ExactContent(data=home_before),
        original_path: ExactContent(data=original_before),
        "Manual.md": ExactContent(data=manual_before),
    }
    incoming_states = tuple(
        interpret_link_target(
            reverse_bytes.get(t.canonical_path, current[t.canonical_path]),
            target_id=t.target_id,
            existence="present",
            memberships=(),
            source_path=t.canonical_path,
        )
        for t in targets
    )
    document_rows = {}
    for stage, versions, stage_states in (
        ("current", current, states),
        ("incoming", reverse_bytes, incoming_states),
    ):
        document_rows[stage + "_documents"] = tuple(
            interpret_links(
                versions[t.canonical_path],
                document_id=t.target_id,
                source_path=t.canonical_path,
                path_mode="vault",
                targets=targets,
                target_facts=stage_states,
                inventory="complete",
            )
            for t in targets
            if t.kind == "note"
        )
    observed = tuple(
        entry.model_copy(
            update={
                "current": entry.current.model_copy(
                    update={"content": current[entry.current.path]}
                )
            }
        )
        for entry in facts.identity_inventory
    )
    extra = next(
        t for t in targets if t.canonical_path == "Assets/data (incoming-ba7816bf).bin"
    )
    observed += (
        IdentityInventoryItem(
            entry_id="physical:secondary",
            facet=None,
            identity_state="missing",
            identity=None,
            raw_identity=None,
            title="Secondary resource",
            current=CurrentContent(
                existence="present",
                path=extra.canonical_path,
                content=current[extra.canonical_path],
            ),
            target=extra.target,
        ),
    )
    manual_entry = next(e for e in observed if e.current.path == "Manual.md")
    assert manual_entry.identity is None and manual_entry.raw_identity is None
    proof = OperationReversalTarget(
        schema_id="brz2obsidian.operation-reversal-target",
        schema_version=1,
        operation_id="1" * 32,
        operation_kind="apply",
        direction="restore",
        operation_generation=1,
        history_fingerprint=sha256(origin.model_dump_json().encode()).hexdigest(),
        origin_change_id=origin_change,
        origin_decision_id=origin_decision,
        owned_targets=(manual_target,),
        outputs=(
            OperationReversalOutput(
                path="Manual.md",
                target_id=manual_target.target_id,
                produced_existence="present",
                produced=produced["Manual.md"],
                current=manual_entry.current,
                target_existence="present",
                target=ExactContent(data=manual_before),
            ),
        ),
    )
    manual = ReconciliationSubject(
        item_id=manual_target.target_id,
        facet="content",
        path="Manual.md",
        baseline=ContentVersion(
            status="unknown", content=None, unavailable_digest=None
        ),
        current=manual_entry.current,
        incoming=ExactContent(data=manual_before),
        interpretation="supported",
        title="Manual",
        source_target=manual_target.target,
        output_role="note",
        structure=None,
        attachment=None,
        operation_reversal=proof,
    )
    undo_subjects = tuple(
        s.model_copy(
            update={
                "baseline": s.baseline.model_copy(update={"content": produced[s.path]}),
                "current": next(
                    e.current for e in observed if e.current.path == s.path
                ),
                "incoming": reverse_bytes[s.path],
            }
        )
        for s in (home, resource)
    ) + (
        linked.model_copy(
            update={
                "baseline": linked.baseline.model_copy(
                    update={"content": linked.incoming}
                ),
                "current": next(
                    e.current for e in observed if e.current.path == linked.path
                ),
            }
        ),
        manual,
    )
    undo_facts = with_subjects(facts, undo_subjects, observed)
    undo_facts = undo_facts.model_copy(
        update={
            "link_context": context.model_copy(
                update={
                    "current_targets": targets,
                    "incoming_targets": targets,
                    "current_target_facts": states,
                    "incoming_target_facts": incoming_states,
                    **document_rows,
                }
            )
        }
    )
    review = prepare_review(undo_facts, preflight=preflight())
    assert not review.ready and not review.blockers and len(review.requirements) == 3
    protected_asset = next(c for c in review.proposal.changes if c.path == linked.path)
    assert not protected_asset.requires_decision
    assert tuple(
        version.data
        for version in (
            protected_asset.original,
            protected_asset.current,
            protected_asset.incoming,
            protected_asset.result,
        )
    ) == (b"abc", b"\x00authored", b"abc", b"\x00authored")
    native = VaultUndoPreparation(
        schema_id="brz2obsidian.vault-undo-preparation",
        schema_version=1,
        status="offered",
        code="undo_offered",
        checkpoint_commit="3" * 40,
        generation=2,
        target_receipt_commit="4" * 40,
        review=review,
    )
    history = intact_local_history()
    history = history.model_copy(
        update={
            "checkpoint": history.checkpoint.model_copy(
                update={
                    "locator": history.checkpoint.locator.model_copy(
                        update={"commit": "3" * 40, "generation": 2}
                    ),
                    "manifest": history.checkpoint.manifest.model_copy(
                        update={
                            "generation": 2,
                            "boundary": "result",
                            "previous": "1" * 40,
                            "operation_intent_commit": "2" * 40,
                        }
                    ),
                }
            )
        }
    )
    operation = VaultApplyResult.model_validate(
        operation_state("incomplete").model_dump()
        | {
            "status": "applied",
            "code": "operation_terminal",
            "generation": 1,
            "phase": "terminal",
            "publication": "complete",
            "history": "terminal",
            "checkpoint_commit": "1" * 40,
            "result_commit": "3" * 40,
            "receipt_commit": "4" * 40,
            "recovery_required": False,
            "origin_role": "source_update",
        }
    )
    resolved = []

    class NativePorts(Operations):
        # Declared physical storage boundary only; real compilation/Core resolution.
        def inspect_history(self, vault, **kwargs):
            return history

        def inspect_update_status(self, vault):
            return operation

        def prepare_undo(self, vault, *, previous=None):
            return native

        def resolve_undo(self, vault, preparation, action):
            import traceback

            diagnostic = {"domain": action.domain, "choice": action.choice}
            try:
                transition = resolve_review(preparation.review, action)
                diagnostic.update(status=transition.status, code=transition.code)
                assert transition.status == "accepted", transition.code
                result = VaultUndoPreparation.model_validate(
                    preparation.model_dump()
                    | {"review": transition.plan, "code": "undo_choice_recorded"}
                )
            except Exception:
                diagnostic["traceback"] = traceback.format_exc()
                destination = (
                    Path(__file__).resolve().parents[2]
                    / "tmp/issue307/storage-port-diagnostic002.json"
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("x", encoding="utf-8") as output:
                    json.dump(diagnostic, output, ensure_ascii=True, indent=2)
                raise
            resolved.append(result)
            return result

        def execute_undo(self, *args, **kwargs):
            raise AssertionError("Choosing an original must never publish")

    vault = tmp_path / "vault"
    vault.mkdir()
    for path, content in current.items():
        output = vault / path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content.data)
    (vault / "Personal.bin").write_bytes(b"Protected\x00\xff\r\n")

    def physical():
        return {
            p.relative_to(vault).as_posix(): p.read_bytes()
            for p in vault.rglob("*")
            if p.is_file()
        }

    before = physical()
    context = UpdateContext(operations=NativePorts())
    opened = worker_context_call(
        context,
        {
            "command": "history",
            "vault": str(vault),
            "selection_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    assert "review_undo" in opened.next_actions
    prepared = worker_context_call(
        context,
        {
            "command": "prepare_history",
            "binding": opened.binding,
            "kind": "undo",
        },
    )
    assert (
        prepared.status == "prepared_review"
        and prepared.changes == 4
        and prepared.unresolved == 3
    )

    def public_offer(binding, path):
        page = worker_context_call(context, {"command": "page", "binding": binding})
        row = next(r for r in page.page.items if r.current_path == path)
        choices = worker_context_call(
            context, {"command": "history_choices", "binding": binding}
        )
        assert choices.status == "available" and choices.binding == binding
        return next(o for o in choices.offers if o.change_id == row.change_id)

    for path, choice, domain in (
        (home.path, "current", "text"),
        ("Manual.md", "reverse", "reversal"),
    ):
        offer = public_offer(prepared.binding, path)
        assert offer.domain == domain and choice in offer.choices
        prepared = worker_context_call(
            context,
            {
                "command": "choose_history",
                "binding": prepared.binding,
                "requirement_id": offer.requirement_id,
                "choice": choice,
                "assumptions_digest": offer.assumptions_digest,
            },
        )
        assert prepared.status == "prepared_review", prepared.code
    assert prepared.changes == 4 and prepared.unresolved == 1
    retained = tuple(resolved[-1].review.approvals)
    offer = public_offer(prepared.binding, original_path)
    assert offer.domain == "attachment" and "incoming" in offer.choices
    details = worker_context_call(
        context,
        {
            "command": "choice_details",
            "binding": prepared.binding,
            "requirement_id": offer.requirement_id,
        },
    )
    assert details.status == "available" and details.binding == prepared.binding
    assert {
        (d.choice, d.path, d.target_id, d.size, d.sha256)
        for d in details.choice_details
    } == {
        (
            "current",
            original_path,
            original_target_id,
            len(original_produced),
            sha256(original_produced).hexdigest(),
        ),
        (
            "incoming",
            original_path,
            original_target_id,
            len(original_before),
            sha256(original_before).hexdigest(),
        ),
    }
    references = worker_context_call(
        context,
        {
            "command": "references",
            "binding": prepared.binding,
            "requirement_id": offer.requirement_id,
        },
    )
    assert references.status == "available" and references.binding == prepared.binding
    assert references.references == () and references.total_references == 0
    assert references.next_reference_offset is None
    chosen = worker_context_call(
        context,
        {
            "command": "choose_history",
            "binding": prepared.binding,
            "requirement_id": offer.requirement_id,
            "choice": "incoming",
            "assumptions_digest": offer.assumptions_digest,
        },
    )
    assert chosen.status == "prepared_review", chosen.code
    assert chosen.ready and chosen.changes == 4 and chosen.unresolved == 0
    assert chosen.binding.proposal_id == prepared.binding.proposal_id
    assert chosen.binding.revision > prepared.binding.revision
    assert chosen.binding.review_generation >= prepared.binding.review_generation
    final = resolved[-1].review
    assert all(approval in final.approvals for approval in retained)
    assert {(a.domain, a.choice) for a in final.approvals} == {
        ("text", "current"),
        ("reversal", "reverse"),
        ("attachment", "incoming"),
    }
    selected = select_review_effects(final)
    assert selected.status == "selected" and selected.remove_paths == ()
    selected_bytes = {f.path: f.content.data for f in selected.files}
    assert selected_bytes[home.path] == home_later
    assert selected_bytes["Manual.md"] == manual_before
    assert selected_bytes[original_path] == original_before
    assert selected_bytes[linked.path] == b"\x00authored"
    assert before[extra.canonical_path] == b"abc"
    assert physical() == before


def test_worker_real_undo_original_incoming_retains_home_and_manual(tmp_path):
    _worker_real_undo_original_case(tmp_path)


def test_worker_real_undo_created_memberships_allow_original_incoming(tmp_path):
    _worker_real_undo_original_case(tmp_path, with_created_memberships=True)


def _worker_real_undo_original_case(tmp_path, *, with_created_memberships=False):
    """One fresh physical graph supplies every actual Undo producer response."""
    from hashlib import sha256

    from brz2obsidian.application.operations import Operations
    from tests.application.test_vault_checkpoints import user_state
    from tests.application.test_vault_undo import _unassociated_reference_update

    _operations, vault, source, applied, manual_before, manual_produced, _ = (
        _unassociated_reference_update(
            with_original=True, with_created_memberships=with_created_memberships
        )
    )
    assert applied.status == "applied" and applied.publication == "complete"
    original_path = "Attachments/opening/Notes.md.original"
    original_before = b"First source writing.\n# Shared heading\nOld block. ^original\n"
    original_produced = (
        b"Second source writing.\n# Shared heading\nNew block. ^original\n"
    )
    later_home = b"opening incoming\nLater independent Home writing.\n"
    assert (vault / original_path).read_bytes() == original_produced
    (vault / "Notes/Opening.md").write_bytes(later_home)
    expected_authored = {
        "Notes/Opening.md": later_home,
        "Notes/Closing.md": b"closing incoming\n",
        "Manual.md": (
            b"[[Assets/data.bin|Keep first]] and "
            b"[Second edited alias](Assets/data%20%28incoming-ba7816bf%29.bin)"
        ),
        "Assets/data.bin": b"\x00authored",
        "Assets/data (incoming-ba7816bf).bin": b"abc",
        "Unrelated.bin": b"protected\x00\xff",
        original_path: original_produced,
    }
    if with_created_memberships:
        expected_authored.update(
            {
                "Categories/Review category.md": (
                    b'---\nsource_collection_id: "folio:collection"\n'
                    b'source_item_id: "definition:review-category"\ntags:\n  - categories\n'
                    b"---\n# Review category\n"
                ),
                "Templates/Review category.md": (
                    b'---\nsource_collection_id: "folio:collection"\n'
                    b'source_item_id: "support:Templates/Review category.md"\n'
                    b'categories:\n  - "[[Categories/Review category.md]]"\n'
                    b"---\n# New member\n"
                ),
            }
        )
    assert user_state(vault)["authored"] == expected_authored
    assert (
        manual_before
        == b"[[Assets/data.bin|Keep first]] and [[Assets/data.bin|Redirect second]]"
    )
    assert (vault / "Manual.md").read_bytes() == manual_produced

    def preservation():
        return {
            "user": user_state(vault),
            "locator": (vault / ".brz2obsidian/locator.json").read_bytes(),
            "source": {
                p.relative_to(source).as_posix(): p.read_bytes()
                for p in source.rglob("*")
                if p.is_file()
            },
        }

    before = preservation()
    preparations = []

    class ObservedOperations(Operations):
        # Only observe public return values; the real storage producer runs unchanged.
        def prepare_undo(self, path, *, previous=None):
            result = super().prepare_undo(path, previous=previous)
            preparations.append(result)
            (tmp_path / f"real-preparation-{len(preparations)}.json").write_text(
                result.model_dump_json(), encoding="utf-8"
            )
            return result

        def resolve_undo(self, path, preparation, action):
            result = super().resolve_undo(path, preparation, action)
            preparations.append(result)
            (tmp_path / f"real-preparation-{len(preparations)}.json").write_text(
                result.model_dump_json(), encoding="utf-8"
            )
            return result

    context = UpdateContext(operations=ObservedOperations())
    opened = worker_context_call(
        context,
        {
            "command": "history",
            "vault": str(vault),
            "selection_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    assert "review_undo" in opened.next_actions
    prepared = worker_context_call(
        context,
        {
            "command": "prepare_history",
            "binding": opened.binding,
            "kind": "undo",
        },
    )
    assert prepared.status == "prepared_review", prepared.code
    total = 7 if with_created_memberships else 5
    assert prepared.changes == total and prepared.unresolved == total
    assert preparations[-1].status == "offered"
    assert prepared.binding.target_receipt_commit == applied.receipt_commit
    if with_created_memberships:
        facts = preparations[-1].review.producer_facts
        paths = {"Categories/Review category.md", "Templates/Review category.md"}
        observed_memberships = []
        for path, item_id in (
            ("Categories/Review category.md", "definition:review-category"),
            ("Templates/Review category.md", "support:Templates/Review category.md"),
        ):
            entry = next(e for e in facts.identity_inventory if e.current.path == path)
            assert entry.identity.item_id == item_id
            assert entry.current.content.data == expected_authored[path]
        for target in facts.link_context.current_targets:
            if target.canonical_path not in paths:
                continue
            state = next(
                s
                for s in facts.link_context.current_target_facts
                if s.target_id == target.target_id
            )
            observed_memberships.append(
                {
                    "path": target.canonical_path,
                    "target_id": target.target_id,
                    "memberships": state.memberships,
                    "structure_memberships": None
                    if state.structure is None
                    else [
                        (m.field_key, [e.target_id for e in m.entries])
                        for m in state.structure.memberships
                    ],
                }
            )
        (tmp_path / "actual-undo-memberships.json").write_text(
            json.dumps(observed_memberships, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
    assert preservation() == before

    def public_offer(binding, path):
        page = worker_context_call(context, {"command": "page", "binding": binding})
        assert page.status == "available" and page.binding == binding
        row = next(r for r in page.page.items if r.current_path == path)
        choices = worker_context_call(
            context, {"command": "history_choices", "binding": binding}
        )
        assert choices.status == "available" and choices.binding == binding
        return next(o for o in choices.offers if o.change_id == row.change_id)

    for path, choice, domain in (
        ("Notes/Opening.md", "current", "text"),
        ("Manual.md", "reverse", "reversal"),
    ):
        offer = public_offer(prepared.binding, path)
        assert offer.domain == domain and choice in offer.choices
        prepared = worker_context_call(
            context,
            {
                "command": "choose_history",
                "binding": prepared.binding,
                "requirement_id": offer.requirement_id,
                "choice": choice,
                "assumptions_digest": offer.assumptions_digest,
            },
        )
        assert prepared.status == "prepared_review", prepared.code
        assert preservation() == before
    assert prepared.changes == total and prepared.unresolved == total - 2
    retained = tuple(preparations[-1].review.approvals)
    assert {(a.domain, a.choice) for a in retained} == {
        ("text", "current"),
        ("reversal", "reverse"),
    }
    assert {a.target_path: a.result.data for a in retained} == {
        "Notes/Opening.md": later_home,
        "Manual.md": manual_before,
    }
    offer = public_offer(prepared.binding, original_path)
    assert offer.domain == "attachment" and "incoming" in offer.choices
    details = worker_context_call(
        context,
        {
            "command": "choice_details",
            "binding": prepared.binding,
            "requirement_id": offer.requirement_id,
        },
    )
    assert details.status == "available" and details.binding == prepared.binding
    assert {
        (d.choice, d.path, d.target_id, d.size, d.sha256)
        for d in details.choice_details
    } == {
        (
            "current",
            original_path,
            "subject:entry:original:asset",
            len(original_produced),
            sha256(original_produced).hexdigest(),
        ),
        (
            "incoming",
            original_path,
            "subject:entry:original:asset",
            len(original_before),
            sha256(original_before).hexdigest(),
        ),
    }
    references = worker_context_call(
        context,
        {
            "command": "references",
            "binding": prepared.binding,
            "requirement_id": offer.requirement_id,
        },
    )
    assert references.status == "available" and references.binding == prepared.binding
    assert references.references == () and references.total_references == 0
    assert references.next_reference_offset is None
    assert preservation() == before
    chosen = worker_context_call(
        context,
        {
            "command": "choose_history",
            "binding": prepared.binding,
            "requirement_id": offer.requirement_id,
            "choice": "incoming",
            "assumptions_digest": offer.assumptions_digest,
        },
    )
    assert preservation() == before
    assert chosen.status == "prepared_review", chosen.code
    assert (
        chosen.changes == total and chosen.unresolved == total - 3 and not chosen.ready
    )
    assert chosen.binding.target_receipt_commit == applied.receipt_commit
    assert chosen.binding.checkpoint_commit == prepared.binding.checkpoint_commit
    assert chosen.binding.revision > prepared.binding.revision
    assert chosen.binding.review_generation >= prepared.binding.review_generation
    final = preparations[-1].review
    assert all(approval in final.approvals for approval in retained)
    selected = next(a for a in final.approvals if a.target_path == original_path)
    assert selected.domain == "attachment" and selected.choice == "incoming"
    assert selected.source_accepted and selected.result.data == original_before
    assert [
        (o.path, o.content.data) for o in selected.attachment_candidate.outputs
    ] == [(original_path, original_before)]
    if with_created_memberships:
        facts = final.producer_facts
        expected_memberships = {
            "Categories/Review category.md": ("format:7:categories",),
            "Templates/Review category.md": (
                "subject:definition:review-category:content",
            ),
        }
        for path, memberships in expected_memberships.items():
            target = next(
                t
                for t in facts.link_context.current_targets
                if t.canonical_path == path
            )
            state = next(
                s
                for s in facts.link_context.current_target_facts
                if s.target_id == target.target_id
            )
            assert state.memberships == memberships
            assert (
                tuple(
                    e.target_id for m in state.structure.memberships for e in m.entries
                )
                == memberships
            )
            assert state.content.data == expected_authored[path]
    assert preservation() == before


def test_worker_history_refresh_counts_the_new_review_scope(tmp_path):
    from brz2obsidian.application.operations import Operations
    from brz2obsidian.core import prepare_review, select_review_effects
    from tests.application.test_history_workflow import (
        absent_history,
        operation_state,
        ready_native_recovery,
    )
    from tests.reconciliation.test_identity import inventory_item, with_subjects
    from tests.reconciliation.test_resolution import preflight, with_review_links

    original = ready_native_recovery().native
    facts = original.review.facts
    second_entry = inventory_item(
        "second-entry", "entry:second", "Notes/Second.md", b"Second retained\n"
    )
    first_subject = facts.subjects[0]
    second_subject = first_subject.model_copy(
        update={
            "item_id": "entry:second",
            "path": "Notes/Second.md",
            "title": "Second",
            "baseline": first_subject.baseline.model_copy(
                update={"content": second_entry.current.content}
            ),
            "current": second_entry.current,
            "incoming": second_entry.current.content,
            "source_target": second_entry.target,
        }
    )
    renewed_facts = with_review_links(
        with_subjects(
            facts.model_copy(update={"generation": 4, "link_context": None}),
            (first_subject, second_subject),
            facts.identity_inventory + (second_entry,),
        )
    )
    renewed = original.model_copy(
        update={"review": prepare_review(renewed_facts, preflight=preflight())}
    )
    assert original.review.ready and renewed.review.ready
    effects = select_review_effects(renewed.review)
    assert effects.status == "selected" and effects.remove_paths == ()
    assert [(row.path, row.content.data) for row in effects.files] == [
        ("Notes/Opening.md", b"retained"),
        ("Notes/Second.md", b"Second retained\n"),
    ]

    class NativePorts(Operations):
        def inspect_history(self, vault, **kwargs):
            return absent_history()

        def inspect_update_status(self, vault):
            return operation_state("incomplete")

        def prepare_recovery(self, vault, *, direction=None):
            assert direction == "finish"
            return original

        def refresh_recovery(self, vault, previous):
            assert previous == original
            return renewed

    vault = tmp_path / "vault"
    vault.mkdir()
    context = UpdateContext(operations=NativePorts())
    header = worker_context_call(
        context,
        {"command": "history", "vault": str(vault), "selection_id": str(uuid4())},
    )
    assert header.changes == 0
    prepared = worker_context_call(
        context,
        {
            "command": "prepare_history",
            "binding": header.binding,
            "kind": "recovery",
            "direction": "finish",
        },
    )
    assert prepared.ready and prepared.changes == 1
    refreshed = worker_context_call(
        context, {"command": "refresh_history", "binding": prepared.binding}
    )
    assert refreshed.ready and refreshed.changes == 2 and refreshed.unresolved == 0
    assert refreshed.binding.review_generation == 4
    assert refreshed.binding != prepared.binding
    page = worker_context_call(
        context, {"command": "page", "binding": refreshed.binding, "limit": 1}
    )
    assert page.page.total == page.changes == 2 and len(page.page.items) == 1
    stale = worker_context_call(
        context, {"command": "page", "binding": prepared.binding}
    )
    assert stale.status == "refused" and stale.code == "context_changed"
    assert stale.changes == 2, "Refusal retains the renewed two-row review"
    assert list(vault.iterdir()) == [], "Counting and refreshing publish no files"


@pytest.mark.parametrize("target", ("matching", "new_checkpoint", "other_receipt"))
def test_undo_context_distinguishes_current_checkpoint_target_receipt_and_prior_operation(
    tmp_path, target
):
    from brz2obsidian.application.operations import Operations
    from brz2obsidian.application.vault_undo_contracts import VaultUndoPreparation
    from brz2obsidian.application.vault_update_contracts import VaultApplyResult
    from tests.application.test_history_workflow import (
        intact_local_history,
        operation_state,
        ready_native_recovery,
    )

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Personal.md").write_bytes(b"Keep authored bytes\r\n")
    history = intact_local_history()
    checkpoint = history.checkpoint.model_copy(
        update={
            "locator": history.checkpoint.locator.model_copy(
                update={"commit": "3" * 40, "generation": 2}
            ),
            "manifest": history.checkpoint.manifest.model_copy(
                update={
                    "generation": 2,
                    "boundary": "result",
                    "previous": "1" * 40,
                    "operation_intent_commit": "2" * 40,
                }
            ),
        }
    )
    history = history.model_copy(update={"checkpoint": checkpoint})
    observed = VaultApplyResult.model_validate(
        operation_state("incomplete").model_dump()
        | {
            "status": "applied",
            "code": "operation_terminal",
            "generation": 1,
            "phase": "terminal",
            "publication": "complete",
            "history": "terminal",
            "published_files": 2,
            "checkpoint_commit": "1" * 40,
            "result_commit": "3" * 40,
            "receipt_commit": "4" * 40,
            "recovery_required": False,
            "origin_role": "source_update",
        }
    )
    review = ready_native_recovery().native.review
    native = VaultUndoPreparation(
        schema_id="brz2obsidian.vault-undo-preparation",
        schema_version=1,
        status="offered",
        code="undo_offered",
        checkpoint_commit="e" * 40 if target == "new_checkpoint" else "3" * 40,
        generation=3 if target == "new_checkpoint" else 2,
        target_receipt_commit="f" * 40 if target == "other_receipt" else "4" * 40,
        review=review,
    )
    undone = VaultApplyResult.model_validate(
        observed.model_dump()
        | {
            "status": "undone",
            "code": "operation_undone",
            "kind": "undo",
            "operation_id": "9" * 32,
            "generation": 3,
            "review_generation": 3,
            "checkpoint_commit": "5" * 40,
            "intent_commit": "6" * 40,
            "result_commit": "7" * 40,
            "receipt_commit": "8" * 40,
        }
    )
    entered = []

    class NativePorts(Operations):
        def inspect_history(self, path, **kwargs):
            assert Path(path) == vault
            return history

        def inspect_update_status(self, path):
            return observed

        def prepare_undo(self, path, *, previous=None):
            return native

        def execute_undo(self, path, preparation, *, cancel=None, progress=None):
            assert progress is not None, (
                "Native Undo must receive the same observer as its apply engine"
            )
            progress(
                VaultProgress(
                    phase="final_reporting",
                    operation_id=undone.operation_id,
                    operation_generation=undone.generation,
                    intent_commit=undone.intent_commit,
                )
            )
            assert preparation == native
            entered.append(True)
            return undone

    context = UpdateContext(operations=NativePorts())
    offered = worker_context_call(
        context,
        {
            "command": "history",
            "vault": str(vault),
            "selection_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    assert "review_undo" in offered.next_actions
    assert (
        offered.binding.operation_generation == 1
        and offered.binding.checkpoint_generation == 2
    )
    if target == "matching":
        old_header = offered.binding
        unsupported_save = worker_context_call(
            context, {"command": "close", "binding": old_header, "choice": "save"}
        )
        assert (
            unsupported_save.code == "history_save_unavailable"
            and not unsupported_save.ready
        )
        assert (
            unsupported_save.publication == "complete"
            and unsupported_save.history_retained
        )
        assert (
            unsupported_save.history.operation == observed
            and unsupported_save.binding == old_header
        )
        foreign_close = worker_context_call(
            context,
            {
                "command": "close",
                "binding": old_header.model_copy(
                    update={"revision": old_header.revision + 1}
                ),
                "choice": "discard",
            },
        )
        assert (
            foreign_close.code == "context_changed"
            and foreign_close.publication == "complete"
        )
        assert (
            foreign_close.history.operation == observed
            and foreign_close.history_retained
            and not entered
        )
        closed_header = worker_context_call(
            context, {"command": "close", "binding": old_header, "choice": "discard"}
        )
        assert (
            closed_header.code == "context_closed"
            and closed_header.status == "no_content_change"
        )
        assert closed_header.binding is None and not closed_header.ready and not entered
        assert (
            closed_header.history.operation == observed
            and closed_header.publication == "complete"
        )
        assert closed_header.history_retained and closed_header.next_actions == (
            "inspect_history",
        )
        stale_header = worker_context_call(
            context,
            {"command": "prepare_history", "binding": old_header, "kind": "undo"},
        )
        assert (
            stale_header.status == "refused"
            and stale_header.code == "context_changed"
            and not entered
        )
        assert stale_header.publication == "complete" and stale_header.history_retained
        assert (
            stale_header.history.operation == observed and stale_header.binding is None
        )
        offered = worker_context_call(
            context,
            {
                "command": "history",
                "vault": str(vault),
                "selection_id": old_header.selection_id,
            },
        )
        assert offered.status == "available" and offered.binding != old_header
        assert offered.history.operation == observed and not entered
    prepared = worker_context_call(
        context,
        {"command": "prepare_history", "binding": offered.binding, "kind": "undo"},
    )
    if target != "matching":
        assert (
            prepared.status == "refused" and prepared.code == "history_target_changed"
        )
        assert prepared.binding is None and not prepared.ready and not entered
        assert prepared.changes == 0
    else:
        assert prepared.ready and prepared.binding.operation_generation == 1
        assert prepared.changes == 1, "One retained row counts despite no byte change"
        assert (
            prepared.binding.operation_id == observed.operation_id
            and prepared.binding.intent_commit == observed.intent_commit
        )
        assert (
            prepared.binding.checkpoint_commit == "3" * 40
            and prepared.binding.checkpoint_generation == 2
        )
        assert (
            prepared.binding.target_receipt_commit == "4" * 40
            and prepared.binding.review_generation == 3
        )
        comparison = worker_context_call(
            context, {"command": "page", "binding": prepared.binding}
        )
        assert comparison.changes == comparison.page.total == 1
        actual = worker_context_call(
            context, {"command": "execute_history", "binding": prepared.binding}
        )
        assert actual.status == "undone" and actual.history_action.operation == undone
        assert (
            actual.history_action.operation.operation_id == "9" * 32
            and actual.history_action.operation.kind == "undo"
        )
        assert actual.binding is None and entered == [True]
    assert (vault / "Personal.md").read_bytes() == b"Keep authored bytes\r\n"


@pytest.mark.parametrize(
    "changed", ("operation_id", "generation", "intent_commit", "kind")
)
def test_history_prepare_cannot_retarget_an_old_offer_to_a_different_native_operation(
    tmp_path, changed
):
    from brz2obsidian.application.operations import Operations
    from tests.application.test_history_workflow import (
        absent_history,
        operation_state,
        ready_native_recovery,
    )

    observed = operation_state("incomplete")
    native = ready_native_recovery().native.model_copy(
        update={
            changed: {
                "operation_id": "f" * 32,
                "generation": 8,
                "intent_commit": "e" * 40,
                "kind": "undo",
            }[changed]
        }
    )
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Personal.md").write_bytes(b"Later personal bytes\r\n")

    class NativePorts(Operations):
        def inspect_history(self, path, **kwargs):
            return absent_history()

        def inspect_update_status(self, path):
            return observed

        def prepare_recovery(self, path, *, direction=None):
            return native

        def execute_recovery(self, *args, **kwargs):
            raise AssertionError("A changed target must not reach execution")

    context = UpdateContext(operations=NativePorts())
    offered = worker_context_call(
        context,
        {
            "command": "history",
            "vault": str(vault),
            "selection_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    result = worker_context_call(
        context,
        {
            "command": "prepare_history",
            "binding": offered.binding,
            "kind": "recovery",
            "direction": "finish",
        },
    )
    assert result.status == "refused" and result.code == "history_target_changed"
    assert (
        result.binding is None
        and not result.ready
        and result.next_actions == ("inspect_history",)
    )
    assert (vault / "Personal.md").read_bytes() == b"Later personal bytes\r\n"


@pytest.mark.parametrize(
    "outcome", ("restored", "undone", "content_complete", "unknown")
)
def test_worker_history_recovery_keeps_native_direction_and_distinct_terminal(
    tmp_path, outcome
):
    from brz2obsidian.application.contracts import WorkerResponse
    from brz2obsidian.application.operations import ApplicationSession, Operations
    from brz2obsidian.application.transport import Terminal
    from brz2obsidian.application.vault_update_contracts import VaultApplyResult
    from tests.application.test_history_workflow import (
        absent_history,
        operation_state,
        ready_native_recovery,
    )

    vault = tmp_path / "vault"
    vault.mkdir()
    literal = b"Later authored bytes\r\n"
    (vault / "Personal.md").write_bytes(literal)
    direction = "restore" if outcome == "restored" else "finish"
    native_kind = "undo" if outcome == "undone" else "apply"
    origin_role = "source_update" if native_kind == "undo" else "attachment_cleanup"
    observed = operation_state("incomplete").model_copy(
        update={"kind": native_kind, "direction": direction, "origin_role": origin_role}
    )
    prepared = ready_native_recovery(kind=native_kind, direction=direction).native
    terminal = outcome in ("restored", "undone")
    result = VaultApplyResult.model_validate(
        observed.model_dump()
        | {
            "status": outcome,
            "code": "native_" + outcome,
            "generation": 8,
            "phase": "terminal"
            if terminal
            else "result"
            if outcome == "content_complete"
            else "publication",
            "publication": "unknown" if outcome == "unknown" else "complete",
            "history": "terminal"
            if terminal
            else "result"
            if outcome == "content_complete"
            else "unknown",
            "checkpoint_commit": "3" * 40,
            "result_commit": None if outcome == "unknown" else "4" * 40,
            "receipt_commit": "5" * 40 if terminal else None,
            "published_files": 1 if outcome == "unknown" else 2,
            "authored_files_changed": None if outcome == "unknown" else True,
            "recovery_required": not terminal,
        }
    )
    writes = []

    class NativePorts(Operations):
        def inspect_history(self, path, **kwargs):
            assert Path(path) == vault
            return absent_history()

        def inspect_update_status(self, path):
            assert Path(path) == vault
            return observed

        def prepare_recovery(self, path, *, direction=None):
            assert Path(path) == vault
            if direction is None:
                return prepared.model_copy(
                    update={
                        "direction": None,
                        "review": None,
                        "available_directions": ("finish", "restore"),
                    }
                )
            assert direction == prepared.direction
            return prepared

        def refresh_recovery(self, path, previous):
            assert Path(path) == vault and previous == prepared
            return prepared

        def execute_recovery(self, path, previous, *, cancel=None, progress=None):
            assert progress is not None, (
                "Native recovery must receive the workflow observer"
            )
            progress(
                VaultProgress(
                    phase="final_reporting",
                    operation_id=result.operation_id,
                    operation_generation=result.generation,
                    intent_commit=result.intent_commit,
                )
            )
            assert Path(path) == vault and previous == prepared
            writes.append(previous)
            return result

    context = UpdateContext(operations=NativePorts())
    session = ApplicationSession()
    selection = "11111111-1111-4111-8111-111111111111"
    session.select_update(str(vault), selection_id=selection)

    def wire(arguments):
        request = session.start_update(arguments)
        assert request is not None
        result = worker_context_call(context, arguments)
        session.complete_update(
            request.request_id,
            Terminal(
                phase="completed",
                response=WorkerResponse(
                    operation="update",
                    request_id=request.request_id,
                    sequence=request.sequence,
                    result=result,
                ),
            ),
        )
        return result

    offered = wire(
        {"command": "history", "vault": str(vault), "selection_id": selection}
    )
    assert offered.publication == "partial" and offered.history.operation == observed
    assert (
        offered.binding.operation_generation == 7
        and offered.binding.intent_commit == "2" * 40
    )
    directions = wire(
        {"command": "prepare_history", "binding": offered.binding, "kind": "recovery"}
    )
    assert directions.status == "direction_required" and not directions.ready
    assert directions.changes == 0
    assert directions.history_action.available_directions == ("finish", "restore")
    selected = wire(
        {
            "command": "prepare_history",
            "binding": directions.binding,
            "kind": "recovery",
            "direction": direction,
        }
    )
    assert selected.ready and selected.binding.operation_generation == 7
    assert selected.changes == 1
    assert session.update_snapshot.reply.changes == 1
    assert (
        selected.binding.review_generation == 3
        and selected.binding.direction == direction
    )
    assert selected.history_action.kind == "recovery" and selected.history_action.ready
    stale = worker_context_call(
        context, {"command": "execute_history", "binding": directions.binding}
    )
    assert stale.status == "refused" and not writes
    assert stale.changes == 1
    refreshed = wire({"command": "refresh_history", "binding": selected.binding})
    assert refreshed.ready and refreshed.binding != selected.binding
    assert refreshed.changes == 1
    assert session.update_snapshot.reply.changes == 1
    completed = wire({"command": "execute_history", "binding": refreshed.binding})
    assert completed.status == outcome and completed.history_action.status == outcome
    assert completed.history_action.operation == result and len(writes) == 1
    assert completed.history_action.operation.generation == 8
    assert completed.history_action.operation.review_generation == 3
    assert completed.history_action.operation.origin_role == origin_role
    assert completed.publication == result.publication and completed.binding is None
    assert completed.history_retained is (None if outcome == "unknown" else True)
    assert not completed.ready and (vault / "Personal.md").read_bytes() == literal
    state = session.update_snapshot
    assert state.publication == result.publication and state.reply.status == outcome
    assert state.reply.changes == 0
    assert state.needs_inspection is (not terminal)
    assert state.history_retained is (None if outcome == "unknown" else True)
    closed = wire({"command": "close", "binding": None, "choice": "discard"})
    assert closed.status == outcome and closed.publication == result.publication
    assert (
        closed.history_action.operation == result and not session.update_snapshot.ready
    )


@pytest.mark.parametrize("conditional_policy", (False, True))
def test_worker_history_initialization_requires_explicit_current_native_offer(
    monkeypatch, conditional_policy
):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-285-history-"))
    owner = {"owner": uuid4().hex, "root": str(root.resolve())}
    (root / ".fixture-owner.json").write_text(json.dumps(owner), encoding="utf-8")
    evidence = Path(__file__).resolve().parents[2] / "tmp/issue-285/history-fixtures"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (owner["owner"] + ".json")).write_text(
        json.dumps(owner), encoding="utf-8"
    )
    vault = root / "vault"
    vault.mkdir()
    raw = b"Exact opaque personal bytes.\x00\xff\r\n"
    (vault / "Personal.bin").write_bytes(raw)
    note = b"Authored note stays exact.\r\n"
    (vault / "Note.md").write_bytes(note)
    if conditional_policy:
        rules = root / "attributes"
        rules.write_bytes(b"*.md filter=unavailable\n")
        included = root / "included-config"
        included.write_text(
            '[core]\n attributesFile = "' + rules.as_posix() + '"\n', encoding="utf-8"
        )
        global_config = root / "global-config"
        global_config.write_text(
            '[includeIf "gitdir/i:'
            + (vault / ".git").as_posix()
            + '"]\n path = "'
            + included.as_posix()
            + '"\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    context = UpdateContext()
    selection = "11111111-1111-4111-8111-111111111111"
    offered = worker_context_call(
        context, {"command": "history", "vault": str(vault), "selection_id": selection}
    )
    assert offered.kind == "history" and offered.status == "initialization_required"
    assert offered.history.status == "initialization_required"
    assert offered.next_actions == ("initialize_vault",) and offered.binding is not None
    assert (
        not offered.history_retained
        and not offered.ready
        and not (vault / ".git").exists()
    )
    assert (
        offered.binding.operation_id is None
        and offered.binding.review_generation is None
    )
    forged = offered.binding.model_copy(update={"fingerprint": "0" * 64})
    refused = worker_context_call(
        context,
        {"command": "initialize_vault", "binding": forged, "choice": "initialize"},
    )
    assert refused.status == "refused" and not (vault / ".git").exists()
    declined = worker_context_call(
        context,
        {
            "command": "initialize_vault",
            "binding": offered.binding,
            "choice": "decline",
        },
    )
    assert declined.status == "declined" and declined.binding == offered.binding
    assert (
        not (vault / ".git").exists() and (vault / "Personal.bin").read_bytes() == raw
    )
    initialized = worker_context_call(
        context,
        {
            "command": "initialize_vault",
            "binding": declined.binding,
            "choice": "initialize",
        },
    )
    assert initialized.status == "initialized_review_required" and not initialized.ready
    assert initialized.binding is None and not initialized.history_retained
    if conditional_policy:
        assert "review_onboarding" not in initialized.next_actions
        assert "custom_filter" in initialized.history.findings
    else:
        assert initialized.next_actions == ("review_onboarding",)
    assert (vault / ".git").is_dir() and (vault / "Personal.bin").read_bytes() == raw
    assert (vault / "Note.md").read_bytes() == note
    assert not (vault / ".brz2obsidian").exists()
