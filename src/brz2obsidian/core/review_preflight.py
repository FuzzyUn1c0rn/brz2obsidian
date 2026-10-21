"""Normalized operation/state/consent gates; no Git, storage or process access."""

import json
from hashlib import sha256

from brz2obsidian.contracts import ProposalAssumption, ReviewRequirement


def preflight_blockers(facts, preflight, proposal):
    result = []
    if preflight.operation_status != "idle":
        result.append("operation:" + preflight.operation_status)
    if preflight.state_status == "supported":
        if (
            not preflight.state_schema
            or preflight.state_version is None
            or preflight.state_version < 1
        ):
            result.append("state:incomplete_facts")
    elif preflight.state_status == "absent":
        if (
            facts.format_operation.kind != "onboarding"
            or preflight.state_schema is not None
            or preflight.state_version is not None
        ):
            result.append("state:onboarding_required")
    else:
        result.append("state:" + preflight.state_status)
    known = {c.subject_id for c in proposal.changes}
    for consent in preflight.consents:
        if not set(consent.subjects) <= known or len(set(consent.subjects)) != len(
            consent.subjects
        ):
            result.append("consent_scope:" + consent.consent_id)
        if consent.requirement in ("unknown", "unsupported") or consent.policy not in (
            "ordinary",
            "builtin_transform",
        ):
            result.append("policy_refused:" + consent.consent_id)
        if consent.policy == "builtin_transform" and (
            consent.kind != "storage" or consent.requirement != "required"
        ):
            result.append("exact_storage_consent:" + consent.consent_id)
    return tuple(result)


def consent_requirements(preflight, proposal, approvals):
    result = []
    for consent in preflight.consents:
        if consent.requirement == "not_required":
            continue
        selected = [
            c
            for c in proposal.changes
            if not consent.subjects or c.subject_id in consent.subjects
        ]
        dependencies = []
        values = []
        for change in selected:
            pertinent = [
                a
                for a in change.assumptions
                if consent.kind == "storage"
                or a.kind
                in ("identity", "target", "format", "history", "operation", "policy")
            ]
            dependencies.extend(a.key for a in pertinent)
            approved = next(
                (a for a in reversed(approvals) if a.change_id == change.change_id),
                None,
            )
            content = change.result if approved is None else approved.result
            values.append(
                (
                    change.subject_id,
                    [(a.key, a.fingerprint) for a in pertinent],
                    None
                    if consent.kind != "storage"
                    else (
                        change.target_path
                        if approved is None
                        else approved.target_path,
                        None if content is None else sha256(content.data).hexdigest(),
                        []
                        if approved is None
                        else [
                            (a.key, a.fingerprint)
                            for a in approved.assumptions
                            if a.kind == "candidate"
                        ],
                    ),
                )
            )
        fingerprint = sha256(
            json.dumps(
                (consent.model_dump(mode="json"), values), sort_keys=True
            ).encode()
        ).hexdigest()
        key = "consent:" + consent.consent_id
        assumption = ProposalAssumption(
            key=key,
            kind="policy",
            fingerprint=fingerprint,
            depends_on=tuple(sorted(set(dependencies))),
        )
        result.append(
            ReviewRequirement(
                requirement_id=key,
                domain=consent.kind,
                change_id=key,
                choices=("accept", "decline")
                if consent.requirement == "required"
                and consent.policy in ("ordinary", "builtin_transform")
                else (),
                assumptions=(assumption,),
            )
        )
    return tuple(result)
