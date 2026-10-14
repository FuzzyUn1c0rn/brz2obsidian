from contextlib import contextmanager
from pathlib import Path
from zipfile import ZipFile

import pytest

from brz2obsidian.application.contracts import BrzSourceSelection
from brz2obsidian.application.operations import Operations, convert_reviewed, inspect
from brz2obsidian.application.wiring import default_workflow


class RecordingPublisher:
    def __init__(self, delegate):
        self.delegate = delegate
        self.calls = 0

    def publish(self, artifacts, session, destination):
        self.calls += 1
        return self.delegate.publish(artifacts, session, destination)


def reviewed_operation(tmp_path):
    source = tmp_path / "archive.brz"
    source.write_bytes(
        (Path(__file__).parents[1] / "fixtures/minimal.brz").read_bytes()
    )
    workflow = default_workflow()
    publisher = RecordingPublisher(workflow.publisher)
    workflow.publisher = publisher
    operation = Operations(workflow)
    return source, operation, publisher


def inventory(root):
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }


def test_clean_review_publishes_verified_vault_and_preserves_source(tmp_path):
    source = tmp_path / "Été archive.brz"
    original = (Path(__file__).parents[1] / "fixtures/minimal.brz").read_bytes()
    source.write_bytes(original)
    reviewed = inspect(source).reviewed

    result = convert_reviewed(source, tmp_path, "Fresh Café", reviewed)

    assert result.status == "conversion_created"
    assert result.publication.state == "published_verified"
    assert result.publication.receipt_verified
    assert result.destination == str(tmp_path / "Fresh Café")
    assert result.counts.actual_notes == 1
    assert result.reviewed is None and not result.review_required
    assert (tmp_path / "Fresh Café/migration-record.json").is_file()
    assert source.read_bytes() == original


@pytest.mark.parametrize(
    "field",
    [
        "source_id",
        "module_id",
        "module_version",
        "format_version",
        "source_sha256",
        "snapshot_digest",
    ],
)
def test_each_review_identity_component_refuses_before_publisher(tmp_path, field):
    source, operation, publisher = reviewed_operation(tmp_path)
    reviewed = operation.inspect(source).reviewed
    identity = reviewed.source_identity.model_copy(update={field: "different"})
    reviewed = reviewed.model_copy(update={"source_identity": identity})
    before = inventory(tmp_path)

    result = operation.convert_reviewed(source, tmp_path, "vault", reviewed)

    assert result.status == "conversion_refused" and result.review_required
    assert result.publication.state == "not_published"
    assert publisher.calls == 0 and inventory(tmp_path) == before


def test_independently_replaced_same_path_archive_refuses_before_publisher(tmp_path):
    source, operation, publisher = reviewed_operation(tmp_path)
    reviewed = operation.inspect(source).reviewed
    replacement = tmp_path / "replacement.brz"
    replacement.write_bytes(source.read_bytes())
    with ZipFile(replacement, "a") as archive:
        archive.comment = b"independent replacement"
    replacement.replace(source)
    before = inventory(tmp_path)

    result = operation.convert_reviewed(source, tmp_path, "vault", reviewed)

    assert result.status == "conversion_refused" and result.review_required
    assert publisher.calls == 0 and inventory(tmp_path) == before


@pytest.mark.parametrize(
    "field", ["converter_version", "profile_id", "profile_version"]
)
def test_each_review_compatibility_component_refuses_before_publisher(tmp_path, field):
    source, operation, publisher = reviewed_operation(tmp_path)
    reviewed = operation.inspect(source).reviewed.model_copy(
        update={field: "different"}
    )
    before = inventory(tmp_path)

    result = operation.convert_reviewed(source, tmp_path, "vault", reviewed)

    assert result.status == "conversion_refused" and result.review_required
    assert publisher.calls == 0 and inventory(tmp_path) == before


