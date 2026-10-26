"""One serialized unsaved producer context over the shared application seam."""

from pathlib import Path
from uuid import uuid4

from brz2obsidian.core import inspect_review_choices

from .contracts import request_identity
from .review_choices import (
    requirement_digest,
    review_plan_attachment_reference_destinations,
    review_plan_attachment_reference_page,
    review_plan_attachment_references,
)
from .update_context_contracts import (
    UpdateChoiceOffer,
    UpdateContextBinding,
    UpdateContextResult,
    UpdateEditHandle,
    UpdateReferenceChoice,
)
from .update_contracts import UpdatePreparation
from .update_edits import EditFailure, EditLease


class UpdateContext:
    """Retain canonical preparations; public handles never become authority."""

    def __init__(self, *, operations=None):
        if operations is None:
            from .operations import Operations

            operations = Operations()
        self._operations = operations
        from .update_history_context import HistoryContext

        self._history = HistoryContext(operations)
        self._preparation = None
        self._binding = None
        self._revision = 0
        self._kind = "source_update"
        self._reference_drafts = {}
        self._edit = None
        self._reset_history()

    @property
    def kind(self):
        return self._kind

    @property
    def draft_pending(self):
        return self._edit is not None or bool(self._reference_drafts)

    def prepare(
        self,
        vault,
        *,
        selection_id,
        kind="source_update",
        source=None,
        original_source=None,
        cancel=None,
        progress=None,
    ):
        if original_source is not None and kind != "onboarding":
            raise ValueError("Original reference evidence belongs to onboarding")
        if (
            self._preparation is not None
            or self._history.preparation is not None
            or self.draft_pending
        ):
            return self._uncommitted_draft(code="close_decision_required")
        self._history.binding = self._history.admission = None
        request_identity(selection_id)
        self._reset_history()
        # Selecting new work retires the prior handle even if preparation refuses.
        self._binding = self._preparation = None
        self._reference_drafts.clear()
        self._revision += 1
        self._kind = kind
        if cancel is not None and cancel():
            cancelled = UpdateContextResult(
                status="cancelled_before_publication",
                code="cancelled_before_preparation",
                kind=kind,
                publication="not_published",
            )
            self._remember(cancelled)
            return cancelled
        from .vault_progress_contracts import report_progress

        report_progress(progress, "current_inspection")
        if kind == "attachment_cleanup":
            result = self._operations.prepare_attachment_cleanup(vault)
        elif kind == "onboarding":
            result = self._operations.prepare_onboarding(
                vault, source, original_source=original_source
            )
        elif kind == "format_transition":
            result = self._operations.prepare_format_transition(vault, source)
        elif kind == "source_update":
            result = self._operations.prepare_update(vault, source)
        else:
            raise ValueError("Unsupported update role")
        if result.preparation is not None:
            prepared = UpdatePreparation.model_validate(result.preparation)
            locator = prepared.locator
            self._preparation = prepared
            self._binding = UpdateContextBinding(
                context_id=str(uuid4()),
                selection_id=selection_id,
                vault=str(Path(prepared.vault).absolute()),
                association_id=locator.association.association_id if locator else None,
                checkpoint_commit=locator.commit if locator else None,
                checkpoint_generation=locator.generation if locator else None,
                proposal_id=prepared.review.proposal.proposal_id,
                generation=prepared.review.proposal.generation,
                revision=self._revision,
            )
        cancelled = cancel is not None and cancel()
        self._remember(result)
        return UpdateContextResult(
            status="cancelled_before_publication" if cancelled else result.status,
            code=result.code,
            kind=result.kind,
            binding=self._binding,
            ready=False if cancelled else result.ready,
            changes=result.changes,
            unresolved=result.unresolved,
            stale=result.stale,
            next_actions=result.next_actions,
            history_retained=result.history_retained,
            checkpoint_commit=result.checkpoint_commit,
            publication="not_published" if cancelled else result.publication,
        )

    def history(self, vault, *, selection_id, cancel=None):
        if self._history.preparation is not None:
            return self._history.blocked()
        if self._preparation is not None or self.draft_pending:
            return self._uncommitted_draft(code="close_decision_required")
        self._reset_history()
        self._kind = "history"
        result = self._history.inspect(vault, selection_id=selection_id, cancel=cancel)
        self._remember(result)
        return result

    def initialize_vault(self, binding, *, choice):
        if self._preparation is not None or self.draft_pending:
            return self._uncommitted_draft(code="close_decision_required")
        result = self._history.initialize(binding, choice=choice)
        self._remember(result)
        return result

    def prepare_history(self, binding, **values):
        if self.draft_pending:
            return self._uncommitted_draft()
        result = self._history.prepare(binding, **values)
        self._remember(result)
        return result

    def refresh_history(self, binding, *, cancel=None, progress=None):
        if self.draft_pending:
            return self._uncommitted_draft()
        result = self._history.refresh(binding, cancel=cancel, progress=progress)
        self._remember(result)
        return result

    def execute_history(self, binding, *, cancel=None, progress=None):
        if self.draft_pending:
            return self._uncommitted_draft()
        result = self._history.execute(binding, cancel=cancel, progress=progress)
        self._remember(result)
        return result

    def history_choices(self, binding, **values):
        return self._history.choice_page(binding, **values)

    def choose_history(self, binding, **values):
        edit_handle = values.pop("edit_handle", None)
        edited = None
        if self._edit is not None:
            if values["choice"] != "edited":
                return self._uncommitted_draft()
            try:
                handle = self._checked_edit(edit_handle)
                if (
                    handle.requirement_id != values["requirement_id"]
                    or handle.assumptions_digest != values["assumptions_digest"]
                ):
                    raise EditFailure("edit_changed")
                edited = self._edit.content()
            except EditFailure as error:
                return self._edit_refusal(str(error))
        elif values["choice"] == "edited":
            return self._edit_refusal("edit_changed")
        requirement_id = values["requirement_id"]
        values["references"] = (
            tuple(self._reference_drafts.get(requirement_id, {}).values())
            if values.get("references") is None
            else values["references"]
        )
        result = self._history.choose(binding, **values, edited=edited)
        if (
            result.status == "prepared_review"
            and result.binding != binding
            and self._edit is not None
        ):
            self._edit.close()
            self._edit = None
        if result.status == "prepared_review" and result.binding != binding:
            self._reference_drafts.pop(requirement_id, None)
        self._remember(result)
        return result

    def page(self, binding, *, offset=0, limit=100, byte_offset=0, byte_limit=65536):
        if self._kind == "history":
            return self._history.page(
                binding,
                offset=offset,
                limit=limit,
                byte_offset=byte_offset,
                byte_limit=byte_limit,
            )

        def refused(code):
            return self._edit_refusal(code)

        try:
            expected = UpdateContextBinding.model_validate(binding)
        except ValueError, TypeError:
            return refused("context_changed")
        if self._preparation is None or expected != self._binding:
            return refused("context_changed")
        if (
            any(
                type(value) is not int or value < 0
                for value in (offset, limit, byte_offset, byte_limit)
            )
            or not 1 <= limit <= 100
            or byte_limit > 65536
        ):
            return refused("invalid_page")
        page = self._operations.inspect_update_review(
            self._preparation,
            proposal_id=expected.proposal_id,
            generation=expected.generation,
            offset=offset,
            limit=limit,
            byte_offset=byte_offset,
            byte_limit=byte_limit,
        )
        if page.status == "refused" and page.code == "association_or_history_changed":
            self._preparation = self._binding = None
            self._requires_source_refresh = False
            result = UpdateContextResult(
                status="publication_unknown",
                code=page.code,
                kind=self._kind,
                history_retained=None,
                publication="unknown",
                next_actions=("inspect_history",),
            )
            self._remember(result)
            return result
        if page.code == "source_payload_changed":
            self._requires_source_refresh = True
        return self._content_result(
            status=page.status,
            code=page.code,
            binding=self._binding,
            page=page,
            next_actions=("refresh_update",)
            if page.code == "source_payload_changed"
            else (),
            configuration=self._operations.configuration_choice_offer(self._preparation)
            if page.status == "available" and self._kind == "format_transition"
            else None,
            offers=tuple(
                UpdateChoiceOffer(
                    requirement_id=row.requirement_id,
                    change_id=row.change_id,
                    domain=row.domain,
                    choices=row.enabled_choices,
                    unavailable_choices=tuple(
                        choice for choice in row.availability if not choice.enabled
                    ),
                    assumptions_digest=requirement_digest(row),
                    selected=next(
                        (
                            a.choice
                            for a in self._preparation.review.approvals
                            if a.change_id == row.change_id and a.domain == row.domain
                        ),
                        None,
                    ),
                    decision_id=next(
                        (
                            a.decision_id
                            for a in self._preparation.review.approvals
                            if a.change_id == row.change_id and a.domain == row.domain
                        ),
                        None,
                    ),
                )
                for row in (
                    inspect_review_choices(self._preparation.review)
                    if page.status == "available"
                    else ()
                )
                if page.status == "available"
                and row.change_id in {item.change_id for item in page.items}
            ),
        )

    def reference_page(self, binding, *, requirement_id, offset=0, limit=100):
        try:
            plan = self._live_review(binding)
        except EditFailure:
            return self._edit_refusal("context_changed")
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            return self._edit_refusal("invalid_page")
        try:
            offers, total, following = review_plan_attachment_reference_page(
                plan,
                requirement_id,
                offset=offset,
                limit=limit,
                drop_only=self._kind == "attachment_cleanup",
            )
        except ValueError, StopIteration:
            return self._edit_refusal("offer_changed")
        return self._content_result(
            status="available",
            code="available",
            binding=self._review_binding(),
            references=tuple(
                offer.model_copy(
                    update={
                        "selected": self._reference_drafts[requirement_id][
                            offer.reference_id
                        ].choice
                    }
                )
                if offer.reference_id in self._reference_drafts.get(requirement_id, {})
                else offer
                for offer in offers
            ),
            total_references=total,
            next_reference_offset=following,
        )

    def choose(
        self,
        binding,
        *,
        requirement_id,
        choice,
        assumptions_digest,
        references=None,
        edit_handle=None,
        selected_entry_id=None,
        disassociate_entry_ids=(),
    ):
        try:
            expected = UpdateContextBinding.model_validate(binding)
            if self._preparation is None or expected != self._binding:
                raise ValueError("Context changed")
        except ValueError, TypeError:
            return UpdateContextResult(
                status="refused", code="context_changed", kind=self._kind
            )
        edited = None
        if self._edit is not None:
            if choice != "edited":
                return self._uncommitted_draft()
            try:
                handle = self._checked_edit(edit_handle)
                if (
                    handle.requirement_id != requirement_id
                    or handle.assumptions_digest != assumptions_digest
                ):
                    raise EditFailure("edit_changed")
                edited = self._edit.content()
            except EditFailure as error:
                return self._edit_refusal(str(error))
        elif choice == "edited":
            return self._edit_refusal("edit_changed")
        try:
            result = self._operations.resolve_update_choice(
                self._preparation,
                requirement_id=requirement_id,
                choice=choice,
                assumptions_digest=assumptions_digest,
                references=tuple(
                    self._reference_drafts.get(requirement_id, {}).values()
                )
                if references is None
                else references,
                edited=edited,
                selected_entry_id=selected_entry_id,
                disassociate_entry_ids=disassociate_entry_ids,
            )
        except ValueError, StopIteration:
            return UpdateContextResult(
                status="refused",
                code="offer_changed",
                kind=self._kind,
                binding=self._binding,
            )
        self._remember(result)
        if result.code == "accepted" and result.preparation is not None:
            if self._edit is not None:
                self._edit.close()
                self._edit = None
            self._reference_drafts.pop(requirement_id, None)
            self._preparation = UpdatePreparation.model_validate(result.preparation)
            self._revision += 1
            self._binding = self._binding.model_copy(
                update={
                    "generation": self._preparation.review.proposal.generation,
                    "revision": self._revision,
                }
            )
        return self._source_projection(
            UpdateContextResult(
                status=result.status,
                code=result.code,
                kind=result.kind,
                binding=self._binding,
                ready=result.ready and not self.draft_pending,
                changes=result.changes,
                unresolved=result.unresolved,
                stale=result.stale,
                next_actions=result.next_actions,
                history_retained=result.history_retained,
                checkpoint_commit=result.checkpoint_commit,
                publication=result.publication,
            )
        )

    def choice_page(self, binding, *, offset=0, limit=100):
        from .review_offers import review_plan_choice_page

        return self._choice_content(
            binding, review_plan_choice_page, offset=offset, limit=limit
        )

    def choice_details(self, binding, *, requirement_id, offset=0, limit=100):
        from .review_offers import review_plan_choice_detail_page

        return self._choice_content(
            binding,
            review_plan_choice_detail_page,
            requirement_id=requirement_id,
            offset=offset,
            limit=limit,
        )

    def _choice_content(self, binding, reader, **kwargs):
        try:
            plan = self._live_review(binding)
        except EditFailure:
            return self._edit_refusal("context_changed")
        try:
            rows, total, following = reader(plan, **kwargs)
        except ValueError, TypeError, StopIteration:
            return self._edit_refusal("offer_changed")
        return self._content_result(
            status="available",
            code="available",
            binding=self._review_binding(),
            **(
                {
                    "choice_details": rows,
                    "total_choice_details": total,
                    "next_choice_detail_offset": following,
                }
                if "requirement_id" in kwargs
                else {
                    "offers": rows,
                    "total_choices": total,
                    "next_choice_offset": following,
                }
            ),
        )

    def apply(self, binding, *, cancel=None, progress=None):
        try:
            expected = UpdateContextBinding.model_validate(binding)
            if self._preparation is None or expected != self._binding:
                raise ValueError("Context changed")
        except ValueError, TypeError:
            return UpdateContextResult(
                status="refused", code="context_changed", kind=self._kind
            )
        if self._reference_drafts or self._edit is not None:
            return self._uncommitted_draft()
        if self._requires_source_refresh:
            return self._content_result(
                status="stale_review",
                code="source_payload_changed",
                binding=self._binding,
            )
        result = self._operations.apply_update(
            self._preparation,
            cancel=cancel,
            **({"progress": progress} if progress is not None else {}),
        )
        self._remember(result)
        if (
            result.application is None
            and result.preparation is not None
            and result.publication in ("not_started", "not_published")
            and result.status
            not in ("publication_unknown", "recovery_required", "failed")
        ):
            return self._retain(result, selection_id=expected.selection_id)
        # Any attempted native mutation retires prior readiness; current native
        # inspection/resume supplies the next authority, including cancellation.
        self._preparation = self._binding = None
        return UpdateContextResult(
            status=result.status,
            code=result.code,
            kind=result.kind,
            ready=False,
            changes=result.changes,
            unresolved=result.unresolved,
            stale=result.stale,
            next_actions=result.next_actions,
            history_retained=result.history_retained,
            checkpoint_commit=result.checkpoint_commit,
            publication=result.publication,
            operation=self._last_operation,
            capture=self._last_capture,
        )

    def _project(self, result):
        self._remember(result)
        return self._source_projection(
            UpdateContextResult(
                status=result.status,
                code=result.code,
                kind=result.kind,
                binding=self._binding,
                ready=result.ready,
                changes=result.changes,
                unresolved=result.unresolved,
                stale=result.stale,
                next_actions=result.next_actions,
                history_retained=result.history_retained,
                checkpoint_commit=result.checkpoint_commit,
                publication=result.publication,
                operation=self._last_operation,
                capture=self._last_capture,
            )
        )

    def _retain(self, result, *, selection_id):
        self._kind = result.kind
        if result.preparation is not None:
            prepared = UpdatePreparation.model_validate(result.preparation)
            locator = prepared.locator
            old = self._binding
            self._revision += 1
            self._preparation = prepared
            self._binding = UpdateContextBinding(
                context_id=old.context_id if old else str(uuid4()),
                selection_id=selection_id,
                vault=str(Path(prepared.vault).absolute()),
                association_id=locator.association.association_id if locator else None,
                checkpoint_commit=locator.commit if locator else None,
                checkpoint_generation=locator.generation if locator else None,
                proposal_id=prepared.review.proposal.proposal_id,
                generation=prepared.review.proposal.generation,
                revision=self._revision,
            )
        return self._project(result)

    def save(self, binding, *, cancel=None, progress=None):
        try:
            expected = UpdateContextBinding.model_validate(binding)
            if self._preparation is None or expected != self._binding:
                raise ValueError("Context changed")
        except ValueError, TypeError:
            return UpdateContextResult(
                status="refused", code="context_changed", kind=self._kind
            )
        if self._reference_drafts or self._edit is not None:
            return self._uncommitted_draft()
        if self._requires_source_refresh:
            return self._content_result(
                status="stale_review",
                code="source_payload_changed",
                binding=self._binding,
            )
        if cancel is not None and cancel():
            return UpdateContextResult(
                status="cancelled_before_publication",
                code="cancelled_before_snapshot",
                kind=self._kind,
                binding=self._binding,
                ready=False,
                history_retained=self._last_history,
                checkpoint_commit=self._last_checkpoint,
                publication="not_published",
                capture=self._last_capture,
                next_actions=("continue_review", "save_update"),
            )
        result = self._operations.save_update(
            self._preparation,
            **({"progress": progress} if progress is not None else {}),
            **({"cancel": cancel} if cancel is not None else {}),
        )
        return self._retain(result, selection_id=expected.selection_id)

    def refresh(self, binding, *, source=None, cancel=None, progress=None):
        try:
            expected = UpdateContextBinding.model_validate(binding)
            if self._preparation is None or expected != self._binding:
                raise ValueError("Context changed")
        except ValueError, TypeError:
            return self._edit_refusal("context_changed")
        if self.draft_pending:
            return self._uncommitted_draft()
        if cancel is not None and cancel():
            return UpdateContextResult(
                status="cancelled_before_publication",
                code="cancelled_before_refresh",
                kind=self._kind,
                binding=self._binding,
                ready=False,
                history_retained=self._last_history,
                checkpoint_commit=self._last_checkpoint,
                publication="not_published",
                next_actions=("continue_review", "refresh_update"),
            )
        from .vault_progress_contracts import report_progress

        report_progress(progress, "current_inspection")
        result = self._operations.refresh_update(self._preparation, source=source)
        if result.preparation is not None and result.status in (
            "prepared_review",
            "unresolved",
            "stale_review",
        ):
            self._requires_source_refresh = False
        if (
            cancel is not None
            and cancel()
            and result.preparation is not None
            and result.status
            not in ("recovery_required", "publication_unknown", "failed")
            and result.publication not in ("partial", "complete", "unknown")
        ):
            result = result.model_copy(
                update={
                    "status": "cancelled_before_publication",
                    "code": "cancelled_after_refresh",
                    "ready": False,
                }
            )
        return self._retain(result, selection_id=expected.selection_id)

    def choose_configuration(self, binding, *, group_id, choice):
        try:
            expected = UpdateContextBinding.model_validate(binding)
            if self._preparation is None or expected != self._binding:
                raise ValueError("Context changed")
        except ValueError, TypeError:
            return self._edit_refusal("context_changed")
        if self._edit is not None or self._reference_drafts:
            return self._uncommitted_draft()
        result = self._operations.resolve_configuration_choice(
            self._preparation, group_id=group_id, choice=choice
        )
        return self._retain(result, selection_id=expected.selection_id)

    def load(self, vault, *, selection_id, cancel=None):
        if (
            self._preparation is not None
            or self._history.preparation is not None
            or self.draft_pending
        ):
            return self._uncommitted_draft(code="close_decision_required")
        request_identity(selection_id)
        self._reset_history()
        self._preparation = self._binding = None
        self._reference_drafts.clear()
        self._revision += 1
        if cancel is not None and cancel():
            return self._cancelled_inspection()
        result = self._operations.load_update(vault)
        self._kind = result.kind
        if (
            cancel is not None
            and cancel()
            and result.status
            not in ("publication_unknown", "recovery_required", "failed")
            and result.publication not in ("partial", "unknown")
        ):
            return self._cancelled_inspection(result)
        return self._project(result)

    def resume(self, vault, *, selection_id, cancel=None):
        if (
            self._preparation is not None
            or self._history.preparation is not None
            or self.draft_pending
        ):
            return self._uncommitted_draft(code="close_decision_required")
        request_identity(selection_id)
        self._reset_history()
        self._preparation = self._binding = None
        self._reference_drafts.clear()
        self._revision += 1
        if cancel is not None and cancel():
            return self._cancelled_inspection()
        result = self._operations.resume_update(vault)
        self._kind = result.kind
        if (
            cancel is not None
            and cancel()
            and result.status
            not in ("publication_unknown", "recovery_required", "failed")
            and result.publication not in ("partial", "unknown")
        ):
            return self._cancelled_inspection(result)
        return self._retain(result, selection_id=selection_id)

    def _cancelled_inspection(self, result=None):
        observed = UpdateContextResult(
            status="cancelled_before_publication",
            code="cancelled_after_inspection"
            if result is not None
            else "cancelled_before_inspection",
            kind=result.kind if result is not None else self._kind,
            history_retained=result.history_retained if result is not None else None,
            checkpoint_commit=result.checkpoint_commit if result is not None else None,
            publication="not_published",
            next_actions=("inspect_history",),
        )
        self._remember(observed)
        return observed

    def _uncommitted_draft(self, *, code="uncommitted_draft"):
        if self._history.preparation is not None:
            return self._history.blocked(code)
        return self._content_result(
            status="unresolved" if self._preparation is not None else self._last_status,
            code=code,
            binding=self._binding,
            unresolved=len(self._preparation.review.requirements)
            if self._preparation is not None
            else 0,
            next_actions=("resolve_update", "discard_draft")
            if self._binding is not None
            else ("continue_review", "discard"),
        )

    def _remember(self, result):
        capture = getattr(result, "capture", None)
        self._last_capture = (
            capture.model_copy(
                update={
                    "message": capture.message[:2036] + " [truncated]"
                    if len(capture.message) > 2048
                    else capture.message
                }
            )
            if capture is not None
            else None
        )
        native = getattr(result, "application", None)
        self._last_operation = (
            native.model_copy(
                update={
                    "message": native.message[:2036] + " [truncated]"
                    if len(native.message) > 2048
                    else native.message
                }
            )
            if native is not None
            else None
        )
        self._last_history = result.history_retained
        self._last_checkpoint = result.checkpoint_commit
        self._last_publication = result.publication
        self._last_status = result.status
        self._last_actions = result.next_actions

    def _reset_history(self):
        self._requires_source_refresh = False
        self._last_capture = None
        self._last_operation = None
        self._last_history = False
        self._last_checkpoint = None
        self._last_publication = "not_started"
        self._last_status = "unresolved"
        self._last_actions = ()

    def close(self, binding=None, *, choice):
        if self._kind == "history":
            if self.draft_pending and choice == "continue":
                return self._uncommitted_draft(code="continue_review")
            result = self._history.close(binding, choice=choice)
            if result.code == "context_closed":
                if self._edit is not None:
                    self._edit.close()
                    self._edit = None
                self._reference_drafts.clear()
            self._remember(result)
            return result
        try:
            expected = (
                UpdateContextBinding.model_validate(binding)
                if binding is not None
                else None
            )
            if expected != self._binding:
                raise ValueError("Context changed")
        except ValueError, TypeError:
            return self._edit_refusal("context_changed")
        if choice == "continue":
            if self._edit is not None or self._reference_drafts:
                return self._uncommitted_draft(code="continue_review")
            return self._source_projection(
                UpdateContextResult(
                    status="prepared_review"
                    if self._preparation is not None
                    else self._last_status,
                    code="continue_review",
                    kind=self._kind,
                    binding=self._binding,
                    ready=self._preparation.review.ready
                    if self._preparation is not None
                    else False,
                    unresolved=len(self._preparation.review.requirements)
                    if self._preparation is not None
                    else 0,
                    history_retained=self._last_history,
                    checkpoint_commit=self._last_checkpoint,
                    publication=self._last_publication,
                    operation=self._last_operation
                    if self._preparation is None
                    else None,
                    capture=self._last_capture,
                    next_actions=self._last_actions,
                )
            )
        if choice == "save":
            saved = self.save(binding)
            if saved.code != "saved":
                return saved
        elif choice != "discard":
            return self._edit_refusal("invalid_close_choice")
        if self._edit is not None:
            self._edit.close()
            self._edit = None
        self._reference_drafts.clear()
        self._preparation = self._binding = None
        self._requires_source_refresh = False
        return UpdateContextResult(
            status=self._last_status
            if self._last_status
            in (
                "applied",
                "recovery_required",
                "publication_unknown",
                "failed",
                "cancelled_before_publication",
            )
            else "no_content_change",
            code="context_closed",
            kind=self._kind,
            history_retained=self._last_history,
            checkpoint_commit=self._last_checkpoint,
            publication=self._last_publication,
            operation=self._last_operation,
            capture=self._last_capture,
            next_actions=self._last_actions
            if self._last_status in ("recovery_required", "publication_unknown")
            else (),
        )

    def stage_references(self, binding, *, requirement_id, choices):
        try:
            plan = self._live_review(binding)
        except EditFailure:
            return self._edit_refusal("context_changed")
        if self._edit is not None:
            return self._uncommitted_draft()
        try:
            destinations = review_plan_attachment_reference_destinations(
                plan, requirement_id
            )
            offered = {
                token: ("drop",)
                if self._kind == "attachment_cleanup"
                else tuple(row.choice for row in destinations[token])
                for token, _, _ in review_plan_attachment_references(
                    plan, requirement_id
                )
            }
            selected = tuple(
                UpdateReferenceChoice.model_validate(row) for row in choices
            )
            if (
                not 1 <= len(selected) <= 100
                or len({row.reference_id for row in selected}) != len(selected)
                or any(
                    row.reference_id not in offered
                    or row.choice not in offered[row.reference_id]
                    for row in selected
                )
            ):
                raise ValueError("Reference offer changed")
        except ValueError, TypeError, StopIteration:
            return self._edit_refusal("offer_changed")
        self._reference_drafts.setdefault(requirement_id, {}).update(
            (row.reference_id, row) for row in selected
        )
        current = self._review_binding()
        self._retain_review_binding(
            current.model_copy(update={"revision": current.revision + 1})
        )
        return self._content_result(
            status="available",
            code="reference_choices_staged",
            binding=self._review_binding(),
            changes=len(plan.proposal.changes),
            unresolved=len(plan.requirements),
        )

    def _edit_refusal(self, code):
        if self._kind == "history":
            return self._history.blocked(code)
        return self._content_result(status="refused", code=code, binding=self._binding)

    def discard_draft(self, binding):
        try:
            plan = self._live_review(binding)
        except EditFailure:
            return self._edit_refusal("context_changed")
        if self._edit is not None:
            self._edit.close()
            self._edit = None
        self._reference_drafts.clear()
        current = self._review_binding()
        self._retain_review_binding(
            current.model_copy(update={"revision": current.revision + 1})
        )
        if self._kind == "history":
            result = self._history._last_result.model_copy(
                update={
                    "status": "prepared_review",
                    "code": "draft_discarded",
                    "ready": self._history.preparation.ready,
                }
            )
            self._history._last_result = result
            return result
        return self._source_projection(
            UpdateContextResult(
                status="prepared_review" if plan.ready else "unresolved",
                code="draft_discarded",
                kind=self._kind,
                binding=self._binding,
                ready=plan.ready,
                changes=len(plan.proposal.changes),
                unresolved=len(plan.requirements),
                history_retained=self._last_history,
                checkpoint_commit=self._last_checkpoint,
                publication=self._last_publication,
                next_actions=self._last_actions,
            )
        )

    def _review_binding(self):
        return self._history.binding if self._kind == "history" else self._binding

    def _live_review(self, binding):
        if self._kind == "history":
            if (
                not self._history._matches(binding)
                or self._history.preparation is None
                or getattr(self._history.preparation.native, "review", None) is None
            ):
                raise EditFailure("context_changed")
            return self._history.preparation.native.review
        try:
            if (
                self._preparation is None
                or UpdateContextBinding.model_validate(binding) != self._binding
            ):
                raise ValueError("Context changed")
            return self._preparation.review
        except ValueError, TypeError:
            raise EditFailure("context_changed") from None

    def _retain_review_binding(self, binding):
        if self._kind == "history":
            self._history.binding = binding
            self._history.revision = binding.revision
            self._history._last_result = self._history._last_result.model_copy(
                update={"binding": binding}
            )
        else:
            self._binding = binding
            self._revision = binding.revision

    def _edit_result(self, code):
        values = {
            "status": "available",
            "code": code,
            "ready": False,
            "binding": self._review_binding(),
            "edit": self._edit.state,
        }
        return self._content_result(**values)

    def _source_projection(self, result):
        # Native debt has its own inspection/recovery route and supersedes refresh.
        if result.publication in ("partial", "unknown") or result.status in (
            "publication_unknown",
            "recovery_required",
        ):
            self._requires_source_refresh = False
        if not self._requires_source_refresh:
            return result
        return result.model_copy(
            update={
                "ready": False,
                "next_actions": ("refresh_update",),
                "status": "stale_review"
                if result.status in ("prepared_review", "unresolved")
                else result.status,
            }
        )

    def _content_result(self, **values):
        if self._kind == "history":
            return self._history._last_result.model_copy(
                update={"ready": False, **values}
            )
        return self._source_projection(
            UpdateContextResult(
                kind=self._kind,
                **{
                    "history_retained": self._last_history,
                    "checkpoint_commit": self._last_checkpoint,
                    "publication": self._last_publication,
                    "capture": self._last_capture,
                    **values,
                },
            )
        )

    def _checked_edit(self, value):
        try:
            handle = UpdateEditHandle.model_validate(value)
            if (
                self._edit is None
                or self._edit.handle != handle
                or handle.binding != self._review_binding()
            ):
                raise ValueError("Edit changed")
            return handle
        except ValueError, TypeError:
            raise EditFailure("edit_changed") from None

    def begin_edit(self, binding, *, requirement_id, size, sha256):
        try:
            plan = self._live_review(binding)
            if self._edit is not None or self._reference_drafts:
                return self._uncommitted_draft()
            requirement = next(
                row
                for row in inspect_review_choices(plan)
                if row.requirement_id == requirement_id
            )
            if "edited" not in requirement.enabled_choices:
                raise EditFailure("offer_changed")
            current = self._review_binding()
            next_binding = current.model_copy(update={"revision": current.revision + 1})
            handle = UpdateEditHandle(
                edit_id=str(uuid4()),
                binding=next_binding,
                requirement_id=requirement_id,
                assumptions_digest=requirement_digest(requirement),
                size=size,
                sha256=sha256,
            )
            self._edit = EditLease(handle)
            self._retain_review_binding(next_binding)
            return self._edit_result("edit_started")
        except EditFailure as error:
            return self._edit_refusal(str(error))
        except ValueError, TypeError, StopIteration, OSError:
            return self._edit_refusal("edit_unavailable")

    def write_edit(self, handle, *, offset, data):
        try:
            self._checked_edit(handle)
            self._edit.write(offset=offset, data=data)
            return self._edit_result("edit_chunk_accepted")
        except EditFailure as error:
            return self._edit_refusal(str(error))
        except OSError:
            return self._edit_refusal("edit_unavailable")

    def seal_edit(self, handle):
        try:
            self._checked_edit(handle)
            self._edit.seal()
            return self._edit_result("edit_sealed")
        except EditFailure as error:
            return self._edit_refusal(str(error))
        except OSError:
            return self._edit_refusal("edit_unavailable")
