"""The default producer's lexical content owner, using the existing review engine."""

import shutil
import stat
import tempfile
from contextlib import closing
from pathlib import Path
from threading import Event
from uuid import uuid4

from brz2obsidian.content_fingerprints import canonical_equal
from brz2obsidian.contracts import RunMetadata
from brz2obsidian.core.reconciliation import ReconcileWork
from brz2obsidian.core.refresh import RefreshWork
from brz2obsidian.core.resolution import ActionWork, PlanWork
from brz2obsidian.publication.content_session import _RetainedReviewRead
from brz2obsidian.publication.vault_history import (
    _binding_signature,
    _checkpoint_review_metadata,
    _Git,
    _review_reference_graph,
    _UpdateRead,
)
from brz2obsidian.publication.vault_native import verify_directory

from . import update_lifecycle as lifecycle
from .review_choices import review_plan_choice_action
from .review_offers import review_plan_choice_offers
from .review_session import ReviewSession


class _ProducerCancellation(Event):
    probe = None

    def is_set(self):
        return super().is_set() or bool(self.probe is not None and self.probe())


class _OwnedPreparation:
    """One context-owned review, never a serialized or caller-created capability."""

    def __init__(self, operations):
        self.operations = operations
        self._directory = Path(tempfile.mkdtemp(prefix="brz2obsidian-update-"))
        self._anchor = verify_directory(self._directory)
        self._session = self.observed = self.preparation = None
        self._closed = False
        self._tip = None
        self._cancel = _ProducerCancellation()

    def _observe(self, vault, expected=None):
        fresh = _UpdateRead(vault, _metadata_only=True)
        fresh.__enter__()
        try:
            if expected is not None and (
                fresh.history.status != "intact"
                or fresh.history.checkpoint is None
                or fresh.history.checkpoint.locator != expected
            ):
                raise OSError("association_or_history_changed")
            old = self.observed
            if self._session is not None:
                self._session._content._attach(fresh)
            self.observed = fresh
            if old is not None:
                old.__exit__()
            return fresh.history
        except BaseException:
            fresh.__exit__()
            raise

    def _load_tip(self, checkpoint):
        if checkpoint.manifest.review_object is None:
            return None
        git = _Git(self.observed._root, self.observed._inspection.executable)
        record, references, available = _review_reference_graph(
            git, checkpoint.manifest
        )
        current = self._session._content._observation
        retained = _RetainedReviewRead(
            git,
            checkpoint.manifest,
            checkpoint.locator.commit,
            capacity=lifecycle.available_memory(),
            envelope_size=checkpoint.manifest.review_size,
        )
        self._session._content._observation = retained
        try:
            return self._session._load_retained(
                record,
                available,
                references,
                local=checkpoint.manifest.boundary == "local"
                and not checkpoint.manifest.proposed,
            )
        finally:
            retained._open = False
            self._session._content._observation = current

    def _physical_payload(self, root, rows):
        values = {}
        for row in rows:
            if Path(root).absolute() == self.observed._root:
                reference = self._session._content._acquire_current(
                    row.path, self._session._ledger, self._session._scope
                )
            else:
                reference = self._session._content._import_physical(
                    root, row, self._session._ledger, self._session._scope
                )
            value = self._session._owned_value(reference)
            if row.path == "migration-record.json":
                value = self._session._text(value)
            values[row.path] = value
        return values

    def _source_payload(self, checkpoint):
        result = {}
        for row in checkpoint.manifest.source:
            reference = self._session._content._acquire(
                row.path,
                role="source",
                locator=checkpoint.locator,
                byte_limit=self._session._ledger.remaining("raw_work"),
                timeout=120,
                cancel=self._session._ledger.budget.cancel,
                ledger=self._session._ledger,
                scope=self._session._scope,
            )
            value = self._session._owned_value(reference)
            result[row.path] = (
                self._session._text(value)
                if row.path == "migration-record.json"
                else value
            )
        return result

    def _write_content(self, value, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb", buffering=0) as output:
            binding = self._session._binding(
                value.occurrence, value.identity, value.reference
            )
            with closing(
                self._session._content._read_owned(
                    binding.registration.backing,
                    binding.registration.reference,
                    self._session._ledger,
                    self._session._scope,
                )
            ) as chunks:
                for block in chunks:
                    if output.write(block) != len(block):
                        raise OSError("Incomplete owned materialization")

    def _reconcile(self, facts):
        facts = self._session._admit_values(facts)
        self._session._coadmit()
        return self._session._drive(ReconcileWork(facts))

    def _scoped(self, history, facts, plan=None):
        subjects = lifecycle._subjects(facts, plan)
        scoped = self.observed.inspect(subjects=subjects)
        if scoped.admission.inventory != history.admission.inventory:
            raise OSError("Current inventory changed")
        admission, requested = self.observed._consume_fresh_scope(
            scoped, purpose=None, ledger=self._session._ledger
        )
        if {(row.path, row.subject_id) for row in requested} != {
            (row.path, row.subject_id) for row in subjects
        }:
            raise OSError("Scoped domain differs from the actual review")
        self._session._admit_current(admission, facts)
        return scoped if admission.preflight.consents else history

    def prepare(self, vault, source, *, cancel=None):
        self._cancel.probe = cancel
        try:
            return self._prepare(vault, source)
        finally:
            self._cancel.probe = None
            if self._session is not None and not self._session._closed:
                self._session._ledger.release_failed()

    def _prepare(self, vault, source):
        try:
            history = self._observe(vault)
            history, stopped = lifecycle._history(
                self.operations,
                vault,
                self.observed if history.status == "intact" else None,
            )
            if stopped is not None:
                self.close()
                return stopped
            self._session = ReviewSession._owned_preparation(
                self.observed,
                self._directory,
                lifecycle.available_memory(),
                _cancel=self._cancel,
            )
            self._tip = self._load_tip(history.checkpoint)
            with self._session._operation():
                baseline = lifecycle._read_source(
                    self.operations,
                    vault,
                    history.checkpoint,
                    self.observed,
                    _owner=self,
                )
                directory, incoming, source_identity, reused = lifecycle._render(
                    self.operations,
                    source,
                    baseline,
                    directory=self._directory / "incoming",
                    _owner=self,
                )
                association = history.checkpoint.locator.association
                record = lifecycle.record(incoming)
                if (
                    record["source_identity"]["source_id"],
                    record["source_identity"]["module_id"],
                ) != (association.collection_id, association.module_id):
                    raise OSError("association_mismatch")
                if (
                    lifecycle.output_identity(lifecycle.record(baseline))
                    != history.checkpoint.manifest.identity
                ):
                    raise OSError("baseline_identity_mismatch")
                memory = (
                    () if self._tip is None else lifecycle._memory(self._tip.saved.plan)
                )
                facts = lifecycle._observed_facts(
                    history,
                    baseline,
                    incoming,
                    proposal_id=uuid4().hex,
                    generation=1,
                    source_memory=memory,
                    _owner=self,
                )
                facts = self._session._admit_values(facts)
                history = self._scoped(history, facts)
                self._session._coadmit()
                plan = self._session._drive(
                    PlanWork(facts, history.admission.preflight)
                )
                binding = self.operations.observe_reviewed_source(directory, plan)
                result = lifecycle._prepared(
                    history,
                    directory,
                    binding,
                    plan,
                    source_identity,
                    reused,
                    source_ref=str(Path(source).absolute()),
                    _owner=self,
                )
                self.preparation = result.preparation
            return result
        except OSError, ValueError, TypeError, KeyError, RecursionError:
            self.close()
            return lifecycle._refused(
                "preparation_unavailable", action="inspect_source_and_history"
            )

    def offers(self, plan):
        with self._session._operation():
            plan = self._session._admit_values(plan)
            self._session._coadmit()
            return review_plan_choice_offers(
                plan, _choices=self._session._canonical_choices(plan)
            )

    def choices(self, plan):
        with self._session._operation():
            plan = self._session._admit_values(plan)
            self._session._coadmit()
            return self._session._canonical_choices(plan)

    def choose(self, preparation, **values):
        try:
            return self._choose(preparation, **values)
        except OSError:
            if self._cancel.is_set():
                return lifecycle._refused(
                    "cancelled_before_choice", preparation=preparation
                ).model_copy(
                    update={
                        "status": "cancelled_before_publication",
                        "ready": False,
                        "publication": "not_published",
                        "history_retained": True,
                        "checkpoint_commit": preparation.locator.commit,
                        "next_actions": ("continue_review",),
                    }
                )
            return lifecycle._refused("invalid_review_action", preparation=preparation)
        finally:
            # Worker clears the lexical request probe after this method;
            # failed workspace is retired at the next noncancelled entry.
            if (
                self._session is not None
                and not self._session._closed
                and not self._cancel.is_set()
            ):
                self._session._ledger.release_failed()

    def _choose(self, preparation, **values):
        with self._session._operation():
            plan = self._session._admit_values(preparation.review)
            self._session._coadmit()
            choices = self._session._canonical_choices(plan)
            edited = values.pop("edited", None)
            action = review_plan_choice_action(plan, _choices=choices, **values)
            action = lifecycle.text_choice_action(
                plan, action, edited=edited, _owner=self
            )
            action = self._session._admit_values(action)
            self._session._coadmit()
            transition = self._session._drive(
                ActionWork(plan, action, self._session._epoch)
            )
            prepared = preparation.model_copy(
                update={
                    "review": transition.plan,
                    "source_binding": preparation.source_binding.model_copy(
                        update={"generation": transition.plan.proposal.generation}
                    ),
                }
            )
            self.preparation = prepared
            from .update_contracts import UpdateResult

            return UpdateResult(
                status="prepared_review" if transition.plan.ready else "unresolved",
                code=transition.code,
                preparation=prepared,
                ready=transition.status == "accepted" and transition.plan.ready,
                history_retained=True,
                checkpoint_commit=prepared.locator.commit,
                changes=len(transition.plan.proposal.changes),
                unresolved=len(transition.plan.requirements),
                next_actions=("save_update", "refresh_update"),
            )

    def _byteslice(self, value, offset, maximum):
        binding = self._session._binding(
            value.occurrence, value.identity, value.reference
        )
        if maximum == 0:
            return b""
        result, position = bytearray(), 0
        with closing(
            self._session._content._read_owned(
                binding.registration.backing,
                binding.registration.reference,
                self._session._ledger,
                self._session._scope,
            )
        ) as chunks:
            for block in chunks:
                start, end = (
                    max(0, offset - position),
                    min(len(block), offset + maximum - position),
                )
                if start < end:
                    result.extend(block[start:end])
                position += len(block)
        return bytes(result)

    def page(self, preparation, **arguments):
        try:
            self._observe(preparation.vault, preparation.locator)
            with self._session._operation():
                plan = self._session._admit_values(preparation.review)
                self._session._coadmit()
                return lifecycle.review_plan_page(plan, _owner=self, **arguments)
        except (OSError, ValueError, TypeError, AttributeError) as error:
            from .update_contracts import UpdateReviewPage

            return UpdateReviewPage(
                status="refused",
                code="association_or_history_changed"
                if error.args == ("association_or_history_changed",)
                else "invalid_review",
                proposal_id=arguments["proposal_id"],
                generation=arguments["generation"],
                total=0,
                offset=arguments.get("offset", 0),
                next_offset=None,
                items=(),
                omitted=True,
            )

    def _reobserve(self, preparation):
        history = self._observe(preparation.vault, preparation.locator)
        if (
            self.operations.observe_reviewed_source(
                preparation.payload_directory, preparation.review
            )
            != preparation.source_binding
        ):
            raise OSError("source_payload_changed")
        with self._session._operation():
            plan = self._session._admit_values(preparation.review)
            self._session._coadmit()
            if self._session._replay(plan) is None:
                raise OSError("invalid_review")
            baseline = self._source_payload(history.checkpoint)
            incoming = lifecycle._read_physical(
                preparation.payload_directory,
                preparation.source_binding.files,
                _owner=self,
            )
            if preparation.source_ref is not None:
                record = lifecycle.record(incoming)
                metadata = RunMetadata.model_validate(record["run_metadata"])
                with tempfile.TemporaryDirectory(
                    prefix="source-check-", dir=self._directory
                ) as directory:
                    checked, _, identity, _ = lifecycle._render(
                        self.operations,
                        preparation.source_ref,
                        baseline,
                        metadata=metadata,
                        directory=Path(directory) / "incoming",
                        _owner=self,
                    )
                    binding = self.operations.observe_reviewed_source(checked, plan)
                    if (
                        identity != preparation.observed_source
                        or binding.files != preparation.source_binding.files
                    ):
                        raise OSError("incoming_source_changed")
            facts = lifecycle._observed_facts(
                history,
                baseline,
                incoming,
                proposal_id=plan.proposal.proposal_id,
                generation=plan.proposal.generation,
                source_memory=plan.facts.source_version_memory,
                _owner=self,
            )
            facts = self._session._admit_values(facts)
            history = self._scoped(history, facts, plan)
            self._session._coadmit()
            changed = (
                not canonical_equal(facts, plan.facts)
                or history.admission.preflight != plan.preflight
            )
            if changed:
                facts = facts.model_copy(update={"generation": facts.generation + 1})
                transition = self._session._drive(
                    RefreshWork(plan, facts, history.admission.preflight)
                )
                if transition.status != "accepted":
                    raise OSError("current_review_unavailable")
                plan = transition.plan
            binding = self.operations.observe_reviewed_source(
                preparation.payload_directory, plan
            )
            result = lifecycle._prepared(
                history,
                preparation.payload_directory,
                binding,
                plan,
                preparation.observed_source,
                preparation.retained_source_provenance,
                source_ref=preparation.source_ref,
                code="current_facts_changed" if changed else "current",
                status="stale_review" if changed else "prepared_review",
                stale=lifecycle._stale_slots(preparation.review, plan)
                if changed
                else 0,
                _owner=self,
            )
            return history, result, baseline

    def refresh(self, preparation, *, source=None, cancel=None):
        self._cancel.probe = cancel
        try:
            if source is None:
                _, result, _ = self._reobserve(preparation)
                if (
                    result.status == "stale_review"
                    and result.ready
                    and not result.stale
                ):
                    result = result.model_copy(update={"status": "prepared_review"})
            else:
                result = self._replace_source(preparation, source)
            if result.preparation is not None and result.status in (
                "prepared_review",
                "unresolved",
                "stale_review",
            ):
                self.preparation = result.preparation
            return result
        except OSError, ValueError, TypeError, KeyError, RecursionError:
            if self._cancel.is_set():
                return lifecycle._refused(
                    "cancelled_after_refresh", preparation=preparation
                ).model_copy(
                    update={
                        "status": "cancelled_before_publication",
                        "ready": False,
                        "publication": "not_published",
                        "history_retained": True,
                        "checkpoint_commit": preparation.locator.commit,
                        "next_actions": ("continue_review", "refresh_update"),
                    }
                )
            return lifecycle._refused("refresh_unavailable", preparation=preparation)
        finally:
            self._cancel.probe = None
            if self._session is not None and not self._session._closed:
                self._session._ledger.release_failed()

    def _replace_source(self, preparation, source):
        history = self._observe(preparation.vault)
        history, stopped = lifecycle._history(
            self.operations, preparation.vault, self.observed
        )
        if stopped is not None:
            return stopped
        if history.checkpoint.locator.association != preparation.locator.association:
            raise OSError("association_mismatch")
        tip = self._load_tip(history.checkpoint)
        with self._session._operation():
            old = self._session._admit_values(preparation.review)
            self._session._coadmit()
            if self._session._replay(old) is None:
                raise OSError("invalid_review")
            baseline = self._source_payload(history.checkpoint)
            directory, incoming, observed_source, reused = lifecycle._render(
                self.operations,
                source,
                baseline,
                directory=self._directory / ("incoming-" + uuid4().hex),
                _owner=self,
            )
            if tip is None:
                memory = ()
            elif (
                history.checkpoint.manifest.boundary == "local"
                and history.checkpoint.manifest.reviewed_source is not None
                and tip.saved.plan.proposal.proposal_id == old.proposal.proposal_id
            ):
                memory = tip.saved.plan.facts.source_version_memory
            else:
                memory = lifecycle._memory(tip.saved.plan)
            facts = lifecycle._observed_facts(
                history,
                baseline,
                incoming,
                proposal_id=old.proposal.proposal_id,
                generation=old.proposal.generation + 1,
                source_memory=memory,
                _owner=self,
            )
            facts = self._session._admit_values(facts)
            history = self._scoped(history, facts, old)
            self._session._coadmit()
            transition = self._session._drive(
                RefreshWork(old, facts, history.admission.preflight)
            )
            if transition.status != "accepted":
                raise OSError(transition.code)
            binding = self.operations.observe_reviewed_source(
                directory, transition.plan
            )
            result = lifecycle._prepared(
                history,
                directory,
                binding,
                transition.plan,
                observed_source,
                reused,
                source_ref=str(Path(source).absolute()),
                stale=lifecycle._stale_slots(old, transition.plan),
                _owner=self,
            )
        # The accepted plan/history keep their immutable snapshots. Only the
        # superseded rendered directory is retired; a refusal keeps it intact.
        try:
            self._remove_owned(
                Path(preparation.payload_directory),
                preparation.source_binding.source_anchor,
            )
        except OSError:
            result = result.model_copy(
                update={"findings": result.findings + ("owned_cleanup_unavailable",)}
            )
        return result

    def save(self, preparation, *, cancel=None, progress=None):
        self._cancel.probe = cancel
        try:
            return self._save(preparation, cancel=cancel, progress=progress)
        finally:
            self._cancel.probe = None
            if self._session is not None and not self._session._closed:
                self._session._ledger.release_failed()

    def _save(self, preparation, *, cancel=None, progress=None):
        captured = None
        try:
            from .vault_progress_contracts import report_progress

            report_progress(progress, "current_inspection")
            history, current, baseline = self._reobserve(preparation)
            self.preparation = current.preparation
            if current.status == "stale_review":
                return current
            if cancel is not None and cancel():
                return current.model_copy(
                    update={
                        "status": "cancelled_before_publication",
                        "code": "cancelled_before_snapshot",
                        "ready": False,
                        "publication": "not_published",
                    }
                )
            export = self._session._freeze_export(current.preparation.review)
            baseline_directory = self._directory / ("baseline-" + uuid4().hex)
            with self._session._operation():
                baseline_directory.mkdir()
                for path, value in baseline.items():
                    self._write_content(value, baseline_directory / path)
                modes = {
                    row.path: row.mode for row in history.checkpoint.manifest.source
                }
                for path, mode in modes.items():
                    (baseline_directory / path).chmod(
                        0o755 if mode == "100755" else 0o644
                    )
            self._session._content._detach()
            self.observed = None
            association = preparation.locator.association
            captured = self.operations.capture_checkpoint(
                preparation.vault,
                baseline_directory,
                vault_id=association.vault_id,
                import_id=association.import_id,
                identity=current.preparation.review.facts.baseline_identity,
                admission=history.admission,
                subjects=lifecycle._subjects(
                    current.preparation.review.producer_facts,
                    current.preparation.review,
                )
                if history.admission.preflight.consents
                else (),
                review=current.preparation.review,
                source_binding=current.preparation.source_binding,
                review_source=current.preparation.payload_directory,
                observed_source=current.preparation.observed_source,
                _owned_export=export,
                **({"progress": progress} if progress is not None else {}),
            )
            if (
                captured.status not in ("captured", "unchanged")
                or captured.locator is None
            ):
                return lifecycle._refused(
                    captured.code, preparation=current.preparation
                ).model_copy(
                    update={
                        "capture": captured,
                        "history_retained": captured.history_retained
                        or current.history_retained,
                        "checkpoint_commit": captured.commit,
                    }
                )
            durable = current.model_copy(
                update={
                    "code": "saved",
                    "capture": captured,
                    "history_retained": True,
                    "checkpoint_commit": captured.commit,
                    "checkpoint": captured.locator,
                    "preparation": current.preparation.model_copy(
                        update={"locator": captured.locator}
                    ),
                }
            )
            # Publication is already durable. Any failure below preserves it.
            fresh = self._observe(preparation.vault, captured.locator)
            metadata = fresh.checkpoint.metadata
            with self._session._operation():
                self._session._coadmit()
                loaded = self._session._load_export_for_comparison(export.saved)
                expected = _checkpoint_review_metadata(
                    fresh.checkpoint.manifest, loaded, set(export.values)
                )
                if metadata != expected or _binding_signature(
                    fresh.checkpoint.manifest.reviewed_source
                ) != _binding_signature(current.preparation.source_binding):
                    raise OSError(
                        "Published owner handoff differs from the actual review"
                    )
            self.preparation = durable.preparation
            return durable
        except OSError, ValueError, TypeError, KeyError, RecursionError:
            if captured is not None and captured.status in ("captured", "unchanged"):
                cleanup = ()
                try:
                    self.close()
                except OSError:
                    cleanup = ("owned_cleanup_unavailable",)
                return current.model_copy(
                    update={
                        "status": "publication_unknown",
                        "code": "saved_context_unavailable",
                        "ready": False,
                        "preparation": None,
                        "capture": captured,
                        "history_retained": True,
                        "checkpoint_commit": captured.commit,
                        "checkpoint": captured.locator,
                        "findings": current.findings + cleanup,
                        "next_actions": ("inspect_history",),
                    }
                )
            if self._cancel.is_set():
                return lifecycle._refused(
                    "cancelled_before_snapshot", preparation=preparation
                ).model_copy(
                    update={
                        "status": "cancelled_before_publication",
                        "publication": "not_published",
                        "preparation": preparation,
                        "history_retained": True,
                        "checkpoint_commit": preparation.locator.commit,
                        "ready": False,
                        "next_actions": ("continue_review", "save_update"),
                    }
                )
            return lifecycle._refused("save_unavailable", preparation=preparation)

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self._session is not None:
                self._session.close()
        finally:
            if self.observed is not None:
                self.observed.__exit__()
                self.observed = None
        self._remove_owned(self._directory, self._anchor)

    def _remove_owned(self, directory, anchor):
        directory = directory.absolute()
        if directory != self._directory and not directory.is_relative_to(
            self._directory
        ):
            raise OSError("Owned preparation cleanup escaped its directory")
        if verify_directory(directory) != anchor:
            raise OSError("Owned preparation directory changed; files retained")
        for path in directory.rglob("*"):
            if path.is_dir():
                verify_directory(path)
            else:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise OSError("Owned preparation file changed; files retained")
        shutil.rmtree(directory)
