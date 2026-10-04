from contextlib import contextmanager

from brz2obsidian.application.workflow import SourceModuleBinding, Workflow
from brz2obsidian.contracts import Issue, MigrationFailed
from brz2obsidian.obsidian.rendering import ObsidianRenderer
from brz2obsidian.publication.filesystem import FilesystemPublisher
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from tests.application.test_minimal_workflow import PROPERTIES, make_archive


class TeardownFailureSource:
    @contextmanager
    def open(self, source_ref):
        with BrzSourceModule().open(source_ref) as session:
            yield session
        raise OSError("OS denied source teardown")


def test_workflow_preserves_verified_receipt_after_session_teardown_failure(tmp_path):
    workflow = Workflow(
        SourceModuleBinding(TeardownFailureSource(), BRZ_POLICY),
        ObsidianRenderer(),
        FilesystemPublisher(),
    )
    result = workflow.convert(make_archive(tmp_path / "source.brz"), tmp_path / "vault")
    assert result.outcome == "failed"
    assert result.receipt.published and result.receipt.verified
    assert result.counts.actual_files == 18
    assert (
        tmp_path / "vault" / "Home — Entry thought.md"
    ).read_bytes() == PROPERTIES + (
        b"# Entry thought\n\nAuthored body.\r\n\n"
        b"## Categories\n\n[[Categories.md|Browse categories]]\n"
    )
    assert {i.code for i in result.issues} == {
        "session_teardown_failure",
        "publication_occurred",
    }


class FailingPublisher:
    def publish(self, artifacts, payloads, destination):
        raise MigrationFailed(
            (
                Issue(
                    code="material_failure",
                    phase="publication",
                    message="Copy failed",
                    guidance="Retry",
                ),
            )
        )


def test_workflow_preserves_material_error_when_teardown_also_fails(tmp_path):
    workflow = Workflow(
        SourceModuleBinding(TeardownFailureSource(), BRZ_POLICY),
        ObsidianRenderer(),
        FailingPublisher(),
    )
    result = workflow.convert(make_archive(tmp_path / "source.brz"), tmp_path / "vault")
    assert result.outcome == "failed"
    assert result.receipt is None
    assert [i.code for i in result.issues] == [
        "material_failure",
        "session_teardown_failure",
    ]
    assert result.counts.planned_notes == 1
    assert result.counts.actual_files is None
    assert not (tmp_path / "vault").exists()


class AfterCommitFailurePublisher:
    def publish(self, artifacts, payloads, destination):
        receipt = FilesystemPublisher().publish(artifacts, payloads, destination)
        raise MigrationFailed(
            (
                Issue(
                    code="after_commit_failure",
                    phase="publication",
                    message="Post-commit operation failed",
                    guidance="Review vault",
                ),
            ),
            receipt=receipt,
        )


def test_workflow_retains_actual_receipt_from_publisher_post_commit_failure(tmp_path):
    workflow = Workflow(
        SourceModuleBinding(BrzSourceModule(), BRZ_POLICY),
        ObsidianRenderer(),
        AfterCommitFailurePublisher(),
    )
    result = workflow.convert(make_archive(tmp_path / "source.brz"), tmp_path / "vault")
    assert result.outcome == "failed"
    assert result.receipt.published
    assert (tmp_path / "vault" / "Home — Entry thought.md").exists()
    assert [i.code for i in result.issues] == [
        "after_commit_failure",
        "publication_occurred",
    ]


def test_workflow_preserves_available_source_counts_when_analysis_refuses(tmp_path):
    policy = BRZ_POLICY.model_copy(update={"format_version": "unreviewed"})
    workflow = Workflow(
        SourceModuleBinding(BrzSourceModule(), policy),
        ObsidianRenderer(),
        FilesystemPublisher(),
    )
    result = workflow.convert(make_archive(tmp_path / "source.brz"), tmp_path / "vault")
    assert result.outcome == "refused"
    assert result.receipt is None
    assert result.counts.source_items == 1
    assert result.counts.source_relationships == 0
    assert result.counts.present_assets == 1
    assert result.counts.planned_notes is None
    assert not (tmp_path / "vault").exists()
