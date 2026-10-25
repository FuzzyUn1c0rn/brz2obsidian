"""Shared restart admission and history actions at public application seams."""

import hashlib

import pytest

from brz2obsidian.application.checkpoint_contracts import (
    CheckpointLocator,
    CheckpointManifest,
    CheckpointRead,
    VaultAssociation,
    VaultHistoryInspection,
)
from brz2obsidian.application.vault_contracts import VaultAdmission, VaultRepository
from brz2obsidian.application.vault_update_contracts import VaultApplyResult
from tests.reconciliation.test_proposals import identity
from tests.reconciliation.test_resolution import preflight


def absent_history():
    return VaultHistoryInspection(
        schema_id="brz2obsidian.vault-history-inspection",
        schema_version=1,
        status="absent",
        checkpoint=None,
        admission=VaultAdmission(
            schema_id="brz2obsidian.vault-admission",
            schema_version=1,
            vault="owned-vault",
            status="supported",
            repository=VaultRepository(
                kind="none",
                root=None,
                git_directory=None,
                common_directory=None,
                object_directory=None,
                head=None,
                object_format=None,
                ref_format=None,
            ),
            git_executable="git",
            git_version="2.55.0",
            capabilities=(),
            policy_scope="before_initialization",
            policy_fingerprint="a" * 64,
            policy_continuity_fingerprint="b" * 64,
            observation_fingerprint="c" * 64,
            inventory=(),
            inventory_complete=True,
            exclusions=(),
            recovery_gaps=("excluded_files",),
            findings=(),
            admitted_actions=("review_initialization",),
            preflight=preflight(),
        ),
    )


def operation_state(status, *, code="operation_incomplete", recovery=True):
    return VaultApplyResult(
        schema_id="brz2obsidian.vault-apply-result",
        schema_version=1,
        status=status,
        code=code,
        operation_id="1" * 32 if status == "incomplete" else None,
        kind="apply",
        direction="finish" if status == "incomplete" else None,
        generation=7 if status == "incomplete" else None,
        review_generation=3 if status == "incomplete" else None,
        phase="publication" if status == "incomplete" else "admission",
        publication="partial" if status == "incomplete" else "unknown",
        history="intent" if status == "incomplete" else "unknown",
        planned_files=2 if status == "incomplete" else 0,
        published_files=1 if status == "incomplete" else 0,
        authored_files_changed=True if status == "incomplete" else None,
        checkpoint_commit=None,
        intent_commit="2" * 40 if status == "incomplete" else None,
        result_commit=None,
        receipt_commit=None,
        recovery_required=recovery,
        elapsed_ms=0,
        message="Retained operation observation.",
    )


@pytest.mark.parametrize(
    "status,code,recovery",
    (
        ("incomplete", "operation_incomplete", True),
        ("unknown", "operation_history_unavailable", False),
        ("refused", "operation_record_missing", True),
    ),
)
def test_restart_interruption_wins_over_absent_history_and_onboarding(
    status, code, recovery
):
    from brz2obsidian.application.history_workflow import history_admission

    observed = operation_state(status, code=code, recovery=recovery)
    result = history_admission(absent_history(), observed)
    assert result.status == "recovery_required"
    assert result.code == "recovery_first"
    assert result.next_actions == ("review_recovery",)
    assert result.operation == observed
    assert result.checkpoint is None
    assert result.recovery_gaps == ("excluded_files",)
    assert not result.history_retained
    assert "review_onboarding" not in result.next_actions
    assert "review_update" not in result.next_actions
    if status == "incomplete":
        assert result.operation.generation == 7
        assert result.operation.review_generation == 3
        assert result.operation.direction == "finish"


