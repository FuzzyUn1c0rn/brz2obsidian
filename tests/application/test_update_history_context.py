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
    choices = worker_context_call(
        context, {"command": "history_choices", "binding": prepared.binding, "limit": 1}
    )
    assert choices.total_choices == 1 and choices.next_choice_offset is None
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
    result = worker_context_call(
        context, {"command": "execute_history", "binding": chosen.binding}
    )
    assert result.status == "restored" and result.history_action.operation == completed
    assert (vault / "Personal.md").read_bytes() == b"Exact personal bytes\r\n"


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
    prepared = worker_context_call(
        context,
        {"command": "prepare_history", "binding": offered.binding, "kind": "undo"},
    )
    if target != "matching":
        assert (
            prepared.status == "refused" and prepared.code == "history_target_changed"
        )
        assert prepared.binding is None and not prepared.ready and not entered
    else:
        assert prepared.ready and prepared.binding.operation_generation == 1
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
    assert (
        selected.binding.review_generation == 3
        and selected.binding.direction == direction
    )
    assert selected.history_action.kind == "recovery" and selected.history_action.ready
    stale = worker_context_call(
        context, {"command": "execute_history", "binding": directions.binding}
    )
    assert stale.status == "refused" and not writes
    refreshed = wire({"command": "refresh_history", "binding": selected.binding})
    assert refreshed.ready and refreshed.binding != selected.binding
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
