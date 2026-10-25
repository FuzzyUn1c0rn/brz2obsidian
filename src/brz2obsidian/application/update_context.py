"""One serialized unsaved producer context over the shared application seam."""

from pathlib import Path
from uuid import uuid4

from brz2obsidian.core import inspect_review_choices

from .contracts import request_identity
from .review_choices import (
    attachment_reference_destinations,
    attachment_reference_page,
    attachment_references,
    requirement_digest,
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

    def prepare(
        self,
        vault,
        *,
        selection_id,
        kind="source_update",
        source=None,
        original_source=None,
        cancel=None,
    ):
        if original_source is not None and kind != "onboarding":
            raise ValueError("Original reference evidence belongs to onboarding")
        if self._preparation is not None:
            return self._uncommitted_draft(code="close_decision_required")
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

    def page(self, binding, *, offset=0, limit=100, byte_offset=0, byte_limit=65536):
        def refused(code):
            return UpdateContextResult(status="refused", code=code, kind=self._kind)

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
        return UpdateContextResult(
            status=page.status,
            code=page.code,
            kind=self._kind,
            binding=self._binding,
            page=page,
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
            if (
                UpdateContextBinding.model_validate(binding) != self._binding
                or self._preparation is None
            ):
                raise ValueError("Context changed")
        except ValueError, TypeError:
            return UpdateContextResult(
                status="refused", code="context_changed", kind=self._kind
            )
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            return UpdateContextResult(
                status="refused", code="invalid_page", kind=self._kind
            )
        try:
            offers, total, following = attachment_reference_page(
                self._preparation, requirement_id, offset=offset, limit=limit
            )
        except ValueError, StopIteration:
            return UpdateContextResult(
                status="refused", code="offer_changed", kind=self._kind
            )
        return UpdateContextResult(
            status="available",
            code="available",
            kind=self._kind,
            binding=self._binding,
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
        return UpdateContextResult(
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
        )

    def choice_page(self, binding, *, offset=0, limit=100):
        from .review_offers import choice_page

        return self._choice_content(binding, choice_page, offset=offset, limit=limit)

    def choice_details(self, binding, *, requirement_id, offset=0, limit=100):
        from .review_offers import choice_detail_page

        return self._choice_content(
            binding,
            choice_detail_page,
            requirement_id=requirement_id,
            offset=offset,
            limit=limit,
        )

    def _choice_content(self, binding, reader, **kwargs):
        try:
            if (
                self._preparation is None
                or UpdateContextBinding.model_validate(binding) != self._binding
            ):
                raise ValueError("Context changed")
        except ValueError, TypeError:
            return UpdateContextResult(
                status="refused", code="context_changed", kind=self._kind
            )
        try:
            rows, total, following = reader(self._preparation, **kwargs)
        except ValueError, TypeError, StopIteration:
            return UpdateContextResult(
                status="refused",
                code="offer_changed",
                kind=self._kind,
                binding=self._binding,
            )
        return UpdateContextResult(
            status="available",
            code="available",
            kind=self._kind,
            binding=self._binding,
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

    def apply(self, binding, *, cancel=None):
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
        result = self._operations.apply_update(self._preparation, cancel=cancel)
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
        )

    def _project(self, result):
        self._remember(result)
        return UpdateContextResult(
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

    def save(self, binding):
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
        result = self._operations.save_update(self._preparation)
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

    def load(self, vault, *, selection_id):
        if self._preparation is not None:
            return self._uncommitted_draft(code="close_decision_required")
        request_identity(selection_id)
        self._reset_history()
        self._preparation = self._binding = None
        self._reference_drafts.clear()
        self._revision += 1
        result = self._operations.load_update(vault)
        self._kind = result.kind
        return self._project(result)

    def resume(self, vault, *, selection_id):
        if self._preparation is not None:
            return self._uncommitted_draft(code="close_decision_required")
        request_identity(selection_id)
        self._reset_history()
        self._preparation = self._binding = None
        self._reference_drafts.clear()
        self._revision += 1
        result = self._operations.resume_update(vault)
        return self._retain(result, selection_id=selection_id)

    def _uncommitted_draft(self, *, code="uncommitted_draft"):
        return UpdateContextResult(
            status="unresolved",
            code=code,
            kind=self._kind,
            binding=self._binding,
            unresolved=len(self._preparation.review.requirements),
            next_actions=("resolve_update", "discard_draft"),
            history_retained=self._last_history,
            checkpoint_commit=self._last_checkpoint,
        )

    def _remember(self, result):
        self._last_history = result.history_retained
        self._last_checkpoint = result.checkpoint_commit
        self._last_publication = result.publication
        self._last_status = result.status
        self._last_actions = result.next_actions

    def _reset_history(self):
        self._last_history = False
        self._last_checkpoint = None
        self._last_publication = "not_started"
        self._last_status = "unresolved"
        self._last_actions = ()

    def close(self, binding=None, *, choice):
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
            return UpdateContextResult(
                status="prepared_review"
                if self._preparation is not None
                else "unresolved",
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
                next_actions=self._last_actions,
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
            next_actions=self._last_actions
            if self._last_status in ("recovery_required", "publication_unknown")
            else (),
        )

    def stage_references(self, binding, *, requirement_id, choices):
        try:
            if (
                UpdateContextBinding.model_validate(binding) != self._binding
                or self._preparation is None
            ):
                raise ValueError("Context changed")
        except ValueError, TypeError:
            return UpdateContextResult(
                status="refused", code="context_changed", kind=self._kind
            )
        if self._edit is not None:
            return self._uncommitted_draft()
        try:
            destinations = attachment_reference_destinations(
                self._preparation, requirement_id
            )
            offered = {
                token: ("drop",)
                if self._kind == "attachment_cleanup"
                else tuple(row.choice for row in destinations[token])
                for token, _, _ in attachment_references(
                    self._preparation, requirement_id
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
            return UpdateContextResult(
                status="refused",
                code="offer_changed",
                kind=self._kind,
                binding=self._binding,
            )
        self._reference_drafts.setdefault(requirement_id, {}).update(
            (row.reference_id, row) for row in selected
        )
        self._revision += 1
        self._binding = self._binding.model_copy(update={"revision": self._revision})
        return UpdateContextResult(
            status="available",
            code="reference_choices_staged",
            kind=self._kind,
            binding=self._binding,
            changes=len(self._preparation.review.proposal.changes),
            unresolved=len(self._preparation.review.requirements),
        )

    def _edit_refusal(self, code):
        return UpdateContextResult(
            status="refused", code=code, kind=self._kind, binding=self._binding
        )

    def _checked_edit(self, value):
        try:
            handle = UpdateEditHandle.model_validate(value)
            if (
                self._edit is None
                or self._edit.handle != handle
                or handle.binding != self._binding
            ):
                raise ValueError("Edit changed")
            return handle
        except ValueError, TypeError:
            raise EditFailure("edit_changed") from None

    def begin_edit(self, binding, *, requirement_id, size, sha256):
        try:
            if (
                self._preparation is None
                or UpdateContextBinding.model_validate(binding) != self._binding
            ):
                raise EditFailure("context_changed")
            if self._edit is not None or self._reference_drafts:
                return self._uncommitted_draft()
            requirement = next(
                row
                for row in inspect_review_choices(self._preparation.review)
                if row.requirement_id == requirement_id
            )
            if "edited" not in requirement.enabled_choices:
                raise EditFailure("offer_changed")
            next_binding = self._binding.model_copy(
                update={"revision": self._revision + 1}
            )
            handle = UpdateEditHandle(
                edit_id=str(uuid4()),
                binding=next_binding,
                requirement_id=requirement_id,
                assumptions_digest=requirement_digest(requirement),
                size=size,
                sha256=sha256,
            )
            self._edit = EditLease(handle)
            self._revision += 1
            self._binding = next_binding
            return UpdateContextResult(
                status="available",
                code="edit_started",
                kind=self._kind,
                binding=self._binding,
                edit=self._edit.state,
            )
        except EditFailure as error:
            return self._edit_refusal(str(error))
        except ValueError, TypeError, StopIteration, OSError:
            return self._edit_refusal("edit_unavailable")

    def write_edit(self, handle, *, offset, data):
        try:
            self._checked_edit(handle)
            self._edit.write(offset=offset, data=data)
            return UpdateContextResult(
                status="available",
                code="edit_chunk_accepted",
                kind=self._kind,
                binding=self._binding,
                edit=self._edit.state,
            )
        except EditFailure as error:
            return self._edit_refusal(str(error))
        except OSError:
            return self._edit_refusal("edit_unavailable")

    def seal_edit(self, handle):
        try:
            self._checked_edit(handle)
            self._edit.seal()
            return UpdateContextResult(
                status="available",
                code="edit_sealed",
                kind=self._kind,
                binding=self._binding,
                edit=self._edit.state,
            )
        except EditFailure as error:
            return self._edit_refusal(str(error))
        except OSError:
            return self._edit_refusal("edit_unavailable")
