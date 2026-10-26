"""Private current shared history admission and explicit setup capability."""

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from .checkpoint_contracts import VaultHistoryInspection, VaultInitializationDecision
from .contract_values import request_identity
from .update_history_contracts import (
    HistoryContextBinding,
    UpdateHistoryActionState,
    UpdateHistoryCopyState,
    UpdateHistoryState,
)


class HistoryContext:
    def __init__(self, operations):
        self.operations = operations
        self.binding = self.admission = None
        self.preparation = None
        self._last_result = None
        self.revision = 0

    def _result(self, **values):
        from .update_context_contracts import UpdateContextResult

        return UpdateContextResult(kind="history", **values)

    def blocked(self, code="close_decision_required"):
        if self._last_result is not None:
            return self._last_result.model_copy(
                update={
                    "status": "refused",
                    "code": code,
                    "ready": False,
                    "binding": self.binding,
                }
            )
        return self._result(status="refused", code=code, binding=self.binding)

    @staticmethod
    def _state(admission):
        operation = admission.operation
        return UpdateHistoryState(
            status=admission.status,
            code=admission.code,
            operation=operation.model_copy(
                update={"message": operation.message[:2048]}
            ),
            history_retained=admission.history_retained,
            recovery_gap_count=len(admission.recovery_gaps),
            findings=admission.findings[:20],
            diagnostic_omission=len(admission.findings) > 20
            or len(operation.message) > 2048
            or len(admission.summary) > 2048,
            summary=admission.summary[:2048],
        )

    def inspect(self, vault, *, selection_id, cancel=None):
        request_identity(selection_id)
        if cancel is not None and cancel():
            self.binding = self.preparation = None
            self._last_result = self._result(
                status="cancelled_before_publication",
                code="cancelled_before_inspection",
                history_retained=None,
                publication="not_published",
                next_actions=("inspect_history",),
            )
            return self._last_result
        admission = self.operations.inspect_history_workflow(vault)
        self.revision += 1
        operation, checkpoint = admission.operation, admission.checkpoint
        self.admission = admission
        self.binding = HistoryContextBinding(
            context_id=str(uuid4()),
            selection_id=selection_id,
            vault=str(Path(vault).absolute()),
            revision=self.revision,
            fingerprint=sha256(admission.model_dump_json().encode()).hexdigest(),
            operation_id=operation.operation_id,
            operation_generation=operation.generation,
            intent_commit=operation.intent_commit,
            direction=operation.direction,
            association_id=checkpoint.association.association_id
            if checkpoint
            else None,
            checkpoint_commit=checkpoint.commit if checkpoint else None,
            checkpoint_generation=checkpoint.generation if checkpoint else None,
        )
        self._last_result = self._result(
            status=admission.status,
            code=admission.code,
            binding=self.binding,
            history_retained=admission.history_retained,
            checkpoint_commit=checkpoint.commit if checkpoint else None,
            next_actions=admission.next_actions,
            publication=operation.publication,
            history=self._state(admission),
        )
        if (
            cancel is not None
            and cancel()
            and admission.status in ("initialization_required", "onboarding_required")
        ):
            self.binding = None
            self._last_result = self._last_result.model_copy(
                update={
                    "status": "cancelled_before_publication",
                    "code": "cancelled_after_inspection",
                    "binding": None,
                    "publication": "not_published",
                    "next_actions": ("inspect_history",),
                }
            )
        return self._last_result

    def _matches(self, binding):
        try:
            return (
                self.binding is not None
                and HistoryContextBinding.model_validate(binding) == self.binding
            )
        except ValueError, TypeError:
            return False

    def _project(self, result):
        preparation = result.preparation
        changed_target = False
        if preparation is not None and preparation.kind == "recovery":
            native = preparation.native
            changed_target = (
                native.operation_id,
                native.generation,
                native.intent_commit,
                native.kind,
            ) != (
                self.binding.operation_id,
                self.binding.operation_generation,
                self.binding.intent_commit,
                self.admission.operation.kind,
            )
        elif preparation is not None and preparation.kind == "undo":
            native = preparation.native
            changed_target = (
                native.checkpoint_commit,
                native.generation,
                native.target_receipt_commit,
            ) != (
                self.binding.checkpoint_commit,
                self.binding.checkpoint_generation,
                self.binding.target_receipt_commit
                or self.admission.operation.receipt_commit,
            )
        elif preparation is not None and preparation.kind == "repair":
            validation = preparation.native.validation
            changed_target = any(
                expected is not None and actual != expected
                for expected, actual in (
                    (self.binding.association_id, validation.association_id),
                    (self.binding.checkpoint_commit, validation.target_commit),
                    (self.binding.checkpoint_generation, validation.target_generation),
                )
            )
        if changed_target:
            self.preparation = self.binding = None
            self._last_result = self._result(
                status="refused",
                code="history_target_changed",
                history_retained=self.admission.history_retained,
                publication=self.admission.operation.publication,
                history=self._state(self.admission),
                next_actions=("inspect_history",),
            )
            return self._last_result
        self.preparation = preparation
        if preparation is not None:
            prior = self.binding
            self.revision += 1
            native = preparation.native
            review = getattr(native, "review", None)
            authority = {}
            if preparation.kind == "recovery":
                authority = {
                    "operation_id": native.operation_id,
                    "operation_generation": native.generation,
                    "intent_commit": native.intent_commit,
                    "direction": native.direction,
                }
            elif preparation.kind == "undo":
                # Undo preparation names a current checkpoint/receipt target,
                # not a newly allocated operation identity or generation.
                authority = {
                    "checkpoint_commit": native.checkpoint_commit,
                    "checkpoint_generation": native.generation,
                    "target_receipt_commit": native.target_receipt_commit,
                }
            else:
                authority = {
                    "association_id": native.validation.association_id,
                    "checkpoint_commit": native.validation.target_commit,
                    "checkpoint_generation": native.validation.target_generation,
                }
            self.binding = prior.model_copy(
                update={
                    "revision": self.revision,
                    "fingerprint": sha256(
                        preparation.model_dump_json().encode()
                    ).hexdigest(),
                    **authority,
                    "proposal_id": review.proposal.proposal_id if review else None,
                    "review_generation": review.proposal.generation if review else None,
                }
            )
        else:
            self.binding = None
        operation = result.operation
        directions = (
            getattr(preparation.native, "available_directions", ())
            if preparation
            else ()
        )
        validation = result.copy_validation
        copy_state = (
            UpdateHistoryCopyState(
                status=validation.status,
                code=validation.code,
                association_id=validation.association_id,
                target_commit=validation.target_commit,
                target_generation=validation.target_generation,
                copy_commit=validation.copy_commit,
                copy_generation=validation.copy_generation,
                missing_objects=len(validation.missing_objects),
                damaged_objects=len(validation.damaged_objects),
            )
            if validation is not None
            else None
        )
        self._last_result = self._result(
            status="prepared_review"
            if preparation is not None and result.status != "direction_required"
            else result.status,
            code=result.code,
            binding=self.binding,
            ready=preparation.ready if preparation else False,
            unresolved=len(preparation.native.review.requirements)
            if preparation and getattr(preparation.native, "review", None)
            else 0,
            history_retained=result.history_retained
            if operation is not None or result.repair is not None
            else self.admission.history_retained,
            checkpoint_commit=operation.checkpoint_commit
            if operation
            else self.binding.checkpoint_commit
            if self.binding
            else None,
            publication=operation.publication
            if operation
            else self.admission.operation.publication,
            next_actions=result.next_actions,
            history_action=UpdateHistoryActionState(
                kind=result.kind,
                status=result.status,
                ready=preparation.ready if preparation else False,
                available_directions=directions,
                operation=operation.model_copy(
                    update={"message": operation.message[:2048]}
                )
                if operation
                else None,
                summary=result.summary[:2048],
                copy_validation=copy_state,
                repair=result.repair.model_copy(
                    update={"message": result.repair.message[:2048]}
                )
                if result.repair
                else None,
            ),
        )
        return self._last_result

    def prepare(self, binding, *, kind, direction=None, copy_path=None):
        if (
            not self._matches(binding)
            or self.admission is None
            or "review_" + ("history_repair" if kind == "repair" else kind)
            not in self.admission.next_actions
        ):
            return self._result(status="refused", code="context_changed")
        return self._project(
            self.operations.prepare_history_workflow(
                self.binding.vault, kind=kind, direction=direction, copy=copy_path
            )
        )

    def refresh(self, binding):
        if not self._matches(binding) or self.preparation is None:
            return self._result(status="refused", code="context_changed")
        return self._project(self.operations.refresh_history_workflow(self.preparation))

    def execute(self, binding, *, cancel=None, progress=None):
        if not self._matches(binding) or self.preparation is None:
            return self._result(status="refused", code="context_changed")
        return self._project(
            self.operations.execute_history_workflow(
                self.preparation, cancel=cancel, progress=progress
            )
        )

    def choice_page(self, binding, *, offset=0, limit=100):
        from .review_offers import review_plan_choice_page

        if (
            not self._matches(binding)
            or self.preparation is None
            or getattr(self.preparation.native, "review", None) is None
        ):
            return self.blocked("context_changed")
        try:
            rows, total, following = review_plan_choice_page(
                self.preparation.native.review, offset=offset, limit=limit
            )
        except ValueError, TypeError:
            return self.blocked("offer_changed")
        return self._last_result.model_copy(
            update={
                "status": "available",
                "ready": False,
                "offers": rows,
                "total_choices": total,
                "next_choice_offset": following,
            }
        )

    def choose(
        self, binding, *, requirement_id, choice, assumptions_digest, references=()
    ):
        from .review_choices import review_plan_choice_action

        if (
            not self._matches(binding)
            or self.preparation is None
            or getattr(self.preparation.native, "review", None) is None
        ):
            return self.blocked("context_changed")
        try:
            action = review_plan_choice_action(
                self.preparation.native.review,
                requirement_id=requirement_id,
                choice=choice,
                assumptions_digest=assumptions_digest,
                references=references,
            )
        except ValueError, TypeError, StopIteration:
            return self.blocked("offer_changed")
        return self._project(
            self.operations.resolve_history_workflow(self.preparation, action)
        )

    def close(self, binding, *, choice):
        try:
            expected = (
                HistoryContextBinding.model_validate(binding)
                if binding is not None
                else None
            )
            if expected != self.binding or self._last_result is None:
                raise ValueError("Context changed")
        except ValueError, TypeError:
            return self._result(status="refused", code="context_changed")
        if choice == "continue":
            return self._last_result.model_copy(update={"code": "continue_review"})
        if choice != "discard":
            return self._result(
                status="refused",
                code="history_save_unavailable",
                binding=self.binding,
                next_actions=("continue_review", "discard"),
            )
        values = {"code": "context_closed", "binding": None, "ready": False}
        if self.preparation is not None:
            values.update(
                status="recovery_required"
                if self.admission.operation.recovery_required
                else "no_content_change",
                history_action=None,
                history=self._state(self.admission),
                next_actions=("inspect_history",),
            )
        self.preparation = self.binding = None
        self._last_result = self._last_result.model_copy(update=values)
        return self._last_result

    def initialize(self, binding, *, choice):
        try:
            expected = HistoryContextBinding.model_validate(binding)
            if (
                expected != self.binding
                or self.admission is None
                or self.admission.status != "initialization_required"
                or self.admission.next_actions != ("initialize_vault",)
                or self.admission.initialization_fingerprint is None
            ):
                raise ValueError("History offer changed")
        except ValueError, TypeError:
            return self._result(status="refused", code="context_changed")
        result = self.operations.initialize_vault(
            expected.vault,
            decision=VaultInitializationDecision(
                schema_id="brz2obsidian.vault-initialization-decision",
                schema_version=1,
                observation_fingerprint=self.admission.initialization_fingerprint,
                choice=choice,
            ),
        )
        if result.status != "declined":
            self.binding = None
        post = None
        if result.status == "initialized_review_required":
            from .history_workflow import history_admission

            post = history_admission(
                VaultHistoryInspection(
                    schema_id="brz2obsidian.vault-history-inspection",
                    schema_version=1,
                    status="absent",
                    checkpoint=None,
                    admission=result.admission,
                ),
                self.operations.inspect_update_status(expected.vault),
            )
        self._last_result = self._result(
            status=result.status,
            code=result.status,
            binding=self.binding,
            repository_created=result.repository_created,
            history_retained=result.history_retained,
            next_actions=post.next_actions if post else ("inspect_history",),
            history=self._state(post) if post else None,
            publication=post.operation.publication if post else "not_started",
        )
        return self._last_result
