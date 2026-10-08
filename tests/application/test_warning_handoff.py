"""Standalone carry and warning authorization at approved public seams."""

import pytest

from brz2obsidian.application.contracts import (
    ApplyResult,
    ConvertCommand,
    InspectCommand,
    InspectionResult,
    SelectSource,
    SetDestination,
    SimpleCommand,
)
from brz2obsidian.application.operations import (
    ApplicationSession,
    inspect,
    validate_destination,
)
from tests.application.test_conversion_review import inventory, warning_operation
from tests.application.test_minimal_workflow import make_archive
from tests.support.v3_collection import mixed_v3_archive


def operation(update):
    return next(effect for effect in update.effects if effect.effect == "run_operation")


def finish(session, effect, result):
    return session.dispatch(
        ApplyResult(
            request_id=effect.request.request_id,
            input_revision=effect.input_revision,
            result=result,
            process_status=0
            if result.outcome in ("clean", "valid")
            else 2
            if result.outcome == "warnings"
            else 1,
        )
    )


@pytest.mark.parametrize("outcome", ["clean", "warnings", "refused", "failed"])
def test_canonical_carry_preserves_usable_review_and_requires_destination(
    tmp_path, outcome
):
    source = (
        mixed_v3_archive(tmp_path / "source.brz")
        if outcome == "warnings"
        else make_archive(tmp_path / "source.brz")
    )
    original = source.read_bytes()
    result = (
        inspect(source)
        if outcome in ("clean", "warnings")
        else InspectionResult(
            outcome=outcome, status="inspection_" + outcome, review_required=True
        )
    )
    session = ApplicationSession()
    session.dispatch(SelectSource(path_or_null=source.as_posix()))
    finish(session, operation(session.dispatch(InspectCommand())), result)
    before, report, generation = (
        session.snapshot,
        session.diagnostics_text(),
        session.diagnostic_generation,
    )
    carried = session.dispatch(SimpleCommand(command="carry_inspection_to_convert"))
    assert carried.effects == () and carried.snapshot.source == before.source
    assert carried.snapshot.reviewed == before.reviewed
    assert carried.snapshot.result == before.result
    assert (
        session.diagnostics_text() == report
        and session.diagnostic_generation == generation
    )
    assert ("convert_this_archive" in carried.snapshot.allowed_actions) is (
        outcome in ("clean", "warnings")
    )
    assert session.dispatch(ConvertCommand(proceed_with_warnings=True)).effects == ()
    assert carried.snapshot.publication is None and source.read_bytes() == original
    if outcome in ("refused", "failed"):
        assert carried.snapshot == before
    else:
        pending = operation(
            session.dispatch(
                SetDestination(parent_or_null=str(tmp_path), vault_name="Fresh vault")
            )
        )
        finish(session, pending, validate_destination(tmp_path, "Fresh vault"))
        if outcome == "warnings":
            assert session.dispatch(ConvertCommand()).effects == ()
            assert (
                operation(
                    session.dispatch(ConvertCommand(proceed_with_warnings=True))
                ).request.arguments.proceed_with_warnings
                is True
            )
        else:
            assert (
                operation(
                    session.dispatch(ConvertCommand())
                ).request.arguments.proceed_with_warnings
                is False
            )


def test_changed_source_invalidates_carried_warning_without_persisted_authorization(
    tmp_path,
):
    source = mixed_v3_archive(tmp_path / "warning.brz")
    session = ApplicationSession()
    session.dispatch(SelectSource(path_or_null=str(source)))
    finish(session, operation(session.dispatch(InspectCommand())), inspect(source))
    session.dispatch(SimpleCommand(command="carry_inspection_to_convert"))
    pending = operation(
        session.dispatch(
            SetDestination(parent_or_null=str(tmp_path), vault_name="Fresh")
        )
    )
    finish(session, pending, validate_destination(tmp_path, "Fresh"))
    assert session.dispatch(ConvertCommand()).effects == ()
    other = make_archive(tmp_path / "clean.brz")
    changed = session.dispatch(SelectSource(path_or_null=other.as_posix()))
    assert changed.snapshot.reviewed is None and changed.snapshot.review_required
    assert "convert_this_archive" not in changed.snapshot.allowed_actions
    assert session.dispatch(ConvertCommand(proceed_with_warnings=True)).effects == ()
    # Fresh clean inspection uses an ordinary non-authorizing Convert command.
    pending = next(
        effect for effect in changed.effects if effect.effect == "run_operation"
    )
    finish(session, pending, validate_destination(tmp_path, "clean"))
    finish(session, operation(session.dispatch(InspectCommand())), inspect(other))
    request = operation(session.dispatch(ConvertCommand())).request
    assert request.arguments.proceed_with_warnings is False


@pytest.mark.parametrize(
    "change",
    [
        "source_sha256",
        "snapshot_digest",
        "module_version",
        "converter_version",
        "profile_id",
        "profile_version",
    ],
)
def test_explicit_warning_authorization_cannot_bypass_changed_review_gate(
    tmp_path, change
):
    source, operations, publisher = warning_operation(tmp_path)
    reviewed = operations.inspect(source).reviewed
    if change in ("source_sha256", "snapshot_digest", "module_version"):
        identity = reviewed.source_identity
        value = (
            "0" * 64 if change in ("source_sha256", "snapshot_digest") else "changed"
        )
        reviewed = reviewed.model_copy(
            update={"source_identity": identity.model_copy(update={change: value})}
        )
    else:
        reviewed = reviewed.model_copy(update={change: "changed"})
    before = inventory(tmp_path)
    result = operations.convert_reviewed(
        source, tmp_path, "Warning vault", reviewed, True
    )
    assert result.status == "conversion_refused" and result.review_required
    assert not result.publication.receipt_verified and publisher.calls == 0
    assert inventory(tmp_path) == before


