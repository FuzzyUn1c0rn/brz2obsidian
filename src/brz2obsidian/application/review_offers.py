"""Bounded read-only summaries over the canonical offered review actions."""

from hashlib import sha256

from brz2obsidian.core import inspect_review_choices

from .review_choices import requirement_digest
from .update_context_contracts import UpdateChoiceDetail, UpdateChoiceOffer
from .update_contracts import UpdatePreparation


def _slice(rows, offset, limit):
    if (
        type(offset) is not int
        or offset < 0
        or type(limit) is not int
        or not 1 <= limit <= 100
    ):
        raise ValueError("Invalid action page")
    end = min(len(rows), offset + limit)
    return rows[offset:end], len(rows), end if end < len(rows) else None


def choice_offers(preparation):
    plan = UpdatePreparation.model_validate(preparation).review
    return review_plan_choice_offers(plan)


def review_plan_choice_offers(plan):
    result = []
    for row in inspect_review_choices(plan):
        selected = next(
            (
                a
                for a in plan.approvals
                if a.change_id == row.change_id and a.domain == row.domain
            ),
            None,
        )
        disclosure, policy, count = "", None, 0
        if row.domain in ("tracking", "storage"):
            consent = next(
                c
                for c in plan.preflight.consents
                if c.consent_id == row.change_id.removeprefix("consent:")
            )
            decision = next(
                (c for c in plan.consents if c.consent_id == consent.consent_id), None
            )
            selected = decision or selected
            disclosure, policy, count = (
                consent.disclosure,
                consent.policy,
                len(consent.subjects) or len(plan.proposal.changes),
            )
        elif row.domain == "compatible_group":
            count = next(g.count for g in plan.groups if g.group_id == row.change_id)
        elif row.domain == "identity":
            count = len(
                next(
                    c.identity_review.candidates
                    for c in plan.proposal.changes
                    if c.change_id == row.change_id
                )
            )
        result.append(
            UpdateChoiceOffer(
                requirement_id=row.requirement_id,
                change_id=row.change_id,
                domain=row.domain,
                choices=row.enabled_choices,
                unavailable_choices=tuple(a for a in row.availability if not a.enabled),
                assumptions_digest=requirement_digest(row),
                selected=selected.choice if selected else None,
                decision_id=selected.decision_id if selected else None,
                disclosure=disclosure[:2048],
                policy=policy,
                detail_count=count,
                detail_omitted=len(disclosure) > 2048,
            )
        )
    return tuple(result)


def choice_page(preparation, *, offset=0, limit=100):
    return _slice(choice_offers(preparation), offset, limit)


def review_plan_choice_page(plan, *, offset=0, limit=100):
    return _slice(review_plan_choice_offers(plan), offset, limit)


def choice_detail_page(preparation, *, requirement_id, offset=0, limit=100):
    plan = UpdatePreparation.model_validate(preparation).review
    requirement = next(
        row
        for row in inspect_review_choices(plan)
        if row.requirement_id == requirement_id
    )
    rows = []
    if requirement.domain == "identity":
        change = next(
            c for c in plan.proposal.changes if c.change_id == requirement.change_id
        )
        for entry in change.identity_review.candidates:
            content = entry.current.content
            rows.append(
                UpdateChoiceDetail(
                    kind="identity",
                    entry_id=entry.entry_id,
                    path=entry.current.path,
                    identity_state=entry.identity_state,
                    eligible=entry.eligible,
                    target_safe=entry.target_safe,
                    existence=entry.current.existence,
                    size=len(content.data) if content is not None else None,
                    sha256=sha256(content.data).hexdigest()
                    if content is not None
                    else None,
                )
            )
    elif requirement.domain == "compatible_group":
        group = next(g for g in plan.groups if g.group_id == requirement.change_id)
        rows = [
            UpdateChoiceDetail(
                kind="compatible_group",
                change_id=c.change_id,
                subject_id=c.subject_id,
                path=c.path,
                size=len(c.result.data),
            )
            for c in group.comparisons
        ]
    elif requirement.domain in ("tracking", "storage"):
        consent = next(
            c
            for c in plan.preflight.consents
            if c.consent_id == requirement.change_id.removeprefix("consent:")
        )
        rows = [
            UpdateChoiceDetail(
                kind="consent_scope",
                change_id=c.change_id,
                subject_id=c.subject_id,
                path=c.target_path,
            )
            for c in plan.proposal.changes
            if not consent.subjects or c.subject_id in consent.subjects
        ]
    return _slice(tuple(rows), offset, limit)