def test_actual_custom_metadata_mismatch_is_rejected_without_normalizing_factory(
    tmp_path,
):
    from tests.application.test_module_seams import METADATA

    source, operation, publisher = reviewed_operation(tmp_path)
    reviewed = operation.inspect(source).reviewed
    calls = []

    def metadata():
        calls.append(METADATA)
        return METADATA

    operation.workflow.metadata_factory = metadata
    before = inventory(tmp_path)

    result = operation.convert_reviewed(source, tmp_path, "vault", reviewed)

    assert result.status == "conversion_refused" and result.review_required
    assert calls == [METADATA]
    assert publisher.calls == 0 and inventory(tmp_path) == before


@pytest.mark.parametrize("field", ["profile_id", "profile_version"])
def test_actual_changed_profile_refuses_before_publisher(tmp_path, field):
    from brz2obsidian.application.workflow import SourceModuleBinding

    source, operation, publisher = reviewed_operation(tmp_path)
    reviewed = operation.inspect(source).reviewed
    binding = operation.workflow.binding
    operation.workflow.binding = SourceModuleBinding(
        binding.source, binding.policy.model_copy(update={field: "different"})
    )
    before = inventory(tmp_path)

    result = operation.convert_reviewed(source, tmp_path, "vault", reviewed)

    assert result.status == "conversion_refused" and result.review_required
    assert publisher.calls == 0 and inventory(tmp_path) == before


@pytest.mark.parametrize(
    "control",
    [
        "no_review",
        "other_source",
        "warnings",
        "invalid_name",
        "missing_parent",
        "populated",
    ],
)
def test_backend_admission_refuses_unsafe_inputs_without_publisher(tmp_path, control):
    source, operation, publisher = reviewed_operation(tmp_path)
    reviewed = operation.inspect(source).reviewed
    parent, name = tmp_path, "vault"
    if control == "no_review":
        reviewed = None
    elif control == "other_source":
        reviewed = reviewed.model_copy(
            update={
                "source_selection": BrzSourceSelection(path=str(tmp_path / "other.brz"))
            }
        )
    elif control == "warnings":
        reviewed = reviewed.model_copy(update={"outcome": "warnings"})
    elif control == "invalid_name":
        name = "../escaped"
    elif control == "missing_parent":
        parent = tmp_path / "missing"
    else:
        (tmp_path / name).mkdir()
        (tmp_path / name / "retained.bin").write_bytes(b"keep")
    before = inventory(tmp_path)

    result = operation.convert_reviewed(source, parent, name, reviewed)

    assert result.status == "conversion_refused"
    assert result.publication.state == "not_published"
    assert publisher.calls == 0 and inventory(tmp_path) == before
    if control in ("no_review", "other_source"):
        assert result.review_required
    if control == "warnings":
        assert result.findings[0].code == "warning_authorization_required"
    if control == "invalid_name":
        assert result.field_errors[0].field == "vault_name"
    assert f"Source: {source}" in result.diagnostic_text
    assert "Converter: 0.3.0" in result.diagnostic_text


@pytest.mark.parametrize(
    "surface", ["artifacts", "session", "snapshot", "renderer_version"]
)
def test_actual_protocol_identity_and_renderer_metadata_are_gated(tmp_path, surface):
    from brz2obsidian.application.workflow import SourceModuleBinding

    source, operation, publisher = reviewed_operation(tmp_path)
    reviewed = operation.inspect(source).reviewed
    renderer = operation.workflow.renderer
    binding = operation.workflow.binding

    class ChangedRenderer:
        def render(self, plan, metadata):
            artifacts = renderer.render(plan, metadata)
            return artifacts.model_copy(
                update={"renderer_version": "different"}
                if surface == "renderer_version"
                else {
                    "source_identity": artifacts.source_identity.model_copy(
                        update={"snapshot_digest": "different"}
                    )
                }
            )

    class ChangedSession:
        def __init__(self, original):
            self.original = original
            changed = original.source_identity.model_copy(
                update={"snapshot_digest": "different"}
            )
            self.source_identity = (
                changed if surface == "session" else original.source_identity
            )
            self.snapshot = (
                original.snapshot.model_copy(update={"identity": changed})
                if surface == "snapshot"
                else original.snapshot
            )

        def open_payload(self, asset_id):
            return self.original.open_payload(asset_id)

        def verify_consistency(self):
            return self.original.verify_consistency()

    class ChangedSource:
        @contextmanager
        def open(self, reference):
            with binding.source.open(reference) as original:
                yield ChangedSession(original)

    if surface in ("artifacts", "renderer_version"):
        operation.workflow.renderer = ChangedRenderer()
    else:
        operation.workflow.binding = SourceModuleBinding(
            ChangedSource(), binding.policy
        )
    before = inventory(tmp_path)

    result = operation.convert_reviewed(source, tmp_path, "vault", reviewed)

    assert result.status == "conversion_refused" and result.review_required
    assert publisher.calls == 0 and inventory(tmp_path) == before


