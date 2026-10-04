"""Generic orchestration; concrete adapters are injected by outer wiring."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from brz2obsidian import __version__
from brz2obsidian.contracts import (
    Counts,
    DocumentInspection,
    Inspection,
    Issue,
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
            renderer_version="2",
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
        failures = []
        phase = "source"

        def retain(error):
            nonlocal issues, receipt, counts
            if isinstance(error, (MigrationRefused, MigrationFailed)):
                issues += error.issues
                receipt = error.receipt or receipt
                failures.append(
                    "refused" if isinstance(error, MigrationRefused) else "failed"
                )
            else:
                issues += (
                    Issue(
                        code="session_teardown_failure"
                        if phase == "session_teardown"
                        else "operation_failure",
                        phase=phase,
                        message=str(error),
                        guidance="Check source and filesystem access, then retry with a fresh destination.",
                    ),
                )
                failures.append("failed")
            if receipt is not None:
                counts = receipt.counts

        try:
            with self.binding.source.open(source_ref) as session:
                try:
                    identity = session.snapshot.identity
                    counts = Counts(
                        source_items=len(session.snapshot.items),
                        source_relationships=len(session.snapshot.relationships),
                        source_references=sum(
                            len(d.references) for d in session.snapshot.documents
                        ),
                        present_assets=sum(
                            asset.availability == "present"
                            for asset in session.snapshot.assets
                        ),
                    )
                    phase = "analysis"
                    analysis = analyze(session.snapshot, self.binding.policy)
                    counts, issues = analysis.counts, analysis.issues
                    migration_plan = plan(analysis)
                    counts, issues = migration_plan.counts, migration_plan.issues
                    if operation == "inspect":
                        session.verify_consistency()
                        inspection = Inspection(
                            item_targets=migration_plan.item_targets,
                            classification_assignments=session.snapshot.classification_assignments,
                            asset_targets=migration_plan.asset_targets,
                            assets=session.snapshot.assets,
                            documents=tuple(
                                DocumentInspection(**d.model_dump(exclude={"text"}))
                                for d in session.snapshot.documents
                            ),
                            adaptations=migration_plan.adaptations,
                            support_artifacts=migration_plan.support_artifacts,
                            reserved_support_paths=migration_plan.reserved_support_paths,
                            tag_targets=migration_plan.tag_targets,
                            tag_memberships=migration_plan.tag_memberships,
                            tag_memberships_path=migration_plan.tag_memberships_path,
                        )
                    else:
                        phase = "rendering"
                        artifacts = self.renderer.render(
                            migration_plan, self.metadata_factory()
                        )
                        phase = "publication"
                        receipt = self.publisher.publish(
                            artifacts, session, destination
                        )
                        counts = receipt.counts
                except (
                    MigrationRefused,
                    MigrationFailed,
                    OSError,
                    ValidationError,
                ) as error:
                    retain(error)
                phase = "session_teardown"
        except (MigrationRefused, MigrationFailed, OSError, ValidationError) as error:
            retain(error)
        if failures and receipt is not None:
            issues += (
                Issue(
                    code="publication_occurred",
                    phase="publication",
                    message=f"The verified vault was published at {receipt.destination} before the later failure.",
                    guidance="Review the published vault; conversion cannot reuse that nonempty destination.",
                ),
            )
        outcome = (
            "failed"
            if "failed" in failures
            else "refused"
            if failures
            else "warnings"
            if issues
            else "clean"
        )
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