def intact_local_history():
    from brz2obsidian.core import load_review, prepare_review, save_review
    from tests.reconciliation.test_proposals import request
    from tests.reconciliation.test_resolution import with_review_links

    history = absent_history()
    record = save_review(
        prepare_review(with_review_links(request()), preflight=preflight())
    ).record
    loaded = load_review(record).loaded
    payload = record.model_dump_json().encode()
    association = VaultAssociation(
        schema_id="brz2obsidian.vault-association",
        schema_version=1,
        association_id="a" * 64,
        vault_id="owned-vault",
        import_id="first-import",
        collection_id="folio:collection",
        module_id="synthetic-folio",
        vault_anchor="physical-vault",
        git_anchor="physical-git",
        ref="refs/brz2obsidian/imports/" + "a" * 64 + "/checkpoint",
    )
    locator = CheckpointLocator(
        schema_id="brz2obsidian.checkpoint-locator",
        schema_version=1,
        association=association,
        generation=1,
        commit="1" * 40,
    )
    manifest = CheckpointManifest(
        schema_id="brz2obsidian.checkpoint-manifest",
        schema_version=1,
        association_id=association.association_id,
        generation=1,
        boundary="local",
        identity=identity(),
        source=(),
        vault=(),
        preimage=(),
        proposed=(),
        review_content=(),
        recovery_gaps=("excluded_files",),
        semantic_fingerprint="recorded-first-local",
        policy_fingerprint="a" * 64,
        policy_continuity_fingerprint="b" * 64,
        previous=None,
        review_object=hashlib.sha1(
            f"blob {len(payload)}\0".encode() + payload
        ).hexdigest(),
        review_size=len(payload),
        review_sha256=hashlib.sha256(payload).hexdigest(),
    )
    checkpoint = CheckpointRead(
        schema_id="brz2obsidian.checkpoint-read",
        schema_version=1,
        status="valid",
        code="validated",
        locator=locator,
        manifest=manifest,
        review=loaded,
        message="Validated physical LOCAL checkpoint.",
    )
    admission = history.admission.model_copy(
        update={
            "preflight": history.admission.preflight.model_copy(
                update={"state_status": "absent"}
            ),
        }
    )
    return history.model_copy(
        update={"status": "intact", "checkpoint": checkpoint, "admission": admission}
    )


def test_intact_local_routes_from_actual_manifest_despite_absent_parent_preflight():
    from brz2obsidian.application.history_workflow import history_admission

    operation = operation_state(
        "refused", code="operation_absent", recovery=False
    ).model_copy(
        update={
            "publication": "not_started",
            "history": "none",
            "authored_files_changed": False,
        }
    )
    history = intact_local_history()
    projected = history_admission(history, operation)
    assert projected.status == "available" and projected.history_retained
    assert projected.checkpoint == history.checkpoint.locator
    assert projected.next_actions == ("resume_update",)
    assert "review_undo" not in projected.next_actions
    assert "review_onboarding" not in projected.next_actions
    absent = history_admission(absent_history(), operation)
    assert absent.status == "onboarding_required"
    assert absent.next_actions == ("review_onboarding",) and not absent.history_retained
    assert absent.checkpoint is None


def test_unavailable_recovery_preparation_keeps_recovery_route():
    from brz2obsidian.application.operations import Operations
    from brz2obsidian.application.vault_recovery_contracts import (
        VaultRecoveryPreparation,
    )

    native = VaultRecoveryPreparation(
        schema_id="brz2obsidian.vault-recovery-preparation",
        schema_version=1,
        status="unavailable",
        code="original_review_unavailable",
        operation_id=None,
        kind=None,
        generation=None,
        intent_commit=None,
        available_directions=(),
        direction=None,
        review=None,
    )

    class UnavailableNativeRecovery(Operations):
        def prepare_recovery(self, vault, *, direction=None):
            return native

    result = UnavailableNativeRecovery().prepare_history_workflow(
        "unobserved-vault", kind="recovery"
    )
    assert result.status == "recovery_required"
    assert result.code == "original_review_unavailable"
    assert result.next_actions == ("review_recovery",)
    assert result.preparation is None and result.operation is None
    assert result.publication is None and result.recovery_gaps is None