def test_matching_custom_renderer_publisher_and_metadata_are_preserved_per_conversion(
    tmp_path,
):
    source, operation, publisher = reviewed_operation(tmp_path)
    reviewed = operation.inspect(source).reviewed
    workflow = operation.workflow
    delegate = workflow.renderer
    metadata = workflow.metadata_factory().model_copy(update={"run_id": "custom-run"})
    calls = []

    class CustomRenderer:
        def render(self, plan, received):
            calls.append(received)
            return delegate.render(plan, received)

    renderer = CustomRenderer()
    factory_calls = []

    def factory():
        factory_calls.append(True)
        return metadata

    workflow.renderer, workflow.metadata_factory = renderer, factory
    result = operation.convert_reviewed(source, tmp_path, "vault", reviewed)

    assert result.status == "conversion_created"
    assert result.publication.state == "published_verified"
    assert result.publication.receipt_verified
    assert publisher.calls > 0
    assert calls and all(received is metadata for received in calls)
    assert factory_calls
    assert workflow.renderer is renderer and workflow.publisher is publisher
    assert workflow.metadata_factory is factory
    assert (
        '"run_id": "custom-run"'
        in (tmp_path / "vault/migration-record.json").read_text()
    )


@pytest.mark.parametrize("published", [False, True])
def test_safe_failure_projection_keeps_planned_or_receipted_actual_facts(
    tmp_path, published
):
    from brz2obsidian.contracts import Issue, MigrationFailed

    source, operation, publisher = reviewed_operation(tmp_path)
    reviewed = operation.inspect(source).reviewed
    leftover = str(tmp_path / ".brz2obsidian-owned-leftover")
    canary = "PRIVATE authored paragraph and raw exception"

    class FailingPublisher:
        def publish(self, artifacts, session, destination):
            receipt = (
                publisher.publish(artifacts, session, destination)
                if published
                else None
            )
            raise MigrationFailed(
                (
                    Issue(
                        code="write_failure",
                        phase="publication",
                        message=canary,
                        guidance=canary,
                        evidence=(canary,),
                    ),
                    Issue(
                        code="cleanup_failure",
                        phase="publication",
                        message=canary,
                        guidance=canary,
                        leftover_path=leftover,
                    ),
                ),
                receipt=receipt,
            )

    operation.workflow.publisher = FailingPublisher()
    original = source.read_bytes()
    result = operation.convert_reviewed(source, tmp_path, "vault", reviewed)

    assert result.status == (
        "conversion_created_with_error" if published else "conversion_failed"
    )
    assert result.publication.receipt_verified is published
    assert result.counts.planned_notes == 1
    assert result.counts.actual_notes == (1 if published else None)
    assert result.destination == str(tmp_path / "vault")
    assert {f.code for f in result.findings} >= {"write_failure", "cleanup_failure"}
    assert (
        next(f for f in result.findings if f.code == "cleanup_failure").path == leftover
    )
    assert leftover in result.diagnostic_text
    assert (
        "Use an absent or empty destination with a shorter path and check filesystem access."
        in result.diagnostic_text
    )
    assert "review" in result.diagnostic_text.lower()
    assert canary not in result.model_dump_json()
    assert source.read_bytes() == original


