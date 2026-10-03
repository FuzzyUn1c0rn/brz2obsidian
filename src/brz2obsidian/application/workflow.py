"""Generic orchestration; concrete adapters are injected by outer wiring."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from brz2obsidian import __version__
from brz2obsidian.contracts import (
    Inspection,
    MigrationFailed,
    MigrationRefused,
    Publisher,
    Renderer,
    RunMetadata,
    RunResult,
    SourceModule,
    SourcePolicy,
)
from brz2obsidian.core import analyze, plan


@dataclass(frozen=True)
class SourceModuleBinding:
    source: SourceModule
    policy: SourcePolicy


class Workflow:
    def __init__(
        self,
        binding: SourceModuleBinding,
        renderer: Renderer,
        publisher: Publisher,
        metadata_factory=None,
    ):
        self.binding, self.renderer, self.publisher = binding, renderer, publisher
        self.metadata_factory = metadata_factory or self._metadata

    @staticmethod
    def _metadata():
        now = datetime.now(UTC)
        return RunMetadata(
            converter_version=__version__,
            renderer_version="1",
            run_id=str(uuid4()),
            run_time=now.isoformat(),
            obsidian_version="1.13.7",
            bookmark_time=int(now.timestamp() * 1000),
        )

    def inspect(self, source_ref: object) -> RunResult:
        return self._run("inspect", source_ref, None)

    def convert(self, source_ref: object, destination: object) -> RunResult:
        return self._run("convert", source_ref, destination)

    def _run(self, operation, source_ref, destination):
        identity = counts = inspection = receipt = None
        issues = ()
        try:
            with self.binding.source.open(source_ref) as session:
                identity = session.snapshot.identity
                analysis = analyze(session.snapshot, self.binding.policy)
                migration_plan = plan(analysis)
                counts, issues = migration_plan.counts, migration_plan.issues
                if operation == "inspect":
                    inspection = Inspection(item_targets=migration_plan.item_targets)
                else:
                    artifacts = self.renderer.render(
                        migration_plan, self.metadata_factory()
                    )
                    receipt = self.publisher.publish(artifacts, session, destination)
                    counts = receipt.counts
            outcome = "warnings" if issues else "clean"
        except (MigrationRefused, MigrationFailed) as error:
            issues += error.issues
            receipt = error.receipt or receipt
            if receipt is not None:
                counts = receipt.counts
            outcome = "refused" if isinstance(error, MigrationRefused) else "failed"
        return RunResult(
            converter_version=__version__,
            operation=operation,
            outcome=outcome,
            source_identity=identity,
            profile_id=self.binding.policy.profile_id,
            profile_version=self.binding.policy.profile_version,
            counts=counts,
            issues=issues,
            inspection=inspection,
            receipt=receipt,
        )