@pytest.mark.parametrize("requested", (False, True))
def test_repair_cancellation_is_checked_only_before_native_execution(requested):
    from brz2obsidian.application.history_workflow_contracts import (
        HistoryWorkflowPreparation,
    )
    from brz2obsidian.application.operations import Operations
    from brz2obsidian.application.vault_repair_contracts import (
        HistoryCopyValidation,
        HistoryRepairPreparation,
        HistoryRepairResult,
    )

    validation = HistoryCopyValidation(
        schema_id="brz2obsidian.history-copy-validation",
        schema_version=1,
        status="matching",
        code="exact_missing_dependency",
        target_generation=2,
        copy_generation=2,
        target_commit="1" * 40,
        copy_commit="1" * 40,
        association_id="a" * 64,
        message="Independently validated native copy.",
    )
    native = HistoryRepairPreparation(
        schema_id="brz2obsidian.history-repair-preparation",
        schema_version=1,
        status="prepared",
        code="exact_missing_dependency",
        validation=validation,
        target_anchor="physical-target",
        target_git_anchor="physical-target-git",
        copy_anchor="physical-copy",
        copy_git_anchor="physical-copy-git",
        target_snapshot="b" * 64,
        copy_snapshot="c" * 64,
        message="Current native repair proof.",
    )

    class ControlledNativeRepair(Operations):
        def execute_history_repair(self, vault, copy, preparation):
            assert not requested, "Cancelled-before-start repair reached native storage"
            return HistoryRepairResult(
                schema_id="brz2obsidian.history-repair-result",
                schema_version=1,
                status="repaired",
                code="repaired",
                history_retained=True,
                object_storage="verified",
                objects_written=1,
                authored_files_changed=False,
                message="Native verified repair.",
            )

    prepared = HistoryWorkflowPreparation(
        kind="repair",
        vault="controlled-target",
        copy_path="controlled-copy",
        native=native,
    )
    result = ControlledNativeRepair().execute_history_workflow(
        prepared, cancel=lambda: requested
    )
    assert result.status == ("cancelled" if requested else "repaired"), result.code
    assert result.kind == "repair" and result.publication is None
    assert result.operation is None and result.preparation is None
    if requested:
        assert result.code == "repair_cancelled_before_start" and result.repair is None
        assert result.history_retained is None
    else:
        assert result.repair.object_storage == "verified"
        assert result.repair.objects_written == 1
        assert result.repair.authored_files_changed is False


@pytest.mark.parametrize("owned_evidence", ("none", "operation", "metadata"))
def test_no_repository_offers_explicit_initialization_only_without_owned_operation(
    owned_evidence,
):
    from brz2obsidian.application.history_workflow import history_admission
    from brz2obsidian.application.vault_contracts import VaultFinding

    # Exact current native shape observed by the independent #281 no-repo case.
    history = absent_history()
    admission = history.admission.model_copy(
        update={
            "preflight": history.admission.preflight.model_copy(
                update={
                    "operation_status": "unknown",
                    "state_status": "unknown",
                    "state_schema": None,
                    "state_version": None,
                }
            ),
        }
    )
    history = history.model_copy(
        update={"status": "unavailable", "admission": admission}
    )
    operation = operation_state(
        "unknown", code="operation_history_invalid", recovery=True
    )
    if owned_evidence == "operation":
        operation = operation_state("incomplete")
    elif owned_evidence == "metadata":
        history = history.model_copy(
            update={
                "admission": admission.model_copy(
                    update={
                        "status": "recovery_first",
                        "admitted_actions": ("resolve_operation",),
                        "findings": (
                            VaultFinding(
                                code="converter_operation",
                                policy="operation",
                                message="Owned metadata requires recovery discovery.",
                                paths=(),
                            ),
                        ),
                    }
                )
            }
        )
    projected = history_admission(history, operation)
    if owned_evidence == "none":
        assert projected.status == "initialization_required"
        assert projected.code == "repository_initialization_required"
        assert projected.next_actions == ("initialize_vault",)
        assert not projected.history_retained and projected.checkpoint is None
    else:
        assert projected.status == "recovery_required"
        assert "review_recovery" in projected.next_actions
        assert "initialize_vault" not in projected.next_actions
        assert "review_onboarding" not in projected.next_actions