def test_safe_teardown_failure_retains_verified_published_receipt(tmp_path):
    from brz2obsidian.application.workflow import SourceModuleBinding
    from tests.application.test_failure_protection import TeardownFailureSource

    source, operation, publisher = reviewed_operation(tmp_path)
    reviewed = operation.inspect(source).reviewed
    operation.workflow.binding = SourceModuleBinding(
        TeardownFailureSource(), operation.workflow.binding.policy
    )

    result = operation.convert_reviewed(source, tmp_path, "vault", reviewed)

    assert result.status == "conversion_created_with_error"
    assert result.publication.receipt_verified and result.counts.actual_notes == 1
    assert {f.code for f in result.findings} == {
        "session_teardown_failure",
        "publication_occurred",
    }
    assert "OS denied" not in result.model_dump_json()
    assert publisher.calls == 1


def warning_operation(tmp_path):
    from brz2obsidian.application.workflow import SourceModuleBinding, Workflow
    from brz2obsidian.contracts import FindingDisposition
    from brz2obsidian.obsidian import ObsidianRenderer
    from brz2obsidian.publication import FilesystemPublisher
    from tests.application.test_alternate_source import add_finding, update_folio
    from tests.support.folio_source import FOLIO_POLICY, FolioSourceModule
    from tests.support.paired_sources import paired_sources

    _, source = paired_sources(tmp_path)
    update_folio(source, add_finding)
    disposition = FindingDisposition(
        rule_id="folio.reviewed-length/v1",
        kind="fixture_metadata_discrepancy",
        disposition="warning",
        issue_code="approved_metadata_discrepancy",
        message="Private source warning canary",
        guidance="Private guidance canary",
    )
    policy = FOLIO_POLICY.model_copy(update={"finding_dispositions": (disposition,)})
    publisher = RecordingPublisher(FilesystemPublisher())
    return (
        source,
        Operations(
            Workflow(
                SourceModuleBinding(FolioSourceModule(), policy),
                ObsidianRenderer(),
                publisher,
            )
        ),
        publisher,
    )


@pytest.mark.parametrize("authorization", [False, 0, 1, "yes", True])
def test_actual_warning_requires_explicit_boolean_authorization(
    tmp_path, authorization
):
    source, operation, publisher = warning_operation(tmp_path)
    reviewed = operation.inspect(source).reviewed
    assert reviewed.outcome == "warnings"
    before = inventory(tmp_path)

    result = operation.convert_reviewed(
        source, tmp_path, "vault", reviewed, authorization
    )

    if authorization is True:
        assert result.status == "conversion_created_with_warnings"
        assert result.counts.actual_notes == 3 and publisher.calls == 1
        assert {f.code for f in result.findings} == {"approved_metadata_discrepancy"}
        assert "Private" not in result.model_dump_json()
    else:
        assert result.status == "conversion_refused"
        assert result.findings[0].code == "warning_authorization_required"
        assert publisher.calls == 0 and inventory(tmp_path) == before


def test_actual_warning_cannot_bypass_review_by_claiming_clean_outcome(tmp_path):
    source, operation, publisher = warning_operation(tmp_path)
    reviewed = operation.inspect(source).reviewed.model_copy(
        update={"outcome": "clean"}
    )
    before = inventory(tmp_path)

    result = operation.convert_reviewed(source, tmp_path, "vault", reviewed)

    assert result.status == "conversion_refused" and result.review_required
    assert publisher.calls == 0 and inventory(tmp_path) == before


