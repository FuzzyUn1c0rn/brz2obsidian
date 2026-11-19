"""The default producer's lexical content owner, using the existing review engine."""

import hashlib
import shutil
import stat
import tempfile
import weakref
from contextlib import closing, contextmanager
from pathlib import Path
from threading import Event
from uuid import uuid4

from brz2obsidian.content_fingerprints import canonical_equal
from brz2obsidian.contracts import RunMetadata, SourceIdentity
from brz2obsidian.core.reconciliation import ReconcileWork
from brz2obsidian.core.refresh import RefreshWork
from brz2obsidian.core.resolution import (
    ActionWork,
    PlanWork,
    _inspect_canonical_choices,
)
from brz2obsidian.core.selected_effects import SelectedEffectsWork
from brz2obsidian.publication.content_session import _RetainedReviewRead
from brz2obsidian.publication.vault_history import (
    _ApplyReviewOwners,
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
        self._tip_commit = None
        self._cancel = _ProducerCancellation()
        self._history_observation = self._history_origin = None
        self._history_origin_commit = None
        self._history_values = {}
        self._apply_review_owners = None
        self._apply_source_update = False
        self._borrowed_apply_session = False
        self._apply_resume = None
        self._readonly_initial = self._readonly_initial_seed = None

    def _stage_readonly_initial(self, result):
        """Reserve the optional alias inside preparation's refusal boundary."""
        self._clear_readonly_initial()
        self.preparation = result.preparation
        if self._session is None or self.preparation is None:
            return
        entry = self._session._initial_review_entry
        if (
            entry is None
            or self.preparation.review.history.events
            or not canonical_equal(entry[1], self.preparation.review)
        ):
            return
        ledger = self._session._ledger
        ledger.check()
        # Two weak aliases own no additional plan graph. Only this known
        # headroom miss is optional; live guard errors must refuse preparation.
        if ledger.metadata + 256 > ledger.budget.metadata_limit:
            return
        ledger.retain_metadata(256)
        self._readonly_initial_seed = weakref.ref(entry[1])

    def _bind_readonly_initial(self, returned, retained):
        """Transfer a freshly minted seed to the Context's validated alias."""
        self._readonly_initial = None
        if self._session is None or returned is not self.preparation:
            self._clear_readonly_initial()
            return
        entry = self._session._initial_review_entry
        seed = self._readonly_initial_seed
        if (
            entry is None
            or seed is None
            or seed() is not entry[1]
            or not canonical_equal(returned.review, retained.review)
        ):
            self._clear_readonly_initial()
            return
        self._readonly_initial = weakref.ref(retained.review)

    def _clear_readonly_initial(self):
        self._readonly_initial = self._readonly_initial_seed = None

    def _is_readonly_initial(self, plan):
        alias, seed = self._readonly_initial, self._readonly_initial_seed
        entry = self._session._initial_review_entry
        if (
            alias is not None
            and alias() is plan
            and seed is not None
            and entry is not None
            and seed() is entry[1]
        ):
            return True
        self._clear_readonly_initial()
        return False

    def _observe(self, vault, expected=None, *, expected_absent=False, _recovery=False):
        fresh = _UpdateRead(
            vault,
            _metadata_only=True,
            _recovery=_recovery,
            _apply_review_owners=self._apply_review_owners if not _recovery else None,
        )
        fresh.__enter__()
        try:
            if expected_absent and fresh.history.status != "absent":
                raise OSError("association_or_history_changed")
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
        return self._load_manifest_review(
            checkpoint.manifest, checkpoint.locator.commit
        )

    def _load_manifest_review(self, manifest, commit):
        if manifest.review_object is None:
            return None
        git = _Git(self.observed._root, self.observed._inspection.executable)
        record, references, available = _review_reference_graph(git, manifest)
        current = self._session._content._observation
        retained = _RetainedReviewRead(
            git,
            manifest,
            commit,
            capacity=lifecycle.available_memory(),
            envelope_size=manifest.review_size,
            memory_spool=self._apply_source_update,
        )
        self._session._content._observation = retained
        try:
            loaded = self._session._load_retained(
                record,
                available,
                references,
                local=manifest.boundary == "local" and not manifest.proposed,
            )
            self._tip_commit = commit
            return loaded
        finally:
            retained._open = False
            self._session._content._observation = current

    def _physical_payload(self, root, rows):
        values = {}
        current = Path(root).absolute() == self.observed._root
        references = None
        if current and self._apply_source_update:
            references = self._session._content._acquire_small_current(
                rows, self._session._ledger, self._session._scope
            )
        for row in rows:
            if references is not None:
                reference = references[row.path]
            elif current:
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

    def inspect_history(self, vault):
        from brz2obsidian.publication.vault_undo import _eligible_target

        from .history_workflow import _history_admission

        try:
            if self._cancel.is_set():
                raise OSError("History inspection cancelled")
            history = self._observe(vault)
            if self._cancel.is_set():
                raise OSError("History inspection cancelled")
            if (
                history.status != "intact"
                or history.admission.status != "supported"
                or self.observed._terminal is None
            ):
                if history.admission.status != "recovery_first":
                    return self.operations.inspect_history_workflow(vault)
                history = self._observe(vault, _recovery=True)
                operation = self.observed._recovery_status
                if (
                    history.status != "intact"
                    or history.admission.status != "supported"
                    or operation is None
                    or not operation.recovery_required
                ):
                    return self.operations.inspect_history_workflow(vault)
            else:
                operation = self.operations.inspect_update_status(vault)
            self._start_session()
            self.observed._check()
            if self._cancel.is_set():
                raise OSError("History inspection cancelled")
            status, _, target = _eligible_target(operation, self.observed._terminal)
            return _history_admission(
                history,
                operation,
                undo_target_receipt_commit=target.receipt_commit
                if status == "offered" and target is not None
                else None,
            )
        except OSError, ValueError, TypeError, UnicodeError:
            if self._cancel.is_set():
                raise
            self.close()
            return self.operations.inspect_history_workflow(vault)

    @contextmanager
    def _history_cancellation(self, cancel):
        cancelled = False

        def probe():
            nonlocal cancelled
            cancelled = cancelled or bool(cancel is not None and cancel())
            return cancelled

        self._cancel.probe = probe
        try:
            yield
        finally:
            self._cancel.probe = None

    def history_fingerprint(self, preparation):
        return self._session._fingerprint(preparation)

    def _operation_target(self, target):
        loaded = self._operation_origin(target.observation, graph=target.graph)
        return target._replace(plan=loaded.saved.plan)

    def _operation_origin(self, observation, *, graph=None):
        self._history_observation = observation
        graph = observation.graph if graph is None else graph
        if graph is not observation.graph and not any(
            graph is item for item in observation.graphs
        ):
            raise OSError("Selected operation graph is outside the actual observation")
        origin = graph.authorities[-1][1]
        manifest, _ = observation.owned[origin.prepared_commit]
        if self._history_origin_commit != origin.prepared_commit:
            self._history_origin = self._load_manifest_review(
                manifest, origin.prepared_commit
            )
            self._history_origin_commit = origin.prepared_commit
        if self._history_origin is None:
            raise OSError("Undo target lacks its canonical owned origin")
        return self._history_origin

    def _operation_content(self, row):
        if row is None:
            return None
        observation = self._history_observation
        if (
            observation is None
            or not any(
                row is candidate
                for manifest, _ in observation.owned.values()
                for role in (
                    "source",
                    "vault",
                    "preimage",
                    "proposed",
                    "review_content",
                )
                for candidate in getattr(manifest, role)
            )
            and not any(
                row is candidate
                for graph in (observation.graph, *observation.graphs)
                for _, authority in graph.authorities
                for candidate in authority.before + authority.proposed
            )
        ):
            raise OSError("Retained content is outside the validated operation graph")
        key = row.object_id, row.size, row.sha256
        if key not in self._history_values:
            from brz2obsidian.publication.git_payload import verify_blobs

            git = _Git(self.observed._root, self.observed._inspection.executable)
            transaction = self._session._begin_input(("operation-role",) + key)

            class Sink:
                def write(self, block):
                    for start in range(0, len(block), 65536):
                        transaction.write(block[start : start + 65536])
                    return len(block)

            try:
                verify_blobs(
                    [*git.prefix, "cat-file", "--batch"],
                    env=git.env,
                    objects=((row.object_id, row.size, row.sha256, Sink()),),
                    timeout=max(30, row.size / (8 * 1024 * 1024) + 30),
                )
                value = self._session._finish_input(transaction, None, inline=False)
                self._history_values[key] = self._session._assembly_content(
                    value, semantic=False
                )
            except BaseException:
                transaction.abort()
                raise
        return self._history_values[key]

    def _history_current(self, rows):
        values = self._physical_payload(self.observed._root, rows)
        return {
            path: self._session._assembly_content(value, semantic=False)
            for path, value in values.items()
        }

    def _history_scoped(self, subjects):
        scoped = self.observed.inspect(subjects=subjects)
        admission, actual = self.observed._consume_fresh_scope(
            scoped, purpose=None, ledger=self._session._ledger
        )
        if {(row.path, row.subject_id) for row in actual} != {
            (row.path, row.subject_id) for row in subjects
        }:
            raise OSError("Undo scoped admission differs from its actual subjects")
        self._history_current_admission = admission
        return admission

    def _history_owned_outputs(self, plan, requests):
        from brz2obsidian.core.reversals import (
            ReviewOwnedOutputs,
            _owned_documents,
            _owned_targets,
        )

        if plan is not self._history_origin.saved.plan:
            raise OSError("Owned output queries require the actual loaded origin")
        self._session._coadmit()
        effects = self._history_origin.historical_effects
        if effects.status != "selected":
            raise OSError("Original operation lacks canonical selected effects")

        def selected():
            return effects

        return ReviewOwnedOutputs(
            tuple(
                _owned_targets(plan, change, decision, selected)
                for change, decision in requests
            ),
            _owned_documents(plan, selected),
            effects,
        )

    def _history_plan(self, facts, preflight, previous=None):
        facts = self._session._admit_values(facts)
        self._session._admit_current(self._history_current_admission, facts)
        self._session._coadmit()
        if previous is None:
            # History seeds retain their independent construction. Canonical
            # replay can retain its own freshly constructed initial result.
            return self._session._drive(PlanWork(facts, preflight))
        transition = self._session._drive(RefreshWork(previous, facts, preflight))
        if transition.status != "accepted":
            raise OSError("Current Undo review could not be refreshed")
        return transition.plan

    def prepare_history(self, vault, *, kind, direction=None, copy=None):
        from brz2obsidian.publication.vault_recovery import prepare_recovery
        from brz2obsidian.publication.vault_undo import prepare_undo

        from .history_workflow import _prepared

        if (
            kind == "recovery"
            and direction in (None, "finish", "restore")
            and copy is None
        ):
            return _prepared(
                vault, kind, prepare_recovery(vault, direction=direction, _owner=self)
            )
        if kind != "undo" or direction is not None or copy is not None:
            return self.operations.prepare_history_workflow(
                vault, kind=kind, direction=direction, copy=copy
            )
        return _prepared(vault, "undo", prepare_undo(vault, _owner=self))

    def refresh_history(self, preparation):
        from brz2obsidian.publication.vault_recovery import refresh_recovery
        from brz2obsidian.publication.vault_undo import prepare_undo

        from .history_workflow import _prepared

        if preparation.kind == "recovery" and preparation.native.direction in (
            "finish",
            "restore",
        ):
            return _prepared(
                preparation.vault,
                "recovery",
                refresh_recovery(preparation.vault, preparation.native, _owner=self),
            )
        if preparation.kind != "undo":
            return self.operations.refresh_history_workflow(preparation)
        return _prepared(
            preparation.vault,
            "undo",
            prepare_undo(preparation.vault, previous=preparation.native, _owner=self),
        )

    def choose_history(self, preparation, **values):
        from brz2obsidian.publication.vault_recovery import (
            _same_recovery_review,
            prepare_recovery,
        )
        from brz2obsidian.publication.vault_undo import _same_review, prepare_undo

        from .history_workflow import _prepared

        if preparation.kind == "recovery" and preparation.native.direction in (
            "finish",
            "restore",
        ):
            fresh = prepare_recovery(
                preparation.vault, direction=preparation.native.direction, _owner=self
            )
            if (
                fresh.generation != preparation.native.generation
                or not _same_recovery_review(fresh, preparation.native)
            ):
                raise ValueError("Recovery review changed")
            code = "recovery_choice_recorded"
        elif preparation.kind == "undo":
            fresh = prepare_undo(preparation.vault, _owner=self)
            if not _same_review(fresh, preparation.native):
                raise ValueError("Undo review changed")
            code = "undo_choice_recorded"
        else:
            action = review_plan_choice_action(
                preparation.native.review,
                **{key: value for key, value in values.items() if key != "edited"},
            )
            action = lifecycle.text_choice_action(
                preparation.native.review, action, edited=values.get("edited")
            )
            return self.operations.resolve_history_workflow(preparation, action)
        with self._session._operation():
            plan = self._session._admit_values(preparation.native.review)
            self._session._coadmit()
            action = review_plan_choice_action(
                plan,
                _choices=self._session._canonical_choices(plan),
                _owner=self,
                **{key: value for key, value in values.items() if key != "edited"},
            )
            action = lifecycle.text_choice_action(
                plan, action, edited=values.get("edited"), _owner=self
            )
            action = self._session._admit_values(action)
            self._session._coadmit()
            transition = self._session._drive(
                ActionWork(plan, action, self._session._epoch)
            )
            if transition.status != "accepted":
                raise ValueError(transition.code)
        return _prepared(
            preparation.vault,
            preparation.kind,
            preparation.native.model_copy(
                update={"review": transition.plan, "code": code}
            ),
        )

    def history_page(self, plan, **arguments):
        with self._session._operation():
            plan = self._session._admit_values(plan)
            self._session._coadmit()
            return lifecycle.review_plan_page(plan, _owner=self, **arguments)

    def execute_history(self, preparation, *, cancel=None, progress=None):
        from brz2obsidian.publication.vault_recovery import execute_recovery
        from brz2obsidian.publication.vault_undo import execute_undo

        from .history_workflow import _executed

        owned_recovery = preparation.kind == "recovery" and (
            preparation.native.direction in ("finish", "restore")
            or preparation.native.status == "cleanup"
        )
        if preparation.kind != "undo" and not owned_recovery:
            return self.operations.execute_history_workflow(
                preparation, cancel=cancel, progress=progress
            )
        with self._history_cancellation(cancel):
            execute = execute_recovery if owned_recovery else execute_undo
            result = execute(
                preparation.vault,
                preparation.native,
                cancel=cancel,
                progress=progress,
                executor=self.operations.vault_executor,
                _owner=self,
            )
            if owned_recovery and self._history_observation is not None:
                graph = self._history_observation.graph
                original = graph.authorities[-1][1]
                if (
                    self._history_origin is not None
                    and self._history_origin_commit == original.prepared_commit
                    and (result.operation_id, result.kind)
                    == (graph.intent.operation_id, graph.intent.kind)
                ):
                    result = result.model_copy(
                        update={
                            "origin_role": self._history_origin.saved.plan.facts.format_operation.kind
                        }
                    )
            return _executed(result, preparation.kind)

    def _source_payload(self, checkpoint):
        references = None
        if self._apply_source_update:
            references = self._session._content._acquire_small_source(
                checkpoint.locator, self._session._ledger, self._session._scope
            )
        result = {}
        for row in checkpoint.manifest.source:
            reference = (
                references[row.path]
                if references is not None
                else self._session._content._acquire(
                    row.path,
                    role="source",
                    locator=checkpoint.locator,
                    byte_limit=self._session._ledger.remaining("raw_work"),
                    timeout=120,
                    cancel=self._session._ledger.budget.cancel,
                    ledger=self._session._ledger,
                    scope=self._session._scope,
                )
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
        purpose = (
            "format_transition"
            if facts.format_operation.kind == "format_transition"
            else None
        )
        scoped = self.observed.inspect(subjects=subjects, new_operation=purpose)
        if scoped.admission.inventory != history.admission.inventory:
            raise OSError("Current inventory changed")
        admission, requested = self.observed._consume_fresh_scope(
            scoped, purpose=purpose, ledger=self._session._ledger
        )
        if {(row.path, row.subject_id) for row in requested} != {
            (row.path, row.subject_id) for row in subjects
        }:
            raise OSError("Scoped domain differs from the actual review")
        self._session._admit_current(admission, facts)
        return scoped if admission.preflight.consents else history

    def _start_session(self):
        if self._session is None:
            self._session = ReviewSession._owned_preparation(
                self.observed,
                self._directory,
                lifecycle.available_memory(),
                _cancel=self._cancel,
            )
            self._session._batch_current = self._apply_source_update
            self._session._content._spool_acquisitions = self._apply_source_update

    def restore(self, vault, *, resume=False, cancel=None, check_saved=None):
        """Read saved history, optionally checking identity before resuming it."""
        from .update_contracts import UpdateResult

        self._cancel.probe = cancel
        history = None
        kind = None
        # Guarded Resume begins with Load's refusal semantics.
        resuming = resume and check_saved is None
        if check_saved is not None:
            self._apply_review_owners = _ApplyReviewOwners(
                memory_spool=True, cancel=self._cancel
            )
        try:
            history = self._observe(vault)
            history, stopped = lifecycle._history(
                self.operations,
                vault,
                self.observed,
                onboarding=True,
                maintenance=True,
            )
            if stopped is not None:
                return stopped
            checkpoint = history.checkpoint
            if (
                checkpoint.manifest.review_object is None
                or checkpoint.manifest.reviewed_source is None
            ):
                return lifecycle._refused("saved_update_unavailable", history)
            # Other operation roles retain their existing public route until
            # their distinct restoration semantics are supported here.
            if checkpoint.metadata[10] not in (
                "onboarding",
                "source_update",
                "format_transition",
                "attachment_cleanup",
            ):
                return None
            kind = checkpoint.metadata[10]
            self._apply_source_update = (
                check_saved is not None and kind == "source_update"
            )
            borrowed = (
                self._apply_review_owners._borrow_local(self.observed, checkpoint)
                if self._apply_source_update
                else None
            )
            if borrowed is None:
                self._start_session()
                self._tip = self._load_tip(checkpoint)
            else:
                self._session, self._tip = borrowed
                self._tip_commit = checkpoint.locator.commit
                self._borrowed_apply_session = True
            plan = self._tip.saved.plan
            if not resume or check_saved is not None:
                saved = UpdateResult(
                    kind=plan.facts.format_operation.kind,
                    status="unresolved",
                    code="revalidation_required",
                    operation_id=plan.proposal.proposal_id,
                    generation=plan.proposal.generation,
                    changes=len(plan.proposal.changes),
                    unresolved=len(plan.requirements),
                    next_actions=("resume_update",),
                    history_retained=True,
                    checkpoint_commit=checkpoint.locator.commit,
                    checkpoint=checkpoint.locator,
                    vault=history.admission.vault,
                )
                if not resume:
                    return saved
                # Apply checks the verified identity before using this same
                # owner to restore Incoming and revalidate Current.
                stopped = check_saved(saved)
                if stopped is not None:
                    return stopped
                resuming = True
            if plan.facts.format_operation.kind in (
                "source_update",
                "format_transition",
                "attachment_cleanup",
            ):
                result = self._resume_update(history, plan)
                self.preparation = result.preparation
                if (
                    self._apply_source_update
                    and result.ready
                    and result.code == "unchanged"
                    and result.preparation is not None
                    and result.preparation.source_ref is None
                ):
                    self._apply_resume = (
                        result,
                        self.observed.current_domain_matcher(),
                        history.checkpoint.manifest,
                    )
                return result
            from .onboarding import _reobserve_onboarding
            from .update_contracts import UpdatePreparation

            with self._session._operation():
                incoming = self._source_payload(checkpoint)
                self._session._coadmit()
                directory, binding = self._restore_incoming(checkpoint, plan, incoming)
                prepared = UpdatePreparation(
                    schema_id="brz2obsidian.update-preparation",
                    schema_version=1,
                    kind="onboarding",
                    vault=history.admission.vault,
                    locator=checkpoint.locator,
                    payload_directory=str(directory),
                    source_binding=binding,
                    observed_source=checkpoint.manifest.observed_source
                    or SourceIdentity.model_validate(
                        lifecycle.record(incoming)["source_identity"]
                    ),
                    retained_source_provenance=False,
                    review=plan,
                )
                _, result, _ = _reobserve_onboarding(
                    self.operations, prepared, history, _owner=self
                )
                self.preparation = result.preparation
                return result
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            RecursionError,
        ) as error:
            if kind == "attachment_cleanup":
                from .attachment_cleanup import refused

                if isinstance(error, lifecycle._ExcludedDependency):
                    return refused(
                        "excluded_dependency_requires_tracking",
                        history,
                        action="review_tracking",
                    )
                if error.args == ("reference_inventory_incomplete",):
                    return refused(
                        "reference_inventory_incomplete",
                        history,
                        action="review_tracking",
                    )
                return refused(
                    "resume_unavailable" if resuming else "saved_update_unavailable",
                    history,
                )
            return lifecycle._refused(
                "resume_unavailable" if resuming else "saved_update_unavailable",
                history,
            )
        finally:
            self._cancel.probe = None
            if self._session is not None and not self._session._closed:
                self._session._ledger.release_failed()
            if not resume or self.preparation is None:
                self.close()

    def _resume_update(self, history, plan):
        checkpoint = history.checkpoint
        exact_retained_plan = self._apply_source_update and plan is self._tip.saved.plan
        with self._session._operation():
            plan = self._session._admit_values(plan)
            baseline = self._source_payload(checkpoint)
            cleanup = plan.facts.format_operation.kind == "attachment_cleanup"
            incoming = (
                baseline
                if cleanup
                else {
                    subject.path: subject.incoming
                    for subject in plan.facts.subjects
                    if subject.incoming is not None
                }
            )
            self._session._coadmit()
            directory, _ = self._restore_incoming(checkpoint, plan, incoming)
            maintenance = plan.facts.format_operation.kind == "format_transition"
            if cleanup:
                from .attachment_cleanup import cleanup_facts

                self._cleanup_inventory(history)
                facts = cleanup_facts(
                    history,
                    baseline,
                    observed=self.observed,
                    proposal_id=plan.proposal.proposal_id,
                    generation=plan.proposal.generation,
                    source_memory=plan.facts.source_version_memory,
                    _owner=self,
                )
            elif maintenance:
                from .format_transition import transition_facts

                baseline = lifecycle._baseline(checkpoint, baseline, _owner=self)
                facts = transition_facts(
                    history,
                    baseline,
                    incoming,
                    proposal_id=plan.proposal.proposal_id,
                    generation=plan.proposal.generation,
                    _owner=self,
                )
            else:
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
            self._session._coadmit()
            if exact_retained_plan:
                # The verified saved plan supplies the subject queries.
                # resume_review still replays against that fresh admission.
                canonical = plan
                effects = None
            else:
                canonical = self._session._replay(plan)
                if canonical is None:
                    raise OSError("invalid_review")
                effects = self._session._drive(SelectedEffectsWork(canonical))
            scoped = self.observed.inspect(
                subjects=lifecycle._subjects(facts, canonical, effects=effects),
                new_operation="format_transition" if maintenance else None,
            )
            if scoped.admission.inventory != history.admission.inventory:
                raise OSError("Current inventory changed")
            if (
                not canonical_equal(facts, canonical.facts)
                or scoped.admission.preflight != canonical.preflight
            ):
                facts = facts.model_copy(
                    update={"generation": plan.proposal.generation + 1}
                )
        # resume_review alone consumes this same reader's latest scoped
        # observation and corroborates current bytes before canonical refresh.
        resumed = self._session.resume_review(
            self._tip,
            facts,
            preflight=scoped.admission.preflight,
            admission=scoped,
        )
        if resumed.status != "resumed":
            return lifecycle._refused(resumed.code, history)
        observed = checkpoint.manifest.observed_source or SourceIdentity.model_validate(
            lifecycle.record(incoming)["source_identity"]
        )
        with self._session._operation():
            current = self._session._admit_values(resumed.plan)
            self._session._coadmit()
            binding = self.operations.observe_reviewed_source(directory, current)
            return lifecycle._prepared(
                scoped,
                directory,
                binding,
                current,
                observed,
                cleanup
                or observed.source_sha256
                != lifecycle.record(incoming)["source_identity"]["source_sha256"],
                code=resumed.code,
                stale=lifecycle._stale_slots(plan, current),
                _owner=self,
            )

    def _restore_incoming(self, checkpoint, plan, incoming):
        """Materialize registered content and corroborate the complete binding."""
        saved = checkpoint.manifest.reviewed_source
        if set(incoming) != {row.path for row in saved.files}:
            raise OSError("saved_payload_mismatch")
        directory = self._directory / "incoming"
        directory.mkdir()
        for row in saved.files:
            path = directory / row.path
            self._write_content(incoming[row.path], path)
            path.chmod(0o755 if row.mode == "100755" else 0o644)
        actual = self.operations.observe_reviewed_source(directory, plan)
        if actual.model_copy(update={"source_anchor": saved.source_anchor}) != saved:
            raise OSError("saved_payload_mismatch")
        return directory, actual

    def _plan(self, history, facts):
        facts = self._session._admit_values(facts)
        history = self._scoped(history, facts)
        self._session._coadmit()
        return history, self._session._initial_review(
            facts, history.admission.preflight
        )

    def prepare(
        self, vault, source, *, kind="source_update", original_source=None, cancel=None
    ):
        self._cancel.probe = cancel
        try:
            return self._prepare(
                vault, source, kind=kind, original_source=original_source
            )
        finally:
            self._cancel.probe = None
            if self._session is not None and not self._session._closed:
                self._session._ledger.release_failed()

    def _prepare(self, vault, source, *, kind, original_source):
        history = None
        try:
            history = self._observe(vault)
            if kind == "attachment_cleanup":
                from .attachment_cleanup import prepare_attachment_cleanup

                result = prepare_attachment_cleanup(self.operations, vault, _owner=self)
                self._stage_readonly_initial(result)
                if result.preparation is None:
                    self.close()
                return result
            if kind == "format_transition":
                from .format_transition import prepare_format_transition

                result = prepare_format_transition(
                    self.operations, vault, source, _owner=self
                )
                self._stage_readonly_initial(result)
                if result.preparation is None:
                    self.close()
                return result
            if kind == "onboarding":
                from .onboarding import prepare_onboarding

                if (
                    history.status != "absent"
                    or history.admission.status != "supported"
                    or history.admission.repository.kind != "root"
                    or not history.admission.inventory_complete
                    or source is None
                ):
                    result = prepare_onboarding(
                        self.operations, vault, source, original_source=original_source
                    )
                    self.close()
                    return result
                self._start_session()
                with self._session._operation():
                    result = prepare_onboarding(
                        self.operations,
                        vault,
                        source,
                        original_source=original_source,
                        _owner=self,
                    )
                    self._stage_readonly_initial(result)
                if result.preparation is None:
                    self.close()
                return result
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
                plan = self._session._initial_review(facts, history.admission.preflight)
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
                self._stage_readonly_initial(result)
            return result
        except OSError, ValueError, TypeError, KeyError, RecursionError:
            self.close()
            if kind == "onboarding":
                from .onboarding import refused

                return refused("onboarding_unavailable", history)
            if kind == "format_transition":
                from .format_transition import refused

                return refused("format_transition_unavailable", history)
            if kind == "attachment_cleanup":
                from .attachment_cleanup import refused

                return refused("current_inputs_unavailable", history)
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

    def _readonly_offers(self, plan):
        with self._session._operation():
            original = plan
            plan = self._session._admit_values(plan)
            self._session._coadmit()
            choices = (
                _inspect_canonical_choices(plan)
                if self._is_readonly_initial(original)
                else self._session._canonical_choices(plan)
            )
            return review_plan_choice_offers(plan, _choices=choices)

    def apply(self, preparation, *, cancel=None, progress=None):
        self._cancel.probe = cancel
        try:
            return lifecycle.apply_update(
                self.operations,
                preparation,
                cancel=cancel,
                progress=progress,
                _owner=self,
            )
        finally:
            self._cancel.probe = None
            if self._session is not None and not self._session._closed:
                self._session._ledger.release_failed()

    def _publication_export(self, plan):
        export = self._session._freeze_export(
            plan, select_effects=self._apply_source_update
        )
        if export.effects is None:
            export.effects = self._session.select_review_effects(export.saved.plan)
        if export.effects.status != "selected":
            raise OSError("Whole current owned review required")
        self._session._content._detach()
        self.observed = None
        export._apply_review_owners = self._apply_review_owners
        return export

    def choices(self, plan):
        with self._session._operation():
            plan = self._session._admit_values(plan)
            self._session._coadmit()
            return self._session._canonical_choices(plan)

    def _readonly_choices(self, plan):
        with self._session._operation():
            original = plan
            plan = self._session._admit_values(plan)
            self._session._coadmit()
            return (
                _inspect_canonical_choices(plan)
                if self._is_readonly_initial(original)
                else self._session._canonical_choices(plan)
            )

    def configuration_choice_offer(self, preparation):
        from .format_configuration import configuration_choice_offer

        return configuration_choice_offer(
            preparation, _choices=self.choices(preparation.review)
        )

    def resolve_configuration_choice(self, preparation, *, group_id, choice):
        from .format_configuration import resolve_configuration_choice

        return resolve_configuration_choice(
            self.operations,
            preparation,
            group_id=group_id,
            choice=choice,
            _owner=self,
        )

    def resolve_update(self, preparation, action):
        """Resolve one prevalidated group member without retaining a partial group."""
        with self._session._operation():
            plan = self._session._admit_values(preparation.review)
            action = self._session._admit_values(action)
            self._session._coadmit()
            return self._action_result(preparation, plan, action)

    def keep_current_unresolved(self, preparation, *, group_id, cancel=None):
        from .review_choices import keep_current_group_action

        previous_probe = self._cancel.probe
        if cancel is not None:
            self._cancel.probe = cancel
        try:
            if preparation.source_ref is not None:
                source_hash = hashlib.sha256()
                with Path(preparation.source_ref).open("rb") as stream:
                    while block := stream.read(1024 * 1024):
                        if self._cancel.is_set():
                            raise OSError("cancelled_before_choice")
                        source_hash.update(block)
                source_sha = source_hash.hexdigest()
                if source_sha != preparation.observed_source.source_sha256:
                    return lifecycle._refused(
                        "source_payload_changed", preparation=preparation
                    )
            history = self._observe(
                preparation.vault,
                preparation.locator,
                expected_absent=preparation.locator is None,
            )
            if history.admission.inventory != preparation.current_inventory:
                return lifecycle._refused(
                    "current_inputs_changed", preparation=preparation
                )
            if (
                self.operations.observe_reviewed_source(
                    preparation.payload_directory, preparation.review
                )
                != preparation.source_binding
            ):
                return lifecycle._refused(
                    "source_payload_changed", preparation=preparation
                )
            with self._session._operation():
                plan = self._session._admit_values(preparation.review)
                self._session._coadmit()
                choices = self._session._canonical_choices(plan)
                action = keep_current_group_action(
                    plan, group_id, _choices=choices, _owner=self
                )
                # The prospective constructors reserved the produced event;
                # reserve its private registration copy before walking/cloning it.
                self._session._ledger.admit_metadata(action)
                action = self._session._admit_values(action)
                self._session._coadmit()
                result = self._action_result(preparation, plan, action)
                self.preparation = result.preparation
                return result
        except OSError, ValueError:
            if self._cancel.is_set():
                return lifecycle._refused(
                    "cancelled_before_choice", preparation=preparation
                ).model_copy(
                    update={
                        "status": "cancelled_before_publication",
                        "ready": False,
                        "publication": "not_published",
                        "preparation": preparation,
                        "history_retained": preparation.locator is not None,
                        "checkpoint_commit": preparation.locator.commit
                        if preparation.locator
                        else None,
                        "next_actions": ("continue_review",),
                    }
                )
            return lifecycle._refused("invalid_review_group", preparation=preparation)
        finally:
            self._cancel.probe = previous_probe
            if (
                self._session is not None
                and not self._session._closed
                and not self._cancel.is_set()
            ):
                self._session._ledger.release_failed()

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
                        "preparation": preparation,
                        "history_retained": preparation.locator is not None,
                        "checkpoint_commit": preparation.locator.commit
                        if preparation.locator
                        else None,
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
            try:
                action = review_plan_choice_action(
                    plan, _choices=choices, _owner=self, **values
                )
            except ValueError:
                return lifecycle._refused(
                    "invalid_review_action", preparation=preparation
                )
            action = lifecycle.text_choice_action(
                plan, action, edited=edited, _owner=self
            )
            action = self._session._admit_values(action)
            self._session._coadmit()
            result = self._action_result(preparation, plan, action)
            self.preparation = result.preparation
            return result

    def _action_result(self, preparation, plan, action):
        from .update_contracts import UpdateResult

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
        ready = transition.status == "accepted" and transition.plan.ready
        result = UpdateResult(
            kind=prepared.kind,
            status="prepared_review" if transition.plan.ready else "unresolved",
            code=transition.code,
            preparation=prepared,
            ready=ready,
            history_retained=prepared.locator is not None,
            checkpoint_commit=prepared.locator.commit if prepared.locator else None,
            changes=len(transition.plan.proposal.changes),
            unresolved=len(transition.plan.requirements),
            next_actions=("save_update",)
            if ready
            and prepared.kind == "onboarding"
            and prepared.locator is None
            and not transition.plan.facts.format_operation.automatic_merge
            else ("apply_update",)
            if ready
            else ("resolve_update", "save_update"),
        )
        return lifecycle._review_explanation(
            lifecycle._configuration_route(result, _owner=self)
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
        return self._page(preparation, **arguments)

    def _readonly_page(self, preparation, **arguments):
        return self._page(preparation, _readonly=True, **arguments)

    def _page(self, preparation, *, _readonly=False, **arguments):
        try:
            self._observe(
                preparation.vault,
                preparation.locator,
                expected_absent=preparation.locator is None,
            )
            with self._session._operation():
                plan = self._session._admit_values(preparation.review)
                self._session._coadmit()
                canonical = (
                    plan
                    if _readonly and self._is_readonly_initial(preparation.review)
                    else None
                )
                return lifecycle.review_plan_page(
                    plan, _owner=self, _canonical_plan=canonical, **arguments
                )
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

    def _cleanup_inventory(self, history):
        if not history.admission.inventory_complete:
            raise OSError("reference_inventory_incomplete")
        if any(
            row.excluded and row.path.lower().endswith(".md")
            for row in history.admission.inventory
        ):
            raise lifecycle._ExcludedDependency

    def _reobserve(self, preparation, *, for_apply=False):
        resume, self._apply_resume = self._apply_resume, None
        if self._session is not None:
            self._session._apply_proved_plan = None
        if preparation.kind == "onboarding":
            from .onboarding import reobserve_onboarding

            history, result, _ = reobserve_onboarding(
                self.operations, preparation, _owner=self
            )
            if history is None or result.preparation is None:
                raise OSError(result.code)
            return history, result, None
        history = self._observe(preparation.vault, preparation.locator)
        maintenance = preparation.kind == "format_transition"
        cleanup = preparation.kind == "attachment_cleanup"
        if cleanup:
            self._cleanup_inventory(history)
        if maintenance or cleanup:
            history, stopped = lifecycle._history(
                self.operations,
                preparation.vault,
                self.observed,
                maintenance=maintenance,
                new_operation="format_transition" if maintenance else None,
                recorded_output_format=preparation.source_binding.incoming_identity.output_format,
            )
            if stopped is not None:
                raise OSError(stopped.code)
            if self._tip_commit != history.checkpoint.locator.commit:
                self._tip = self._load_tip(history.checkpoint)
        if (
            self.operations.observe_reviewed_source(
                preparation.payload_directory, preparation.review
            )
            != preparation.source_binding
        ):
            raise OSError("source_payload_changed")
        if (
            for_apply
            and resume is not None
            and resume[0].preparation is self.preparation
            and resume[0].preparation == preparation
            and resume[2] == history.checkpoint.manifest
            and resume[1](self.observed)
        ):
            with self._session._operation():
                plan = self._session._admit_values(preparation.review)
                self._recheck_resumed_payloads(history, preparation)
                scoped = self._scoped(history, plan.facts, plan)
                if scoped.admission.preflight == plan.preflight:
                    # Resume proved this graph against the same inputs. Fresh
                    # admission rechecks history, Current and its policy, and
                    # co-admission rechecks every live retained backing.
                    self._session._coadmit()
                    if (
                        self.operations.observe_reviewed_source(
                            preparation.payload_directory, plan
                        )
                        != preparation.source_binding
                    ):
                        raise OSError("source_payload_changed")
                    self._session._apply_proved_plan = resume[0].preparation.review
                    return (
                        scoped,
                        resume[0].model_copy(update={"code": "current"}),
                        None,
                    )
        with self._session._operation():
            plan = self._session._admit_values(preparation.review)
            self._session._coadmit()
            if self._session._replay(plan) is None:
                raise OSError("invalid_review")
            baseline = self._source_payload(history.checkpoint)
            if maintenance:
                baseline = lifecycle._baseline(
                    history.checkpoint, baseline, _owner=self
                )
            incoming = lifecycle._read_physical(
                preparation.payload_directory,
                preparation.source_binding.files,
                _owner=self,
            )
            if cleanup:
                expected = tuple(
                    (row.path, row.mode, row.size, row.sha256)
                    for row in history.checkpoint.manifest.source
                )
                if (
                    preparation.source_ref is not None
                    or preparation.source_binding.incoming_identity
                    != history.checkpoint.manifest.identity
                    or preparation.source_binding.target_source_version
                    != lifecycle.record(baseline)["source_identity"]["snapshot_digest"]
                    or tuple(
                        (row.path, row.mode, row.size, row.sha256)
                        for row in preparation.source_binding.files
                    )
                    != expected
                    or preparation.observed_source
                    != SourceIdentity.model_validate(
                        lifecycle.record(baseline)["source_identity"]
                    )
                ):
                    raise OSError("retained_source_authority_required")
            elif preparation.source_ref is not None:
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
            if cleanup:
                from .attachment_cleanup import cleanup_facts

                facts = cleanup_facts(
                    history,
                    baseline,
                    observed=self.observed,
                    proposal_id=plan.proposal.proposal_id,
                    generation=plan.proposal.generation,
                    source_memory=lifecycle._producer_memory(
                        history.checkpoint, plan.proposal.proposal_id, _owner=self
                    ),
                    _owner=self,
                )
            elif maintenance:
                from .format_transition import transition_facts

                facts = transition_facts(
                    history,
                    baseline,
                    incoming,
                    proposal_id=plan.proposal.proposal_id,
                    generation=plan.proposal.generation,
                    _owner=self,
                )
            else:
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

    def _recheck_resumed_payloads(self, history, preparation):
        # Keep exact live byte comparisons with Resume's owned registrations.
        # The admission inventory identifies candidates for those comparisons.
        current_paths = {
            origin[1]
            for _, _, _, origin in self._session._content._values.values()
            if origin[0] == "current"
        }
        self._source_payload(history.checkpoint)
        lifecycle._read_physical(
            preparation.payload_directory, preparation.source_binding.files, _owner=self
        )
        lifecycle._read_physical(
            preparation.vault,
            tuple(
                row for row in history.admission.inventory if row.path in current_paths
            ),
            _owner=self,
        )

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
                if preparation.kind == "attachment_cleanup":
                    return lifecycle._refused(
                        "retained_source_authority_required", preparation=preparation
                    )
                result = self._replace_source(preparation, source)
            if result.preparation is not None and result.status in (
                "prepared_review",
                "unresolved",
                "stale_review",
            ):
                self.preparation = result.preparation
            return result
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
            if self._cancel.is_set():
                return lifecycle._refused(
                    "cancelled_after_refresh", preparation=preparation
                ).model_copy(
                    update={
                        "status": "cancelled_before_publication",
                        "ready": False,
                        "publication": "not_published",
                        "preparation": preparation,
                        "history_retained": preparation.locator is not None,
                        "checkpoint_commit": preparation.locator.commit
                        if preparation.locator
                        else None,
                        "next_actions": ("continue_review", "refresh_update"),
                    }
                )
            if preparation.kind == "format_transition" and error.args == (
                "format_source_changed",
            ):
                from .format_transition import refused

                return refused(
                    "format_source_changed", action="choose_source_reference"
                )
            if preparation.kind == "attachment_cleanup":
                from .attachment_cleanup import refused

                history = self.observed.history if self.observed is not None else None
                if isinstance(error, lifecycle._ExcludedDependency):
                    return refused(
                        "excluded_dependency_requires_tracking",
                        history,
                        action="review_tracking",
                    )
                if error.args == ("reference_inventory_incomplete",):
                    return refused(
                        "reference_inventory_incomplete",
                        history,
                        action="review_tracking",
                    )
            return lifecycle._refused("refresh_unavailable", preparation=preparation)
        finally:
            self._cancel.probe = None
            if self._session is not None and not self._session._closed:
                self._session._ledger.release_failed()

    def _replace_source(self, preparation, source):
        history = self._observe(preparation.vault)
        maintenance = preparation.kind == "format_transition"
        output_format = preparation.source_binding.incoming_identity.output_format
        history, stopped = lifecycle._history(
            self.operations,
            preparation.vault,
            self.observed,
            maintenance=maintenance,
            new_operation="format_transition" if maintenance else None,
            recorded_output_format=output_format,
        )
        if stopped is not None:
            return stopped.model_copy(update={"kind": preparation.kind})
        if history.checkpoint.locator.association != preparation.locator.association:
            raise OSError("association_mismatch")
        tip = self._load_tip(history.checkpoint)
        with self._session._operation():
            old = self._session._admit_values(preparation.review)
            self._session._coadmit()
            if self._session._replay(old) is None:
                raise OSError("invalid_review")
            baseline = self._source_payload(history.checkpoint)
            if maintenance:
                self._tip = tip
                baseline = lifecycle._baseline(
                    history.checkpoint, baseline, _owner=self
                )
            directory, incoming, observed_source, reused = lifecycle._render(
                self.operations,
                source,
                baseline,
                output_format=output_format,
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
            if maintenance:
                from .format_transition import transition_facts

                facts = transition_facts(
                    history,
                    baseline,
                    incoming,
                    proposal_id=old.proposal.proposal_id,
                    generation=old.proposal.generation + 1,
                    _owner=self,
                )
            else:
                facts = lifecycle._observed_facts(
                    history,
                    baseline,
                    incoming,
                    proposal_id=old.proposal.proposal_id,
                    generation=old.proposal.generation + 1,
                    source_memory=memory,
                    retained_review=tip,
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
            if (
                export.saved.plan.ready
                and export.saved.plan.facts.format_operation.kind
                == "attachment_cleanup"
            ):
                export.effects = self._session.select_review_effects(export.saved.plan)
                if export.effects.status != "selected":
                    raise OSError("Whole current owned review required")
            onboarding = current.preparation.kind == "onboarding"
            if onboarding:
                baseline_directory = current.preparation.payload_directory
            else:
                baseline_directory = self._directory / ("baseline-" + uuid4().hex)
                with self._session._operation():
                    baseline_directory.mkdir()
                    for path, value in baseline.items():
                        self._write_content(value, baseline_directory / path)
                    source_files = (
                        self.observed.format_baseline_files()
                        if current.kind == "format_transition"
                        and history.checkpoint.manifest.boundary == "prepared"
                        else history.checkpoint.manifest.source
                    )
                    modes = {row.path: row.mode for row in source_files}
                    for path, mode in modes.items():
                        (baseline_directory / path).chmod(
                            0o755 if mode == "100755" else 0o644
                        )
            self._session._content._detach()
            self.observed = None
            association = (
                preparation.locator.association if preparation.locator else None
            )
            proposal_id = current.preparation.review.proposal.proposal_id
            captured = self.operations.capture_checkpoint(
                preparation.vault,
                baseline_directory,
                vault_id=association.vault_id
                if association
                else "vault-" + proposal_id,
                import_id=association.import_id
                if association
                else "import-" + proposal_id,
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
                review_source=None
                if onboarding
                else current.preparation.payload_directory,
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
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
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
                        "history_retained": preparation.locator is not None,
                        "checkpoint_commit": preparation.locator.commit
                        if preparation.locator
                        else None,
                        "ready": False,
                        "next_actions": ("continue_review", "save_update"),
                    }
                )
            if preparation.kind == "attachment_cleanup":
                from .attachment_cleanup import refused

                history = self.observed.history if self.observed is not None else None
                if isinstance(error, lifecycle._ExcludedDependency):
                    return refused(
                        "excluded_dependency_requires_tracking",
                        history,
                        action="review_tracking",
                    )
                if error.args == ("reference_inventory_incomplete",):
                    return refused(
                        "reference_inventory_incomplete",
                        history,
                        action="review_tracking",
                    )
            return lifecycle._refused("save_unavailable", preparation=preparation)

    def close(self):
        self._clear_readonly_initial()
        self._apply_resume = None
        if self._closed:
            return
        self._closed = True
        try:
            try:
                if self._session is not None and not self._borrowed_apply_session:
                    self._session.close()
            finally:
                if self.observed is not None:
                    self.observed.__exit__()
                    self.observed = None
        finally:
            if self._apply_review_owners is not None:
                self._apply_review_owners.close()
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