def test_authorized_warning_attempt_does_not_authorize_fresh_same_path_review(tmp_path):
    from zipfile import ZipFile

    from brz2obsidian.application.contracts import ApplyTransportFailure

    source = mixed_v3_archive(tmp_path / "Warning.brz")
    session = ApplicationSession()
    session.dispatch(SelectSource(path_or_null=str(source)))
    finish(session, operation(session.dispatch(InspectCommand())), inspect(source))
    first_review = session.snapshot.reviewed
    pending = operation(
        session.dispatch(
            SetDestination(parent_or_null=str(tmp_path), vault_name="First")
        )
    )
    finish(session, pending, validate_destination(tmp_path, "First"))
    authorized = operation(session.dispatch(ConvertCommand(proceed_with_warnings=True)))
    session.dispatch(
        ApplyTransportFailure(
            request_id=authorized.request.request_id,
            phase="not_started",
            code="launch_failure",
        )
    )
    # A synthetic external replacement changes bytes; the app never writes source.
    with ZipFile(source, "a") as archive:
        archive.comment = b"new reviewed generation"
    replaced_bytes = source.read_bytes()
    finish(session, operation(session.dispatch(InspectCommand())), inspect(source))
    assert session.snapshot.reviewed.source_identity != first_review.source_identity
    pending = operation(
        session.dispatch(
            SetDestination(parent_or_null=str(tmp_path), vault_name="Second")
        )
    )
    finish(session, pending, validate_destination(tmp_path, "Second"))
    assert "convert_with_warnings" in session.snapshot.allowed_actions
    assert session.dispatch(ConvertCommand()).effects == ()
    assert not (tmp_path / "First").exists() and not (tmp_path / "Second").exists()
    assert source.read_bytes() == replaced_bytes


@pytest.mark.parametrize(
    "corruption", ["missing_publication", "unverified_receipt", "missing_receipt_fact"]
)
def test_warning_wire_without_trustworthy_receipt_is_never_created(
    tmp_path, corruption
):
    import json
    from uuid import uuid4

    from brz2obsidian.application.contracts import (
        ConvertArguments,
        WorkerRequest,
        WorkerResponse,
    )
    from brz2obsidian.application.protocol import (
        ProtocolFailure,
        decode_response,
        encode_response,
    )

    source, operations, _ = warning_operation(tmp_path)
    reviewed = operations.inspect(source).reviewed
    result = operations.convert_reviewed(
        source, tmp_path, "Warning vault", reviewed, True
    )
    assert (
        result.status == "conversion_created_with_warnings"
        and result.publication.receipt_verified
    )
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="convert_reviewed",
        arguments=ConvertArguments(
            source=str(source),
            parent=str(tmp_path),
            vault_name="Warning vault",
            reviewed=reviewed,
            proceed_with_warnings=True,
        ),
    )
    wire = json.loads(
        encode_response(
            WorkerResponse(
                request_id=request.request_id,
                operation=request.operation,
                result=result,
            )
        )
    )
    if corruption == "missing_publication":
        del wire["result"]["publication"]
    elif corruption == "missing_receipt_fact":
        del wire["result"]["publication"]["receipt_verified"]
    else:
        wire["result"]["publication"]["receipt_verified"] = False
    before = inventory(tmp_path)
    with pytest.raises(ProtocolFailure):
        decode_response(json.dumps(wire).encode("utf-8") + b"\n", request)
    assert inventory(tmp_path) == before


@pytest.mark.parametrize(
    "rejection", ["absent_authorization", "replaced_source", "changed_compatibility"]
)
def test_real_warning_worker_rejects_absent_or_stale_authorization_without_target_writes(
    tmp_path, rejection
):
    import sys
    from pathlib import Path
    from uuid import uuid4
    from zipfile import ZipFile

    from brz2obsidian.application.contracts import ConvertArguments, WorkerRequest
    from brz2obsidian.application.transport import Supervisor

    source = mixed_v3_archive(tmp_path / "Warning source.BRZ")
    reviewed = inspect(source).reviewed
    if rejection == "replaced_source":
        with ZipFile(source, "a") as archive:
            archive.comment = b"different actual source after review"
    elif rejection == "changed_compatibility":
        reviewed = reviewed.model_copy(update={"profile_version": "incompatible"})
    original = source.read_bytes()
    before = inventory(tmp_path)
    directories = {
        p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_dir()
    }
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="convert_reviewed",
        arguments=ConvertArguments(
            source=str(source),
            parent=str(tmp_path),
            vault_name="Refused vault",
            reviewed=reviewed,
            proceed_with_warnings=rejection != "absent_authorization",
        ),
    )
    terminal = Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src").run(
        request
    )
    assert terminal.phase == "completed" and terminal.process_status == 1
    result = terminal.response.result
    assert (
        result.status == "conversion_refused"
        and not result.publication.receipt_verified
    )
    assert result.review_required is (rejection != "absent_authorization")
    assert source.read_bytes() == original and inventory(tmp_path) == before
    assert {
        p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_dir()
    } == directories