@pytest.mark.parametrize("known_operation", (False, True))
def test_unknown_root_history_offers_copy_validation_without_admitting_write(
    known_operation,
):
    from brz2obsidian.application.history_workflow import history_admission

    history = absent_history()
    admission = history.admission.model_copy(
        update={
            "status": "recovery_first",
            "admitted_actions": ("resolve_operation",),
            "repository": history.admission.repository.model_copy(
                update={
                    "kind": "root",
                    "root": "owned-vault",
                    "git_directory": "owned-vault/.git",
                    "common_directory": "owned-vault/.git",
                    "object_directory": "owned-vault/.git/objects",
                    "object_format": "sha1",
                    "ref_format": "files",
                }
            ),
        }
    )
    history = history.model_copy(
        update={"status": "unavailable", "admission": admission}
    )
    operation = (
        operation_state("incomplete")
        if known_operation
        else operation_state("unknown", code="operation_history_invalid")
    )
    routed = history_admission(history, operation)
    assert routed.status == "recovery_required"
    assert "review_recovery" in routed.next_actions
    assert ("review_history_repair" in routed.next_actions) is (not known_operation)
    assert not {
        "review_update",
        "review_onboarding",
        "initialize_vault",
        "execute_history",
    }.intersection(routed.next_actions)


def ready_native_recovery(*, kind="apply", direction="finish"):
    from brz2obsidian.application.history_workflow_contracts import (
        HistoryWorkflowPreparation,
    )
    from brz2obsidian.application.vault_recovery_contracts import (
        VaultRecoveryPreparation,
    )
    from brz2obsidian.core import prepare_review
    from tests.reconciliation.test_proposals import request
    from tests.reconciliation.test_resolution import with_review_links

    facts = with_review_links(
        request(
            original=b"retained",
            current=b"retained",
            incoming=b"retained",
            generation=3,
        )
    )
    review = prepare_review(facts, preflight=preflight())
    assert review.ready
    native = VaultRecoveryPreparation(
        schema_id="brz2obsidian.vault-recovery-preparation",
        schema_version=1,
        status="offered",
        code="recovery_choice_recorded",
        operation_id="1" * 32,
        kind=kind,
        generation=7,
        intent_commit="2" * 40,
        available_directions=(direction,),
        direction=direction,
        review=review,
    )
    return HistoryWorkflowPreparation(
        kind="recovery", vault="controlled-vault", native=native
    )


@pytest.mark.parametrize(
    "status", ("restored", "undone", "content_complete", "unknown")
)
def test_history_results_preserve_distinct_native_outcomes_and_uncertainty(status):
    from brz2obsidian.application.operations import Operations

    kind = "undo" if status in ("undone", "unknown") else "apply"
    direction = "restore" if status == "restored" else "finish"
    prepared = ready_native_recovery(kind=kind, direction=direction)
    observed = operation_state("incomplete").model_copy(
        update={"kind": kind, "direction": direction}
    )
    terminal = status in ("restored", "undone")
    result_fields = observed.model_dump() | {
        "status": status,
        "code": "native_" + status,
        "generation": 8,
        "review_generation": 3,
        "phase": "terminal"
        if terminal
        else "result"
        if status == "content_complete"
        else "publication",
        "publication": "unknown" if status == "unknown" else "complete",
        "history": "terminal"
        if terminal
        else "result"
        if status == "content_complete"
        else "unknown",
        "checkpoint_commit": "3" * 40,
        "result_commit": None if status == "unknown" else "4" * 40,
        "receipt_commit": "5" * 40 if terminal else None,
        "published_files": 1 if status == "unknown" else 2,
        "authored_files_changed": None if status == "unknown" else True,
        "recovery_required": not terminal,
    }
    native = VaultApplyResult.model_validate(result_fields)

    class ControlledNativeResult(Operations):
        def inspect_update_status(self, vault):
            return observed

        def execute_recovery(self, vault, preparation, *, cancel=None):
            return native

    result = ControlledNativeResult().execute_history_workflow(prepared)
    assert result.status == status and result.code == "native_" + status
    assert result.kind == "recovery" and result.operation == native
    assert result.publication == native.publication
    assert result.operation.generation == 8 and result.operation.review_generation == 3
    assert result.next_actions == (
        ("inspect_history",) if terminal else ("review_recovery",)
    )
    assert result.history_retained is (None if status == "unknown" else True)
    assert result.preparation is None