@pytest.mark.parametrize("failure", ["permission", "disk_full", "cleanup_denied"])
def test_real_publisher_write_failures_and_cleanup_paths_are_projected(
    tmp_path, monkeypatch, failure
):
    import errno
    import shutil

    source, operation, publisher = reviewed_operation(tmp_path)
    reviewed = operation.inspect(source).reviewed
    original = source.read_bytes()
    original_open, original_rmtree = Path.open, shutil.rmtree

    def failing_write(path, mode="r", *args, **kwargs):
        if mode == "xb" and any(
            part.startswith(".brz2obsidian-") for part in path.parts
        ):
            raise OSError(
                errno.EACCES if failure == "permission" else errno.ENOSPC,
                "Private write exception canary",
            )
        return original_open(path, mode, *args, **kwargs)

    def denied_cleanup(path, *args, **kwargs):
        if failure == "cleanup_denied" and Path(path).name.startswith(".brz2obsidian-"):
            raise PermissionError("Private cleanup exception canary")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_write)
    monkeypatch.setattr(shutil, "rmtree", denied_cleanup)
    result = operation.convert_reviewed(source, tmp_path, "vault", reviewed)

    assert (
        result.status == "conversion_failed" and not result.publication.receipt_verified
    )
    assert result.counts.planned_notes == 1 and result.counts.actual_notes is None
    assert not (tmp_path / "vault").exists() and source.read_bytes() == original
    assert "write_failure" in {f.code for f in result.findings}
    assert publisher.calls == 1
    assert "Private" not in result.model_dump_json()
    leftovers = list(tmp_path.glob(".brz2obsidian-*"))
    if failure == "cleanup_denied":
        assert len(leftovers) == 1
        finding = next(f for f in result.findings if f.code == "cleanup_failure")
        assert (
            finding.path == str(leftovers[0]) and finding.path in result.diagnostic_text
        )
    else:
        assert leftovers == []


def test_destination_race_after_validation_preserves_new_existing_bytes(tmp_path):
    source, operation, publisher = reviewed_operation(tmp_path)
    reviewed = operation.inspect(source).reviewed
    renderer = operation.workflow.renderer
    vault = tmp_path / "vault"

    class RacingRenderer:
        def render(self, plan, metadata):
            artifacts = renderer.render(plan, metadata)
            vault.mkdir()
            (vault / "keep.bin").write_bytes(b"late destination owner")
            return artifacts

    operation.workflow.renderer = RacingRenderer()
    result = operation.convert_reviewed(source, tmp_path, "vault", reviewed)

    assert result.status == "conversion_refused" and publisher.calls == 1
    assert {f.code for f in result.findings} == {"destination_not_empty"}
    assert inventory(vault) == {"keep.bin": b"late destination owner"}
    assert list(tmp_path.glob(".brz2obsidian-*")) == []


@pytest.mark.parametrize(
    "fault,expected_status,expected_code",
    [
        ({"stream_failure": True}, "conversion_failed", "write_failure"),
        ({"read_failure": True}, "conversion_failed", "write_failure"),
        ({"mutate_on_payload": True}, "conversion_refused", "source_changed"),
    ],
)
def test_existing_staged_stream_and_within_run_consistency_checks_remain_authoritative(
    tmp_path, fault, expected_status, expected_code
):
    from brz2obsidian.application.workflow import SourceModuleBinding, Workflow
    from brz2obsidian.obsidian import ObsidianRenderer
    from brz2obsidian.publication import FilesystemPublisher
    from tests.support.folio_source import FOLIO_POLICY, FolioSourceModule
    from tests.support.paired_sources import paired_sources

    _, source = paired_sources(tmp_path)
    publisher = RecordingPublisher(FilesystemPublisher())
    operation = Operations(
        Workflow(
            SourceModuleBinding(FolioSourceModule(**fault), FOLIO_POLICY),
            ObsidianRenderer(),
            publisher,
        )
    )
    reviewed = operation.inspect(source).reviewed
    original = source.read_bytes()

    result = operation.convert_reviewed(source, tmp_path, "vault", reviewed)

    assert result.status == expected_status
    assert expected_code in {f.code for f in result.findings}
    assert result.counts.planned_notes == 3 and result.counts.actual_notes is None
    assert publisher.calls == 1
    assert result.review_required is (expected_code == "source_changed")
    assert source.read_bytes() == (
        original + b"\n" if fault.get("mutate_on_payload") else original
    )
    assert not (tmp_path / "vault").exists()
    assert list(tmp_path.glob(".brz2obsidian-*")) == []


