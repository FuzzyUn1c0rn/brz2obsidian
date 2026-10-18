from pathlib import Path

from brz2obsidian.application.operations import Operations
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