@pytest.mark.parametrize(
    "changed", ("operation_id", "intent_commit", "generation", "kind", "direction")
)
def test_shared_recovery_rejects_changed_native_operation_authority(changed):
    from brz2obsidian.application.operations import Operations

    prepared = ready_native_recovery()
    changed_values = {
        "operation_id": "f" * 32,
        "intent_commit": "e" * 40,
        "generation": 8,
        "kind": "undo",
        "direction": "restore",
    }
    observed = operation_state("incomplete").model_copy(
        update={changed: changed_values[changed]}
    )

    class ChangedNativeAuthority(Operations):
        def inspect_update_status(self, vault):
            return observed

        def execute_recovery(self, vault, preparation, *, cancel=None):
            raise AssertionError(
                "Changed operation authority reached native publication"
            )

    result = ChangedNativeAuthority().execute_history_workflow(prepared)
    assert result.status == "refused" and result.code == "history_authority_changed"
    assert result.operation == observed and result.publication == "partial"
    assert result.operation.review_generation == 3
    assert result.preparation is None


@pytest.mark.parametrize(
    "invalid",
    (
        "none",
        "malformed",
        "operation_id",
        "intent_commit",
        "generation",
        "kind",
        "direction",
        "checkpoint_commit",
        "empty_operation_id",
    ),
)
def test_history_details_refuse_unbound_expected_identity_before_native_read(invalid):
    from brz2obsidian.application.operations import Operations

    expected = operation_state("incomplete").model_copy(
        update={"checkpoint_commit": "3" * 40}
    )
    if invalid == "none":
        expected = None
    elif invalid == "malformed":
        expected = {"unexpected": "not an operation"}
    elif invalid == "empty_operation_id":
        expected = expected.model_copy(update={"operation_id": ""})
    else:
        expected = expected.model_copy(update={invalid: None})

    class NoNativeRead(Operations):
        def read_update_details(self, vault, **kwargs):
            raise AssertionError("Unbound S3 request reached native detail exposure")

    with pytest.raises(ValueError):
        NoNativeRead().read_history_details("unobserved-vault", expected=expected)


def test_bound_metadata_contract_keeps_content_omitted_and_identity_complete():
    from pydantic import ValidationError

    from brz2obsidian.application.vault_update_contracts import VaultUpdateDetailPage

    fields = {
        "schema_id": "brz2obsidian.vault-update-detail-page",
        "schema_version": 1,
        "status": "available",
        "code": "validated",
        "operation_id": "1" * 32,
        "intent_commit": "2" * 40,
        "generation": 7,
        "kind": "apply",
        "direction": "finish",
        "review_generation": None,
        "offset": 0,
        "limit": 1,
        "total": 0,
        "items": (),
        "next_offset": None,
    }
    page = VaultUpdateDetailPage(**fields)
    assert page.content_omitted and page.review_generation is None
    with pytest.raises(ValidationError):
        VaultUpdateDetailPage(**(fields | {"content_omitted": False}))
    with pytest.raises(ValidationError):
        VaultUpdateDetailPage(**(fields | {"generation": None}))
