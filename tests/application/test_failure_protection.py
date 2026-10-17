from contextlib import contextmanager

from brz2obsidian.contracts import Issue, MigrationFailed
from brz2obsidian.publication.filesystem import FilesystemPublisher
from brz2obsidian.sources.thebrain import BrzSourceModule


class TeardownFailureSource:
    @contextmanager
    def open(self, source_ref):
        with BrzSourceModule().open(source_ref) as session:
            yield session
        raise OSError("OS denied source teardown")


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
