"""One scoped configuration choice expressed by existing canonical S1 actions."""

import json
from hashlib import sha256

from brz2obsidian.contracts import ReviewAction
from brz2obsidian.core import inspect_review_choices

from .review_choices import requirement_digest, review_choice_action
from .update_context_contracts import UpdateConfigurationOffer
from .update_contracts import UpdatePreparation, UpdateResult


def configuration_choice_offer(preparation):
    preparation = UpdatePreparation.model_validate(preparation)
    plan = preparation.review
    requirements = {row.change_id: row for row in inspect_review_choices(plan)}
    changes = configuration_changes(plan)
    if preparation.kind != "format_transition" or not changes:
        return None
    material = (
        plan.proposal.proposal_id,
        plan.proposal.generation,
        tuple(
            (key, tuple((a.key, a.fingerprint) for a in value.assumptions))
            for key, value in sorted(changes.items())
        ),
    )
    selected = {a.choice for a in plan.approvals if a.change_id in changes}
    return UpdateConfigurationOffer(
        group_id=sha256(json.dumps(material).encode("utf-8")).hexdigest(),
        member_count=len(changes),
        choices=tuple(
            choice
            for choice in ("current", "incoming")
            if all(
                key in requirements and choice in requirements[key].enabled_choices
                for key in changes
            )
        ),
        selected=next(iter(selected))
        if len(selected) == 1
        and selected <= {"current", "incoming"}
        and len(tuple(a for a in plan.approvals if a.change_id in changes))
        == len(changes)
        else None,
    )


def resolve_configuration_choice(operations, preparation, *, group_id, choice):
    try:
        preparation = UpdatePreparation.model_validate(preparation)
        offered = configuration_choice_offer(preparation)
        if (
            offered is None
            or group_id != offered.group_id
            or choice not in offered.choices
        ):
            return operations.resolve_configuration(preparation, ())
        changes = configuration_changes(preparation.review)
        requirements = {
            row.change_id: row for row in inspect_review_choices(preparation.review)
        }
        actions = tuple(
            review_choice_action(
                preparation,
                requirement_id=requirements[key].requirement_id,
                choice=choice,
                assumptions_digest=requirement_digest(requirements[key]),
            )
            for key in sorted(changes)
        )
        return operations.resolve_configuration(preparation, actions)
    except ValueError, TypeError, KeyError:
        return operations.resolve_configuration(preparation, ())


def configuration_changes(plan):
    return {
        change.change_id: change
        for change in plan.proposal.changes
        if change.format_review is not None
        and change.format_review.configuration_choice
    }


def configuration_effects_authorized(preparation, selected):
    if preparation.kind != "format_transition" or any(
        path.startswith(".obsidian/") for path in selected.remove_paths
    ):
        return False
    plan = preparation.review
    offered = configuration_changes(plan)
    approved = {approval.change_id: approval for approval in plan.approvals}
    if not offered or any(change_id not in approved for change_id in offered):
        return False
    choices = {approved[change_id].choice for change_id in offered}
    if len(choices) != 1 or not choices <= {"current", "incoming"}:
        return False
    allowed = {}
    for change_id, change in offered.items():
        approval = approved[change_id]
        subject = next(
            s
            for s in plan.producer_facts.subjects
            if (s.item_id, s.facet) == (change.item_id, change.facet)
        )
        if (
            approval.domain != "configuration"
            or approval.provenance != "explicit_user"
            or subject.output_role != "configuration"
            or not subject.path.startswith(".obsidian/")
            or approval.target_path != subject.path
            or change.target_path != subject.path
        ):
            return False
        if approval.result is not None:
            allowed[approval.target_path] = approval.result
    return all(
        not row.path.startswith(".obsidian/") or allowed.get(row.path) == row.content
        for row in selected.files
    )


def resolve_configuration(operations, preparation, actions):
    original = None
    try:
        original = UpdatePreparation.model_validate(preparation)
        plan = original.review
        offered = configuration_changes(plan)
        actions = tuple(ReviewAction.model_validate(action) for action in actions)
        qualified = (
            original.kind == "format_transition"
            and bool(offered)
            and len(actions) == len(offered)
            and {action.change_id for action in actions} == set(offered)
            and len({action.decision_id for action in actions}) == len(actions)
            and len({action.choice for action in actions}) == 1
            and all(
                action.domain == "configuration"
                and action.choice in ("current", "incoming")
                and action.proposal_id == plan.proposal.proposal_id
                and action.expected_generation == plan.proposal.generation
                and action.reviewed_assumptions == offered[action.change_id].assumptions
                for action in actions
            )
        )
        if qualified:
            current = original
            for action in actions:
                result = operations.resolve_update(current, action)
                if (
                    result.code != "accepted"
                    or result.preparation is None
                    or result.preparation.review.proposal.proposal_id
                    != plan.proposal.proposal_id
                    or result.preparation.review.proposal.generation
                    != plan.proposal.generation
                ):
                    break
                current = result.preparation
            else:
                return result
    except OSError, ValueError, TypeError, AttributeError, KeyError:
        pass
    return UpdateResult(
        kind=original.kind if original is not None else "format_transition",
        status="refused",
        code="configuration_group_mismatch",
        preparation=original,
        operation_id=original.review.proposal.proposal_id
        if original is not None
        else None,
        generation=original.review.proposal.generation
        if original is not None
        else None,
        changes=len(original.review.proposal.changes) if original is not None else 0,
        unresolved=len(original.review.requirements) if original is not None else 0,
        history_retained=original is not None and original.locator is not None,
        checkpoint=original.locator if original is not None else None,
        checkpoint_commit=original.locator.commit
        if original is not None and original.locator is not None
        else None,
        vault=original.vault if original is not None else None,
        next_actions=("resolve_configuration",)
        if original is not None and original.kind == "format_transition"
        else ("review_configuration",),
    )