@pytest.mark.parametrize(
    "fault", ["source_changed_after_render", "manifest_corruption", "long_final_path"]
)
def test_existing_final_preparation_checks_refuse_before_publication(tmp_path, fault):
    source, operation, publisher = reviewed_operation(tmp_path)
    reviewed = operation.inspect(source).reviewed
    original = source.read_bytes()
    renderer = operation.workflow.renderer
    name = "v" * 130 if fault == "long_final_path" else "vault"

    class ControlledRenderer:
        def render(self, plan, metadata):
            artifacts = renderer.render(plan, metadata)
            if fault == "source_changed_after_render":
                source.write_bytes(original + b"independent actor mutation")
            elif fault == "manifest_corruption":
                artifacts = artifacts.model_copy(
                    update={"manifest": artifacts.manifest + ("missing.md",)}
                )
            return artifacts

    operation.workflow.renderer = ControlledRenderer()
    result = operation.convert_reviewed(source, tmp_path, name, reviewed)

    assert result.status == "conversion_refused"
    expected = {
        "source_changed_after_render": "source_changed",
        "manifest_corruption": "unsafe_target_path",
        "long_final_path": "target_path_too_long",
    }[fault]
    assert expected in {f.code for f in result.findings}
    assert publisher.calls == 1 and not (tmp_path / name).exists()
    assert result.counts.actual_notes is None
    assert list(tmp_path.glob(".brz2obsidian-*")) == []
    assert source.read_bytes() == (
        original + b"independent actor mutation"
        if fault == "source_changed_after_render"
        else original
    )


@pytest.mark.parametrize("replace_after_review", [False, True])
def test_real_hidden_conversion_worker_unicode_paths_and_stale_review(
    tmp_path, replace_after_review
):
    import sys
    from uuid import uuid4

    from brz2obsidian.application.contracts import ConvertArguments, WorkerRequest
    from brz2obsidian.application.transport import Supervisor

    source = tmp_path / "Été archive.brz"
    source.write_bytes(
        (Path(__file__).parents[1] / "fixtures/minimal.brz").read_bytes()
    )
    parent = tmp_path / "Parent Café"
    parent.mkdir()
    reviewed = inspect(source).reviewed
    if replace_after_review:
        with ZipFile(source, "a") as archive:
            archive.comment = b"replaced since independent inspection"
    original = source.read_bytes()
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="convert_reviewed",
        arguments=ConvertArguments(
            source=str(source),
            parent=str(parent),
            vault_name="Fresh Été",
            reviewed=reviewed,
            proceed_with_warnings=False,
        ),
    )

    terminal = Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src").run(
        request
    )

    assert terminal.phase == "completed"
    assert terminal.process_status == (1 if replace_after_review else 0)
    result = terminal.response.result
    assert result.status == (
        "conversion_refused" if replace_after_review else "conversion_created"
    )
    assert result.publication.receipt_verified is not replace_after_review
    assert result.review_required is replace_after_review
    assert result.counts.actual_notes == (None if replace_after_review else 1)
    assert "Authored body" not in terminal.response.model_dump_json()
    assert source.read_bytes() == original
    assert (parent / "Fresh Été").exists() is not replace_after_review


@pytest.mark.parametrize("authorization", [False, True])
def test_real_warning_conversion_worker_exit_two_means_verified_warning_publication(
    tmp_path, authorization
):
    import sys
    from uuid import uuid4

    from brz2obsidian.application.contracts import ConvertArguments, WorkerRequest
    from brz2obsidian.application.transport import Supervisor
    from tests.support.v3_collection import mixed_v3_archive

    source = mixed_v3_archive(tmp_path / "warning source.BRZ")
    original = source.read_bytes()
    reviewed = inspect(source).reviewed
    assert reviewed.outcome == "warnings"
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="convert_reviewed",
        arguments=ConvertArguments(
            source=str(source),
            parent=str(tmp_path),
            vault_name="warning vault",
            reviewed=reviewed,
            proceed_with_warnings=authorization,
        ),
    )

    terminal = Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src").run(
        request
    )

    assert terminal.phase == "completed" and terminal.process_status == (
        2 if authorization else 1
    )
    result = terminal.response.result
    assert result.status == (
        "conversion_created_with_warnings" if authorization else "conversion_refused"
    )
    assert result.publication.receipt_verified is authorization
    assert (tmp_path / "warning vault").exists() is authorization
    assert source.read_bytes() == original
