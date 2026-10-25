"""One serialized unsaved producer context over the shared application seam."""

from pathlib import Path
from uuid import uuid4

from .contracts import request_identity
from .review_choices import attachment_references, requirement_digest
from .update_context_contracts import (
    UpdateChoiceOffer,
    UpdateContextBinding,
    UpdateContextResult,
    UpdateReferenceOffer,
)
from .update_contracts import UpdatePreparation


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

    @property
    def kind(self):
        return self._kind

    def prepare(
        self, vault, *, selection_id, kind="source_update", source=None, cancel=None
    ):
        request_identity(selection_id)
        # Selecting new work retires the prior handle even if preparation refuses.
        self._binding = self._preparation = None
        self._revision += 1
        self._kind = kind
        if cancel is not None and cancel():
            return UpdateContextResult(
                status="cancelled_before_publication",
                code="cancelled_before_preparation",
                kind=kind,
                publication="not_published",
            )
        if kind == "attachment_cleanup":
            result = self._operations.prepare_attachment_cleanup(vault)
        elif kind == "onboarding":
            result = self._operations.prepare_onboarding(vault, source)
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
            offers=tuple(
                UpdateChoiceOffer(
                    requirement_id=row.requirement_id,
                    change_id=row.change_id,
                    domain=row.domain,
                    choices=row.choices,
                    assumptions_digest=requirement_digest(row),
                )
                for row in self._preparation.review.requirements
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
            refs = attachment_references(self._preparation, requirement_id)
        except ValueError, StopIteration:
            return UpdateContextResult(
                status="refused", code="offer_changed", kind=self._kind
            )
        end = min(len(refs), offset + limit)
        return UpdateContextResult(
            status="available",
            code="available",
            kind=self._kind,
            binding=self._binding,
            references=tuple(
                UpdateReferenceOffer(
                    reference_id=token,
                    document_id=doc.document_id,
                    occurrence_id=occ.occurrence_id,
                )
                for token, doc, occ in refs[offset:end]
            ),
            total_references=len(refs),
            next_reference_offset=end if end < len(refs) else None,
        )

    def choose(
        self, binding, *, requirement_id, choice, assumptions_digest, references=()
    ):
        try:
            expected = UpdateContextBinding.model_validate(binding)
            if self._preparation is None or expected != self._binding:
                raise ValueError("Context changed")
        except ValueError, TypeError:
            return UpdateContextResult(
                status="refused", code="context_changed", kind=self._kind
            )
        try:
            result = self._operations.resolve_update_choice(
                self._preparation,
                requirement_id=requirement_id,
                choice=choice,
                assumptions_digest=assumptions_digest,
                references=references,
            )
        except ValueError, StopIteration:
            return UpdateContextResult(
                status="refused",
                code="offer_changed",
                kind=self._kind,
                binding=self._binding,
            )
        if result.code == "accepted" and result.preparation is not None:
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

    def apply(self, binding, *, cancel=None):
        try:
            expected = UpdateContextBinding.model_validate(binding)
            if self._preparation is None or expected != self._binding:
                raise ValueError("Context changed")
        except ValueError, TypeError:
            return UpdateContextResult(
                status="refused", code="context_changed", kind=self._kind
            )
        result = self._operations.apply_update(self._preparation, cancel=cancel)
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
        result = self._operations.save_update(self._preparation)
        return self._retain(result, selection_id=expected.selection_id)

    def load(self, vault, *, selection_id):
        request_identity(selection_id)
        self._preparation = self._binding = None
        self._revision += 1
        result = self._operations.load_update(vault)
        self._kind = result.kind
        return self._project(result)

    def resume(self, vault, *, selection_id):
        request_identity(selection_id)
        self._preparation = self._binding = None
        self._revision += 1
        result = self._operations.resume_update(vault)
        return self._retain(result, selection_id=selection_id)
